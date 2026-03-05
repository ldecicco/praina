import uuid
from typing import Any

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.organization import PartnerOrganization, Team, TeamMember
from app.models.project import Project, ProjectStatus
from app.models.work import (
    Deliverable,
    Milestone,
    Task,
    WorkPackage,
    deliverable_collaborators,
    milestone_collaborators,
    task_collaborators,
    wp_collaborators,
)
from app.schemas.organization import PartnerCreate, TeamCreate, TeamMemberCreate
from app.schemas.project import ProjectCreate
from app.schemas.work import DeliverableCreate, MilestoneCreate, TaskCreate, WorkPackageCreate


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class ConflictError(Exception):
    pass


ENTITY_DEFINITION: dict[str, dict[str, Any]] = {
    "work_package": {"model": WorkPackage, "table": wp_collaborators, "fk": "wp_id"},
    "task": {"model": Task, "table": task_collaborators, "fk": "task_id"},
    "milestone": {"model": Milestone, "table": milestone_collaborators, "fk": "milestone_id"},
    "deliverable": {"model": Deliverable, "table": deliverable_collaborators, "fk": "deliverable_id"},
}


class OnboardingService:
    def __init__(self, db: Session):
        self.db = db

    def create_project(self, payload: ProjectCreate) -> Project:
        project = Project(code=payload.code, title=payload.title, description=payload.description)
        self.db.add(project)
        self._safe_flush("Project code must be unique in the platform.")
        self._log_event(project.id, "project.created", "project", project.id, after_json=self._project_json(project))
        self.db.commit()
        self.db.refresh(project)
        return project

    def create_partner(self, project_id: uuid.UUID, payload: PartnerCreate) -> PartnerOrganization:
        self._get_project(project_id)
        partner = PartnerOrganization(project_id=project_id, short_name=payload.short_name, legal_name=payload.legal_name)
        self.db.add(partner)
        self._safe_flush("Partner short name must be unique within the project.")
        self._log_event(project_id, "partner.created", "partner_organization", partner.id, after_json=self._partner_json(partner))
        self.db.commit()
        self.db.refresh(partner)
        return partner

    def create_team(self, project_id: uuid.UUID, payload: TeamCreate) -> Team:
        org = self._get_partner(payload.organization_id, project_id)
        team = Team(project_id=project_id, organization_id=org.id, name=payload.name)
        self.db.add(team)
        self._safe_flush("Team could not be created due to a data conflict.")
        self._log_event(project_id, "team.created", "team", team.id, after_json=self._team_json(team))
        self.db.commit()
        self.db.refresh(team)
        return team

    def create_member(self, project_id: uuid.UUID, payload: TeamMemberCreate) -> TeamMember:
        org = self._get_partner(payload.organization_id, project_id)
        team = self._get_team(payload.team_id, project_id)
        if team.organization_id != org.id:
            raise ValidationError("Selected team does not belong to selected organization.")

        member = TeamMember(
            project_id=project_id,
            organization_id=org.id,
            team_id=team.id,
            full_name=payload.full_name,
            email=str(payload.email),
            role=payload.role,
            is_active=True,
        )
        self.db.add(member)
        self._safe_flush("Member email must be unique.")
        self._log_event(project_id, "member.created", "team_member", member.id, after_json=self._member_json(member))
        self.db.commit()
        self.db.refresh(member)
        return member

    def create_wp(self, project_id: uuid.UUID, payload: WorkPackageCreate) -> WorkPackage:
        self._get_project(project_id)
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        entity = WorkPackage(
            project_id=project_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Work package code must be unique within the project.")
        self._sync_collaborators(wp_collaborators, "wp_id", entity.id, project_id, payload.assignment.collaborating_team_ids)
        self._log_event(project_id, "wp.created", "work_package", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def create_task(self, project_id: uuid.UUID, payload: TaskCreate) -> Task:
        self._get_project(project_id)
        wp = self.db.scalar(select(WorkPackage).where(WorkPackage.id == payload.wp_id, WorkPackage.project_id == project_id))
        if not wp:
            raise NotFoundError("Work package not found in project.")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        entity = Task(
            project_id=project_id,
            wp_id=payload.wp_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Task code must be unique within the project.")
        self._sync_collaborators(task_collaborators, "task_id", entity.id, project_id, payload.assignment.collaborating_team_ids)
        self._log_event(project_id, "task.created", "task", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def create_milestone(self, project_id: uuid.UUID, payload: MilestoneCreate) -> Milestone:
        self._get_project(project_id)
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        entity = Milestone(
            project_id=project_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Milestone code must be unique within the project.")
        self._sync_collaborators(
            milestone_collaborators, "milestone_id", entity.id, project_id, payload.assignment.collaborating_team_ids
        )
        self._log_event(project_id, "milestone.created", "milestone", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def create_deliverable(self, project_id: uuid.UUID, payload: DeliverableCreate) -> Deliverable:
        self._get_project(project_id)
        if payload.wp_id:
            wp = self.db.scalar(select(WorkPackage).where(WorkPackage.id == payload.wp_id, WorkPackage.project_id == project_id))
            if not wp:
                raise NotFoundError("Work package not found in project.")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        entity = Deliverable(
            project_id=project_id,
            wp_id=payload.wp_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Deliverable code must be unique within the project.")
        self._sync_collaborators(
            deliverable_collaborators, "deliverable_id", entity.id, project_id, payload.assignment.collaborating_team_ids
        )
        self._log_event(project_id, "deliverable.created", "deliverable", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def list_projects(
        self, status: ProjectStatus | None, search: str | None, page: int, page_size: int
    ) -> tuple[list[Project], int]:
        stmt = select(Project)
        if status:
            stmt = stmt.where(Project.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Project.code.ilike(like), Project.title.ilike(like)))
        stmt = stmt.order_by(Project.created_at.desc())
        return self._paginate(stmt, page, page_size)

    def list_partners(
        self, project_id: uuid.UUID, search: str | None, page: int, page_size: int
    ) -> tuple[list[PartnerOrganization], int]:
        self._get_project(project_id)
        stmt = select(PartnerOrganization).where(PartnerOrganization.project_id == project_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(PartnerOrganization.short_name.ilike(like), PartnerOrganization.legal_name.ilike(like)))
        stmt = stmt.order_by(PartnerOrganization.short_name.asc())
        return self._paginate(stmt, page, page_size)

    def list_teams(
        self,
        project_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Team], int]:
        self._get_project(project_id)
        stmt = select(Team).where(Team.project_id == project_id)
        if organization_id:
            stmt = stmt.where(Team.organization_id == organization_id)
        if search:
            stmt = stmt.where(Team.name.ilike(f"%{search}%"))
        stmt = stmt.order_by(Team.name.asc())
        return self._paginate(stmt, page, page_size)

    def list_members(
        self,
        project_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TeamMember], int]:
        self._get_project(project_id)
        stmt = select(TeamMember).where(TeamMember.project_id == project_id)
        if organization_id:
            stmt = stmt.where(TeamMember.organization_id == organization_id)
        if team_id:
            stmt = stmt.where(TeamMember.team_id == team_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(TeamMember.full_name.ilike(like), TeamMember.email.ilike(like)))
        stmt = stmt.order_by(TeamMember.full_name.asc())
        return self._paginate(stmt, page, page_size)

    def list_work_packages(
        self, project_id: uuid.UUID, search: str | None, page: int, page_size: int
    ) -> tuple[list[WorkPackage], int]:
        self._get_project(project_id)
        stmt = select(WorkPackage).where(WorkPackage.project_id == project_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(WorkPackage.code.ilike(like), WorkPackage.title.ilike(like)))
        stmt = stmt.order_by(WorkPackage.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_tasks(
        self, project_id: uuid.UUID, wp_id: uuid.UUID | None, search: str | None, page: int, page_size: int
    ) -> tuple[list[Task], int]:
        self._get_project(project_id)
        stmt = select(Task).where(Task.project_id == project_id)
        if wp_id:
            stmt = stmt.where(Task.wp_id == wp_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Task.code.ilike(like), Task.title.ilike(like)))
        stmt = stmt.order_by(Task.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_milestones(
        self, project_id: uuid.UUID, search: str | None, page: int, page_size: int
    ) -> tuple[list[Milestone], int]:
        self._get_project(project_id)
        stmt = select(Milestone).where(Milestone.project_id == project_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Milestone.code.ilike(like), Milestone.title.ilike(like)))
        stmt = stmt.order_by(Milestone.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_deliverables(
        self, project_id: uuid.UUID, wp_id: uuid.UUID | None, search: str | None, page: int, page_size: int
    ) -> tuple[list[Deliverable], int]:
        self._get_project(project_id)
        stmt = select(Deliverable).where(Deliverable.project_id == project_id)
        if wp_id:
            stmt = stmt.where(Deliverable.wp_id == wp_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Deliverable.code.ilike(like), Deliverable.title.ilike(like)))
        stmt = stmt.order_by(Deliverable.code.asc())
        return self._paginate(stmt, page, page_size)

    def get_project(self, project_id: uuid.UUID) -> Project:
        return self._get_project(project_id)

    def get_assignment_matrix(
        self,
        project_id: uuid.UUID,
        entity_type: str | None,
        wp_id: uuid.UUID | None,
        leader_organization_id: uuid.UUID | None,
        responsible_person_id: uuid.UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        self._get_project(project_id)
        if entity_type and entity_type not in ENTITY_DEFINITION:
            raise ValidationError("entity_type must be one of: work_package, task, milestone, deliverable.")

        selected_types = [entity_type] if entity_type else list(ENTITY_DEFINITION.keys())
        rows: list[dict[str, Any]] = []

        for selected in selected_types:
            definition = ENTITY_DEFINITION[selected]
            model = definition["model"]
            stmt = select(model).where(model.project_id == project_id)

            if wp_id and hasattr(model, "wp_id"):
                stmt = stmt.where(model.wp_id == wp_id)
            if leader_organization_id:
                stmt = stmt.where(model.leader_organization_id == leader_organization_id)
            if responsible_person_id:
                stmt = stmt.where(model.responsible_person_id == responsible_person_id)

            entities = self.db.scalars(stmt.order_by(model.code.asc())).all()
            for entity in entities:
                collaborators = self.get_collaborators(definition["table"], definition["fk"], entity.id)
                rows.append(
                    {
                        "entity_type": selected,
                        "entity_id": str(entity.id),
                        "code": entity.code,
                        "title": entity.title,
                        "wp_id": str(getattr(entity, "wp_id")) if hasattr(entity, "wp_id") and getattr(entity, "wp_id") else None,
                        "leader_organization_id": str(entity.leader_organization_id),
                        "responsible_person_id": str(entity.responsible_person_id),
                        "collaborating_team_ids": [str(team_id) for team_id in collaborators],
                    }
                )

        rows.sort(key=lambda row: (row["entity_type"], row["code"]))
        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return rows[start:end], total

    def update_assignment(
        self,
        project_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        leader_organization_id: uuid.UUID,
        responsible_person_id: uuid.UUID,
        collaborating_team_ids: list[uuid.UUID],
    ) -> WorkPackage | Task | Milestone | Deliverable:
        self._get_project(project_id)
        if entity_type not in ENTITY_DEFINITION:
            raise ValidationError("entity_type must be one of: work_package, task, milestone, deliverable.")

        definition = ENTITY_DEFINITION[entity_type]
        model = definition["model"]
        table = definition["table"]
        foreign_key = definition["fk"]

        entity = self.db.scalar(select(model).where(model.id == entity_id, model.project_id == project_id))
        if not entity:
            raise NotFoundError(f"{entity_type} not found in project.")

        self._validate_assignment(project_id, leader_organization_id, responsible_person_id)

        before_json = self._work_json(entity)
        before_json["collaborating_team_ids"] = [
            str(team_id) for team_id in self.get_collaborators(table, foreign_key, entity.id)
        ]

        entity.leader_organization_id = leader_organization_id
        entity.responsible_person_id = responsible_person_id
        self._sync_collaborators(table, foreign_key, entity.id, project_id, collaborating_team_ids)
        self._safe_flush("Assignment update failed due to a data conflict.")

        after_json = self._work_json(entity)
        after_json["collaborating_team_ids"] = [
            str(team_id) for team_id in self.get_collaborators(table, foreign_key, entity.id)
        ]

        self._log_event(
            project_id=project_id,
            event_type=f"{entity_type}.assignment_updated",
            entity_type=entity_type,
            entity_id=entity.id,
            before_json=before_json,
            after_json=after_json,
            reason="Assignment matrix update",
        )
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def validate_project(self, project_id: uuid.UUID) -> list[dict[str, str]]:
        self._get_project(project_id)
        errors: list[dict[str, str]] = []
        entity_checks = [
            ("work_package", WorkPackage, "work package"),
            ("task", Task, "task"),
            ("milestone", Milestone, "milestone"),
            ("deliverable", Deliverable, "deliverable"),
        ]
        for entity_type, model, label in entity_checks:
            entities = self.db.scalars(select(model).where(model.project_id == project_id)).all()
            for entity in entities:
                if not entity.leader_organization_id or not entity.responsible_person_id:
                    errors.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": str(entity.id),
                            "code": "MISSING_ASSIGNMENT",
                            "message": f"{label.title()} must have leader organization and responsible person.",
                        }
                    )
                    continue
                member = self.db.scalar(select(TeamMember).where(TeamMember.id == entity.responsible_person_id))
                if not member or not member.is_active:
                    errors.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": str(entity.id),
                            "code": "RESPONSIBLE_NOT_ACTIVE",
                            "message": "Responsible person must be active.",
                        }
                    )
                    continue
                if member.project_id != project_id:
                    errors.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": str(entity.id),
                            "code": "RESPONSIBLE_OUTSIDE_PROJECT",
                            "message": "Responsible person must belong to this project.",
                        }
                    )
                if member.organization_id != entity.leader_organization_id:
                    errors.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": str(entity.id),
                            "code": "RESPONSIBLE_NOT_IN_LEADER_ORG",
                            "message": "Responsible person must belong to the selected leader organization.",
                        }
                    )
        return errors

    def activate_project(self, project_id: uuid.UUID) -> tuple[Project, AuditEvent]:
        project = self._get_project(project_id)
        errors = self.validate_project(project_id)
        if errors:
            raise ValidationError("Project cannot be activated because validation failed.")
        before_json = self._project_json(project)
        project.status = ProjectStatus.active
        project.baseline_version = project.baseline_version + 1
        event = self._log_event(
            project.id,
            "project.activated",
            "project",
            project.id,
            before_json=before_json,
            after_json=self._project_json(project),
            reason="Activation after successful validation",
        )
        self.db.commit()
        self.db.refresh(project)
        self.db.refresh(event)
        return project, event

    def get_collaborators(self, table: Any, foreign_key: str, entity_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self.db.execute(select(table.c.team_id).where(getattr(table.c, foreign_key) == entity_id)).all()
        return [row[0] for row in rows]

    def _safe_flush(self, conflict_message: str) -> None:
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(conflict_message) from exc

    def _paginate(self, stmt: Any, page: int, page_size: int) -> tuple[list[Any], int]:
        total = self.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        paged_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        items = self.db.scalars(paged_stmt).all()
        return items, total

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _get_partner(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> PartnerOrganization:
        org = self.db.scalar(
            select(PartnerOrganization).where(
                PartnerOrganization.id == organization_id, PartnerOrganization.project_id == project_id
            )
        )
        if not org:
            raise NotFoundError("Partner organization not found in project.")
        return org

    def _get_team(self, team_id: uuid.UUID, project_id: uuid.UUID) -> Team:
        team = self.db.scalar(select(Team).where(Team.id == team_id, Team.project_id == project_id))
        if not team:
            raise NotFoundError("Team not found in project.")
        return team

    def _validate_assignment(
        self, project_id: uuid.UUID, leader_organization_id: uuid.UUID, responsible_person_id: uuid.UUID
    ) -> None:
        self._get_partner(leader_organization_id, project_id)
        member = self.db.scalar(
            select(TeamMember).where(
                TeamMember.id == responsible_person_id, TeamMember.project_id == project_id, TeamMember.is_active.is_(True)
            )
        )
        if not member:
            raise ValidationError("Responsible person must be an active member of this project.")
        if member.organization_id != leader_organization_id:
            raise ValidationError("Responsible person must belong to leader organization.")

    def _sync_collaborators(
        self,
        table: Any,
        foreign_key: str,
        entity_id: uuid.UUID,
        project_id: uuid.UUID,
        team_ids: list[uuid.UUID],
    ) -> None:
        unique_ids = list(dict.fromkeys(team_ids))
        self.db.execute(delete(table).where(getattr(table.c, foreign_key) == entity_id))
        if not unique_ids:
            return
        teams = self.db.scalars(select(Team).where(Team.id.in_(unique_ids), Team.project_id == project_id)).all()
        if len(teams) != len(unique_ids):
            raise ValidationError("All collaborating teams must belong to this project.")
        values = [{foreign_key: entity_id, "team_id": team_id} for team_id in unique_ids]
        self.db.execute(insert(table), values)

    def _log_event(
        self,
        project_id: uuid.UUID,
        event_type: str,
        entity_type: str,
        entity_id: uuid.UUID,
        after_json: dict[str, Any],
        before_json: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            project_id=project_id,
            actor_id=None,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            reason=reason,
            before_json=before_json,
            after_json=after_json,
        )
        self.db.add(event)
        self.db.flush()
        return event

    @staticmethod
    def _project_json(project: Project) -> dict[str, Any]:
        return {
            "id": str(project.id),
            "code": project.code,
            "title": project.title,
            "description": project.description,
            "baseline_version": project.baseline_version,
            "status": project.status.value if isinstance(project.status, ProjectStatus) else str(project.status),
        }

    @staticmethod
    def _partner_json(partner: PartnerOrganization) -> dict[str, Any]:
        return {
            "id": str(partner.id),
            "project_id": str(partner.project_id),
            "short_name": partner.short_name,
            "legal_name": partner.legal_name,
        }

    @staticmethod
    def _team_json(team: Team) -> dict[str, Any]:
        return {
            "id": str(team.id),
            "project_id": str(team.project_id),
            "organization_id": str(team.organization_id),
            "name": team.name,
        }

    @staticmethod
    def _member_json(member: TeamMember) -> dict[str, Any]:
        return {
            "id": str(member.id),
            "project_id": str(member.project_id),
            "organization_id": str(member.organization_id),
            "team_id": str(member.team_id),
            "full_name": member.full_name,
            "email": member.email,
            "role": member.role,
            "is_active": member.is_active,
        }

    @staticmethod
    def _work_json(entity: WorkPackage | Task | Milestone | Deliverable) -> dict[str, Any]:
        payload = {
            "id": str(entity.id),
            "project_id": str(entity.project_id),
            "code": entity.code,
            "title": entity.title,
            "description": entity.description,
            "leader_organization_id": str(entity.leader_organization_id),
            "responsible_person_id": str(entity.responsible_person_id),
        }
        if hasattr(entity, "wp_id"):
            payload["wp_id"] = str(entity.wp_id) if entity.wp_id else None
        return payload

