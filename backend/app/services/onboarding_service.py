import uuid
import secrets
import string
import shutil
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError as PydanticValidationError
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.auth import PlatformRole, ProjectMembership, ProjectRole, UserAccount
from app.models.audit import AuditEvent
from app.models.organization import PartnerOrganization, TeamMember
from app.models.document import ProjectDocument
from app.models.project import Project, ProjectMode, ProjectStatus
from app.models.proposal import ProjectProposalSection
from app.models.proposal_image import ProposalImage
from app.models.work import (
    Deliverable,
    DeliverableWorkflowStatus,
    Milestone,
    ProjectRisk,
    RiskLevel,
    RiskStatus,
    Task,
    WorkExecutionStatus,
    WorkPackage,
    deliverable_collaborators,
    deliverable_wps,
    milestone_collaborators,
    milestone_wps,
    task_collaborators,
    wp_collaborators,
)
from app.schemas.risk import ProjectRiskCreate, ProjectRiskUpdate
from app.schemas.organization import PartnerCreate, PartnerUpdate, TeamMemberCreate, TeamMemberUpdate
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.work import (
    DeliverableCreate,
    DeliverableUpdate,
    MilestoneCreate,
    MilestoneUpdate,
    TaskCreate,
    TaskUpdate,
    WorkPackageCreate,
    WorkPackageUpdate,
)


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
EMAIL_ADAPTER = TypeAdapter(EmailStr)


class OnboardingService:
    def __init__(self, db: Session, actor_user_id: uuid.UUID | None = None):
        self.db = db
        self.actor_user_id = actor_user_id

    def create_project(self, payload: ProjectCreate, actor_user_id: uuid.UUID | None = None) -> Project:
        effective_start_date = payload.start_date or date.today()
        effective_duration = payload.duration_months or 36
        reporting_dates = self._normalize_reporting_dates(
            effective_start_date, effective_duration, payload.reporting_dates
        )
        project = Project(
            code=payload.code,
            title=payload.title,
            description=payload.description,
            start_date=effective_start_date,
            duration_months=effective_duration,
            reporting_dates=[item.isoformat() for item in reporting_dates],
            project_mode=payload.project_mode,
            language=payload.language,
            coordinator_partner_id=payload.coordinator_partner_id,
            principal_investigator_id=payload.principal_investigator_id,
            proposal_template_id=payload.proposal_template_id,
        )
        self.db.add(project)
        self._safe_flush("Project code must be unique in the platform.")
        if actor_user_id:
            membership = ProjectMembership(
                project_id=project.id,
                user_id=actor_user_id,
                role=ProjectRole.project_owner.value,
            )
            self.db.add(membership)
            self._safe_flush("Project membership creation failed.")
        self._log_event(project.id, "project.created", "project", project.id, after_json=self._project_json(project))
        self.db.commit()
        self.db.refresh(project)
        return project

    def update_project(self, project_id: uuid.UUID, payload: ProjectUpdate) -> Project:
        project = self._get_project(project_id)
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return project

        if "duration_months" in update_data:
            self._validate_project_duration_change(project_id, update_data["duration_months"])
        effective_start_date = update_data.get("start_date", project.start_date)
        effective_duration = update_data.get("duration_months", project.duration_months)
        if "reporting_dates" in update_data:
            update_data["reporting_dates"] = self._normalize_reporting_dates(
                effective_start_date,
                effective_duration,
                update_data["reporting_dates"] or [],
            )
        elif "start_date" in update_data or "duration_months" in update_data:
            current_reporting_dates = [date.fromisoformat(item) for item in project.reporting_dates or []]
            self._normalize_reporting_dates(effective_start_date, effective_duration, current_reporting_dates)

        before_json = self._project_json(project)
        if "code" in update_data:
            project.code = update_data["code"]
        if "title" in update_data:
            project.title = update_data["title"]
        if "description" in update_data:
            project.description = update_data["description"]
        if "start_date" in update_data:
            project.start_date = update_data["start_date"]
        if "duration_months" in update_data:
            project.duration_months = update_data["duration_months"]
        if "reporting_dates" in update_data:
            project.reporting_dates = [item.isoformat() for item in update_data["reporting_dates"]]
        if "language" in update_data:
            project.language = update_data["language"]

        if "coordinator_partner_id" in update_data:
            new_coord_id = update_data["coordinator_partner_id"]
            old_coord_id = project.coordinator_partner_id
            if new_coord_id != old_coord_id:
                if old_coord_id:
                    old_coord = self.db.scalar(
                        select(PartnerOrganization).where(PartnerOrganization.id == old_coord_id)
                    )
                    if old_coord:
                        old_coord.partner_type = "beneficiary"
                if new_coord_id:
                    new_coord = self._get_partner(new_coord_id, project.id)
                    new_coord.partner_type = "coordinator"
                project.coordinator_partner_id = new_coord_id
                if project.principal_investigator_id and new_coord_id:
                    pi = self.db.scalar(
                        select(TeamMember).where(TeamMember.id == project.principal_investigator_id)
                    )
                    if pi and pi.organization_id != new_coord_id:
                        project.principal_investigator_id = None
                elif not new_coord_id:
                    project.principal_investigator_id = None

        if "principal_investigator_id" in update_data:
            new_pi_id = update_data["principal_investigator_id"]
            if new_pi_id:
                pi = self.db.scalar(
                    select(TeamMember).where(
                        TeamMember.id == new_pi_id,
                        TeamMember.project_id == project.id,
                    )
                )
                if not pi:
                    raise ValidationError("Principal investigator must belong to this project.")
                if project.coordinator_partner_id and pi.organization_id != project.coordinator_partner_id:
                    raise ValidationError("Principal investigator must belong to the coordinator organization.")
            project.principal_investigator_id = new_pi_id
        if "proposal_template_id" in update_data:
            project.proposal_template_id = update_data["proposal_template_id"]
        if "project_mode" in update_data:
            project.project_mode = update_data["project_mode"]

        self._safe_flush("Project update failed due to a data conflict.")
        self._log_event(
            project_id=project.id,
            event_type="project.updated",
            entity_type="project",
            entity_id=project.id,
            before_json=before_json,
            after_json=self._project_json(project),
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def mark_as_funded(
        self,
        project_id: uuid.UUID,
        start_date: date,
        duration_months: int,
        reporting_dates: list[date] | None = None,
    ) -> tuple[Project, "AuditEvent"]:
        project = self._get_project(project_id)
        if project.project_mode != "proposal":
            raise ValidationError("Only proposal-mode projects can be marked as funded.")
        if project.status == ProjectStatus.archived:
            raise ValidationError("Archived projects cannot be marked as funded.")
        before_json = self._project_json(project)
        project.project_mode = "execution"
        project.start_date = start_date
        project.duration_months = duration_months
        normalized = self._normalize_reporting_dates(start_date, duration_months, reporting_dates or [])
        project.reporting_dates = [item.isoformat() for item in normalized]
        self._safe_flush("Failed to mark project as funded.")
        event = self._log_event(
            project_id=project.id,
            event_type="project.marked_as_funded",
            entity_type="project",
            entity_id=project.id,
            before_json=before_json,
            after_json=self._project_json(project),
        )
        self.db.commit()
        self.db.refresh(project)
        return project, event

    def archive_project(self, project_id: uuid.UUID) -> Project:
        if not self.actor_user_id:
            raise ValidationError("Only super_admin can archive projects.")
        actor = self.db.get(UserAccount, self.actor_user_id)
        if not actor or actor.platform_role != PlatformRole.super_admin.value:
            raise ValidationError("Only super_admin can archive projects.")
        project = self._get_project(project_id)
        before_json = self._project_json(project)
        project.status = ProjectStatus.archived
        self._safe_flush("Failed to archive project.")
        self._log_event(
            project_id=project.id,
            event_type="project.archived",
            entity_type="project",
            entity_id=project.id,
            before_json=before_json,
            after_json=self._project_json(project),
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def hard_delete_project(self, project_id: uuid.UUID) -> None:
        if not self.actor_user_id:
            raise ValidationError("Only super_admin can delete projects.")
        actor = self.db.get(UserAccount, self.actor_user_id)
        if not actor or actor.platform_role != PlatformRole.super_admin.value:
            raise ValidationError("Only super_admin can delete projects.")
        project = self._get_project(project_id)
        proposal_image_paths = [
            row.storage_path
            for row in self.db.scalars(select(ProposalImage).where(ProposalImage.project_id == project_id)).all()
        ]
        documents_root = Path(settings.documents_storage_path)
        if not documents_root.is_absolute():
            documents_root = (Path.cwd() / documents_root).resolve()
        project_documents_dir = documents_root / str(project_id)
        storage_root = Path(getattr(settings, "storage_root", "storage"))
        if not storage_root.is_absolute():
            storage_root = (Path.cwd() / storage_root).resolve()
        proposal_images_dir = storage_root / "proposal-images" / str(project_id)
        self.db.delete(project)
        self.db.commit()
        if project_documents_dir.exists():
            shutil.rmtree(project_documents_dir, ignore_errors=True)
        if proposal_images_dir.exists():
            shutil.rmtree(proposal_images_dir, ignore_errors=True)
        for relative_path in proposal_image_paths:
            path = storage_root / relative_path
            if path.exists():
                path.unlink(missing_ok=True)

    def create_partner(self, project_id: uuid.UUID, payload: PartnerCreate) -> PartnerOrganization:
        self._get_project(project_id)
        partner = PartnerOrganization(
            project_id=project_id,
            short_name=payload.short_name,
            legal_name=payload.legal_name,
            partner_type=payload.partner_type,
            country=payload.country,
            expertise=payload.expertise,
        )
        self.db.add(partner)
        self._safe_flush("Partner short name must be unique within the project.")
        self._log_event(project_id, "partner.created", "partner_organization", partner.id, after_json=self._partner_json(partner))
        self.db.commit()
        self.db.refresh(partner)
        return partner

    def update_partner(self, project_id: uuid.UUID, partner_id: uuid.UUID, payload: PartnerUpdate) -> PartnerOrganization:
        self._get_project(project_id)
        partner = self._get_partner(partner_id, project_id)
        before_json = self._partner_json(partner)
        partner.short_name = payload.short_name
        partner.legal_name = payload.legal_name
        if payload.partner_type is not None:
            partner.partner_type = payload.partner_type
        if payload.country is not None:
            partner.country = payload.country
        if payload.expertise is not None:
            partner.expertise = payload.expertise
        self._safe_flush("Partner short name must be unique within the project.")
        self._log_event(
            project_id=project_id,
            event_type="partner.updated",
            entity_type="partner_organization",
            entity_id=partner.id,
            before_json=before_json,
            after_json=self._partner_json(partner),
            reason="Partner updated",
        )
        self.db.commit()
        self.db.refresh(partner)
        return partner

    def create_member(self, project_id: uuid.UUID, payload: TeamMemberCreate) -> TeamMember:
        partner = self._get_partner(payload.partner_id, project_id)
        linked_user_id, full_name, email, generated_password = self._resolve_member_identity(
            user_id=payload.user_id,
            full_name=payload.full_name,
            email=payload.email,
            create_user_if_missing=payload.create_user_if_missing,
            temporary_password=payload.temporary_password,
        )

        member = TeamMember(
            project_id=project_id,
            organization_id=partner.id,
            user_account_id=linked_user_id,
            full_name=full_name,
            email=email,
            role=payload.role,
            is_active=True,
        )
        self.db.add(member)
        self._safe_flush("Member email must be unique within the project.")
        if linked_user_id:
            self._ensure_project_membership(project_id, linked_user_id)
        self._log_event(project_id, "member.created", "team_member", member.id, after_json=self._member_json(member))
        self.db.commit()
        self.db.refresh(member)
        setattr(member, "temporary_password", generated_password)
        return member

    def update_member(self, project_id: uuid.UUID, member_id: uuid.UUID, payload: TeamMemberUpdate) -> TeamMember:
        member = self.db.scalar(select(TeamMember).where(TeamMember.id == member_id, TeamMember.project_id == project_id))
        if not member:
            raise NotFoundError("Member not found in project.")
        partner = self._get_partner(payload.partner_id, project_id)
        linked_user_id, full_name, email, generated_password = self._resolve_member_identity(
            user_id=payload.user_id,
            full_name=payload.full_name,
            email=payload.email,
            create_user_if_missing=payload.create_user_if_missing,
            temporary_password=payload.temporary_password,
        )

        before_json = self._member_json(member)
        member.organization_id = partner.id
        member.user_account_id = linked_user_id
        member.full_name = full_name
        member.email = email
        member.role = payload.role
        if payload.is_active is not None:
            member.is_active = payload.is_active

        self._safe_flush("Member update failed due to a data conflict.")
        if linked_user_id:
            self._ensure_project_membership(project_id, linked_user_id)
        self._log_event(
            project_id=project_id,
            event_type="member.updated",
            entity_type="team_member",
            entity_id=member.id,
            before_json=before_json,
            after_json=self._member_json(member),
            reason="Member updated",
        )
        self.db.commit()
        self.db.refresh(member)
        setattr(member, "temporary_password", generated_password)
        return member

    def delete_partner(self, project_id: uuid.UUID, partner_id: uuid.UUID) -> None:
        self._get_project(project_id)
        partner = self._get_partner(partner_id, project_id)
        member_count = self.db.scalar(
            select(func.count()).select_from(TeamMember).where(
                TeamMember.organization_id == partner_id,
                TeamMember.project_id == project_id,
            )
        )
        if member_count and member_count > 0:
            raise ValidationError(f"Cannot delete partner with {member_count} member(s). Remove them first.")
        before_json = self._partner_json(partner)
        self.db.delete(partner)
        self._log_event(project_id, "partner.deleted", "partner_organization", partner_id, before_json=before_json)
        self.db.commit()

    def delete_member(self, project_id: uuid.UUID, member_id: uuid.UUID) -> None:
        member = self.db.scalar(select(TeamMember).where(TeamMember.id == member_id, TeamMember.project_id == project_id))
        if not member:
            raise NotFoundError("Member not found in project.")
        before_json = self._member_json(member)
        self.db.delete(member)
        self._log_event(project_id, "member.deleted", "team_member", member_id, before_json=before_json)
        self.db.commit()

    def create_wp(self, project_id: uuid.UUID, payload: WorkPackageCreate) -> WorkPackage:
        project = self._get_project(project_id)
        self._validate_month_window(payload.start_month, payload.end_month, project.duration_months, "Work package")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        execution_status, completed_at, completed_by_member_id, completion_note = self._normalize_work_execution_state(
            project_id=project_id,
            entity_label="Work package",
            execution_status=payload.execution_status,
            responsible_person_id=payload.assignment.responsible_person_id,
            completed_by_member_id=payload.completed_by_member_id,
            completion_note=payload.completion_note,
        )
        entity = WorkPackage(
            project_id=project_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            start_month=payload.start_month,
            end_month=payload.end_month,
            execution_status=execution_status,
            completed_at=completed_at,
            completed_by_member_id=completed_by_member_id,
            completion_note=completion_note,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Work package code must be unique within the project.")
        self._sync_collaborators(
            wp_collaborators, "wp_id", entity.id, project_id, payload.assignment.collaborating_partner_ids
        )
        self._log_event(project_id, "wp.created", "work_package", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_wp(self, project_id: uuid.UUID, wp_id: uuid.UUID, payload: WorkPackageUpdate) -> WorkPackage:
        project = self._get_project(project_id)
        wp = self.db.scalar(
            select(WorkPackage).where(
                WorkPackage.id == wp_id,
                WorkPackage.project_id == project_id,
                WorkPackage.is_trashed.is_(False),
            )
        )
        if not wp:
            raise NotFoundError("Work package not found in project.")

        self._validate_month_window(payload.start_month, payload.end_month, project.duration_months, "Work package")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)

        tasks_in_wp = self.db.scalars(
            select(Task).where(
                Task.project_id == project_id,
                Task.wp_id == wp_id,
                Task.is_trashed.is_(False),
            )
        ).all()
        for task in tasks_in_wp:
            if task.start_month < payload.start_month or task.end_month > payload.end_month:
                raise ValidationError("Cannot update WP window because existing tasks would fall outside the new WP window.")

        deliverables_in_wp = self.db.scalars(
            select(Deliverable)
            .join(deliverable_wps, deliverable_wps.c.deliverable_id == Deliverable.id)
            .where(
                Deliverable.project_id == project_id,
                Deliverable.is_trashed.is_(False),
                deliverable_wps.c.wp_id == wp_id,
            )
        ).all()
        for deliverable in deliverables_in_wp:
            if deliverable.due_month > payload.end_month:
                raise ValidationError("Cannot update WP end month because existing deliverables are due after the new WP end.")

        execution_status, completed_at, completed_by_member_id, completion_note = self._normalize_work_execution_state(
            project_id=project_id,
            entity_label="Work package",
            execution_status=payload.execution_status,
            responsible_person_id=payload.assignment.responsible_person_id,
            completed_by_member_id=payload.completed_by_member_id,
            completion_note=payload.completion_note,
        )
        if execution_status == WorkExecutionStatus.closed:
            open_tasks = self.db.scalars(
                select(Task).where(
                    Task.project_id == project_id,
                    Task.wp_id == wp_id,
                    Task.is_trashed.is_(False),
                    Task.execution_status != WorkExecutionStatus.closed,
                )
            ).all()
            if open_tasks:
                raise ValidationError("A work package can be closed only after all its tasks are closed.")

        before_json = self._work_json(wp)
        before_json["collaborating_partner_ids"] = [str(pid) for pid in self.get_collaborators(wp_collaborators, "wp_id", wp.id)]

        wp.code = payload.code
        wp.title = payload.title
        wp.description = payload.description
        wp.start_month = payload.start_month
        wp.end_month = payload.end_month
        wp.execution_status = execution_status
        wp.completed_at = completed_at
        wp.completed_by_member_id = completed_by_member_id
        wp.completion_note = completion_note
        wp.leader_organization_id = payload.assignment.leader_organization_id
        wp.responsible_person_id = payload.assignment.responsible_person_id
        self._sync_collaborators(
            wp_collaborators, "wp_id", wp.id, project_id, payload.assignment.collaborating_partner_ids
        )
        self._safe_flush("Work package update failed due to a data conflict.")

        after_json = self._work_json(wp)
        after_json["collaborating_partner_ids"] = [str(pid) for pid in self.get_collaborators(wp_collaborators, "wp_id", wp.id)]
        self._log_event(
            project_id=project_id,
            event_type="wp.updated",
            entity_type="work_package",
            entity_id=wp.id,
            before_json=before_json,
            after_json=after_json,
            reason="Work package updated",
        )
        self.db.commit()
        self.db.refresh(wp)
        return wp

    def create_task(self, project_id: uuid.UUID, payload: TaskCreate) -> Task:
        project = self._get_project(project_id)
        wp = self.db.scalar(
            select(WorkPackage).where(
                WorkPackage.id == payload.wp_id,
                WorkPackage.project_id == project_id,
                WorkPackage.is_trashed.is_(False),
            )
        )
        if not wp:
            raise NotFoundError("Work package not found in project.")
        self._validate_month_window(payload.start_month, payload.end_month, project.duration_months, "Task")
        if payload.start_month < wp.start_month or payload.end_month > wp.end_month:
            raise ValidationError("Task month window must stay inside the parent work package window.")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        execution_status, completed_at, completed_by_member_id, completion_note = self._normalize_work_execution_state(
            project_id=project_id,
            entity_label="Task",
            execution_status=payload.execution_status,
            responsible_person_id=payload.assignment.responsible_person_id,
            completed_by_member_id=payload.completed_by_member_id,
            completion_note=payload.completion_note,
        )
        entity = Task(
            project_id=project_id,
            wp_id=payload.wp_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            start_month=payload.start_month,
            end_month=payload.end_month,
            execution_status=execution_status,
            completed_at=completed_at,
            completed_by_member_id=completed_by_member_id,
            completion_note=completion_note,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Task code must be unique within the project.")
        self._sync_collaborators(
            task_collaborators, "task_id", entity.id, project_id, payload.assignment.collaborating_partner_ids
        )
        self._log_event(project_id, "task.created", "task", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_task(self, project_id: uuid.UUID, task_id: uuid.UUID, payload: TaskUpdate) -> Task:
        project = self._get_project(project_id)
        task = self.db.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.project_id == project_id,
                Task.is_trashed.is_(False),
            )
        )
        if not task:
            raise NotFoundError("Task not found in project.")
        wp = self.db.scalar(
            select(WorkPackage).where(
                WorkPackage.id == task.wp_id,
                WorkPackage.project_id == project_id,
                WorkPackage.is_trashed.is_(False),
            )
        )
        if not wp:
            raise NotFoundError("Parent work package not found in project.")

        self._validate_month_window(payload.start_month, payload.end_month, project.duration_months, "Task")
        if payload.start_month < wp.start_month or payload.end_month > wp.end_month:
            raise ValidationError("Task month window must stay inside the parent work package window.")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        execution_status, completed_at, completed_by_member_id, completion_note = self._normalize_work_execution_state(
            project_id=project_id,
            entity_label="Task",
            execution_status=payload.execution_status,
            responsible_person_id=payload.assignment.responsible_person_id,
            completed_by_member_id=payload.completed_by_member_id,
            completion_note=payload.completion_note,
        )

        before_json = self._work_json(task)
        before_json["collaborating_partner_ids"] = [str(pid) for pid in self.get_collaborators(task_collaborators, "task_id", task.id)]

        task.code = payload.code
        task.title = payload.title
        task.description = payload.description
        task.start_month = payload.start_month
        task.end_month = payload.end_month
        task.execution_status = execution_status
        task.completed_at = completed_at
        task.completed_by_member_id = completed_by_member_id
        task.completion_note = completion_note
        task.leader_organization_id = payload.assignment.leader_organization_id
        task.responsible_person_id = payload.assignment.responsible_person_id
        self._sync_collaborators(
            task_collaborators, "task_id", task.id, project_id, payload.assignment.collaborating_partner_ids
        )
        self._safe_flush("Task update failed due to a data conflict.")

        after_json = self._work_json(task)
        after_json["collaborating_partner_ids"] = [str(pid) for pid in self.get_collaborators(task_collaborators, "task_id", task.id)]
        self._log_event(
            project_id=project_id,
            event_type="task.updated",
            entity_type="task",
            entity_id=task.id,
            before_json=before_json,
            after_json=after_json,
            reason="Task updated",
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def create_milestone(self, project_id: uuid.UUID, payload: MilestoneCreate) -> Milestone:
        project = self._get_project(project_id)
        self._validate_due_month(payload.due_month, project.duration_months, "Milestone")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        milestone_wps_list = self._resolve_wps(project_id, payload.wp_ids, required=False)
        self._validate_due_month_against_wps(payload.due_month, milestone_wps_list, "Milestone")
        entity = Milestone(
            project_id=project_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            due_month=payload.due_month,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        self._safe_flush("Milestone code must be unique within the project.")
        self._sync_collaborators(
            milestone_collaborators, "milestone_id", entity.id, project_id, payload.assignment.collaborating_partner_ids
        )
        self._sync_work_package_links(milestone_wps, "milestone_id", entity.id, [wp.id for wp in milestone_wps_list])
        self._log_event(project_id, "milestone.created", "milestone", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_milestone(self, project_id: uuid.UUID, milestone_id: uuid.UUID, payload: MilestoneUpdate) -> Milestone:
        project = self._get_project(project_id)
        milestone = self.db.scalar(
            select(Milestone).where(
                Milestone.id == milestone_id,
                Milestone.project_id == project_id,
                Milestone.is_trashed.is_(False),
            )
        )
        if not milestone:
            raise NotFoundError("Milestone not found in project.")

        self._validate_due_month(payload.due_month, project.duration_months, "Milestone")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        milestone_wps_list = self._resolve_wps(project_id, payload.wp_ids, required=False)
        self._validate_due_month_against_wps(payload.due_month, milestone_wps_list, "Milestone")

        before_json = self._work_json(milestone)
        before_json["collaborating_partner_ids"] = [
            str(pid) for pid in self.get_collaborators(milestone_collaborators, "milestone_id", milestone.id)
        ]
        before_json["wp_ids"] = [str(wp_id) for wp_id in self.get_related_wps(milestone_wps, "milestone_id", milestone.id)]

        milestone.code = payload.code
        milestone.title = payload.title
        milestone.description = payload.description
        milestone.due_month = payload.due_month
        milestone.leader_organization_id = payload.assignment.leader_organization_id
        milestone.responsible_person_id = payload.assignment.responsible_person_id
        self._sync_collaborators(
            milestone_collaborators, "milestone_id", milestone.id, project_id, payload.assignment.collaborating_partner_ids
        )
        self._sync_work_package_links(milestone_wps, "milestone_id", milestone.id, [wp.id for wp in milestone_wps_list])
        self._safe_flush("Milestone update failed due to a data conflict.")

        after_json = self._work_json(milestone)
        after_json["collaborating_partner_ids"] = [
            str(pid) for pid in self.get_collaborators(milestone_collaborators, "milestone_id", milestone.id)
        ]
        after_json["wp_ids"] = [str(wp_id) for wp_id in self.get_related_wps(milestone_wps, "milestone_id", milestone.id)]
        self._log_event(
            project_id=project_id,
            event_type="milestone.updated",
            entity_type="milestone",
            entity_id=milestone.id,
            before_json=before_json,
            after_json=after_json,
            reason="Milestone updated",
        )
        self.db.commit()
        self.db.refresh(milestone)
        return milestone

    def create_deliverable(self, project_id: uuid.UUID, payload: DeliverableCreate) -> Deliverable:
        project = self._get_project(project_id)
        normalized_code = payload.code.strip()
        if not normalized_code:
            raise ValidationError("Deliverable code is required.")
        existing = self.db.scalar(
            select(Deliverable.id).where(
                Deliverable.project_id == project_id,
                func.lower(Deliverable.code) == func.lower(normalized_code),
            )
        )
        if existing:
            raise ConflictError("Deliverable code must be unique within the project.")
        deliverable_wps_list = self._resolve_wps(project_id, payload.wp_ids, required=True)
        self._validate_due_month(payload.due_month, project.duration_months, "Deliverable")
        self._validate_due_month_against_wps(payload.due_month, deliverable_wps_list, "Deliverable")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        self._validate_review_window(payload.review_due_month, payload.due_month)
        self._validate_review_owner(project_id, payload.review_owner_member_id)
        workflow_status = self._normalize_deliverable_workflow_status(payload.workflow_status)
        entity = Deliverable(
            project_id=project_id,
            code=normalized_code,
            title=payload.title,
            description=payload.description,
            due_month=payload.due_month,
            workflow_status=workflow_status,
            review_due_month=payload.review_due_month,
            review_owner_member_id=payload.review_owner_member_id,
            leader_organization_id=payload.assignment.leader_organization_id,
            responsible_person_id=payload.assignment.responsible_person_id,
        )
        self.db.add(entity)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            details = str(getattr(exc, "orig", exc)).lower()
            if "uq_deliverable_project_code" in details or "deliverables_project_id_code_key" in details:
                raise ConflictError("Deliverable code must be unique within the project.") from exc
            if "deliverables_wp_id" in details and "null value" in details:
                raise ValidationError("Database schema is outdated for deliverables. Run alembic upgrade head and retry.") from exc
            raise ConflictError("Deliverable creation failed due to a data conflict.") from exc
        self._sync_collaborators(
            deliverable_collaborators,
            "deliverable_id",
            entity.id,
            project_id,
            payload.assignment.collaborating_partner_ids,
        )
        self._sync_work_package_links(deliverable_wps, "deliverable_id", entity.id, [wp.id for wp in deliverable_wps_list])
        self._log_event(project_id, "deliverable.created", "deliverable", entity.id, after_json=self._work_json(entity))
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_deliverable(self, project_id: uuid.UUID, deliverable_id: uuid.UUID, payload: DeliverableUpdate) -> Deliverable:
        project = self._get_project(project_id)
        deliverable = self.db.scalar(
            select(Deliverable).where(
                Deliverable.id == deliverable_id,
                Deliverable.project_id == project_id,
                Deliverable.is_trashed.is_(False),
            )
        )
        if not deliverable:
            raise NotFoundError("Deliverable not found in project.")
        normalized_code = payload.code.strip()
        if not normalized_code:
            raise ValidationError("Deliverable code is required.")
        duplicate = self.db.scalar(
            select(Deliverable.id).where(
                Deliverable.project_id == project_id,
                Deliverable.id != deliverable_id,
                func.lower(Deliverable.code) == func.lower(normalized_code),
            )
        )
        if duplicate:
            raise ConflictError("Deliverable code must be unique within the project.")

        deliverable_wps_list = self._resolve_wps(project_id, payload.wp_ids, required=True)
        self._validate_due_month(payload.due_month, project.duration_months, "Deliverable")
        self._validate_due_month_against_wps(payload.due_month, deliverable_wps_list, "Deliverable")
        self._validate_assignment(project_id, payload.assignment.leader_organization_id, payload.assignment.responsible_person_id)
        self._validate_review_window(payload.review_due_month, payload.due_month)
        self._validate_review_owner(project_id, payload.review_owner_member_id)

        before_json = self._work_json(deliverable)
        before_json["collaborating_partner_ids"] = [
            str(pid) for pid in self.get_collaborators(deliverable_collaborators, "deliverable_id", deliverable.id)
        ]
        before_json["wp_ids"] = [str(wp_id) for wp_id in self.get_related_wps(deliverable_wps, "deliverable_id", deliverable.id)]

        deliverable.code = normalized_code
        deliverable.title = payload.title
        deliverable.description = payload.description
        deliverable.due_month = payload.due_month
        deliverable.workflow_status = self._normalize_deliverable_workflow_status(payload.workflow_status)
        deliverable.review_due_month = payload.review_due_month
        deliverable.review_owner_member_id = payload.review_owner_member_id
        deliverable.leader_organization_id = payload.assignment.leader_organization_id
        deliverable.responsible_person_id = payload.assignment.responsible_person_id
        self._sync_collaborators(
            deliverable_collaborators,
            "deliverable_id",
            deliverable.id,
            project_id,
            payload.assignment.collaborating_partner_ids,
        )
        self._sync_work_package_links(
            deliverable_wps, "deliverable_id", deliverable.id, [wp.id for wp in deliverable_wps_list]
        )
        self._safe_flush("Deliverable update failed due to a data conflict.")

        after_json = self._work_json(deliverable)
        after_json["collaborating_partner_ids"] = [
            str(pid) for pid in self.get_collaborators(deliverable_collaborators, "deliverable_id", deliverable.id)
        ]
        after_json["wp_ids"] = [str(wp_id) for wp_id in self.get_related_wps(deliverable_wps, "deliverable_id", deliverable.id)]
        self._log_event(
            project_id=project_id,
            event_type="deliverable.updated",
            entity_type="deliverable",
            entity_id=deliverable.id,
            before_json=before_json,
            after_json=after_json,
            reason="Deliverable updated",
        )
        self.db.commit()
        self.db.refresh(deliverable)
        return deliverable

    def create_risk(self, project_id: uuid.UUID, payload: ProjectRiskCreate) -> ProjectRisk:
        project = self._get_project(project_id)
        normalized_code = payload.code.strip()
        if not normalized_code:
            raise ValidationError("Risk code is required.")
        existing = self.db.scalar(
            select(ProjectRisk.id).where(
                ProjectRisk.project_id == project_id,
                func.lower(ProjectRisk.code) == func.lower(normalized_code),
            )
        )
        if existing:
            raise ConflictError("Risk code must be unique within the project.")
        if payload.due_month is not None:
            self._validate_due_month(payload.due_month, project.duration_months, "Risk")
        self._validate_assignment(project_id, payload.owner_partner_id, payload.owner_member_id)
        risk = ProjectRisk(
            project_id=project_id,
            code=normalized_code,
            title=payload.title,
            description=payload.description,
            mitigation_plan=payload.mitigation_plan,
            status=self._normalize_risk_status(payload.status),
            probability=self._normalize_risk_level(payload.probability),
            impact=self._normalize_risk_level(payload.impact),
            due_month=payload.due_month,
            owner_partner_id=payload.owner_partner_id,
            owner_member_id=payload.owner_member_id,
        )
        self.db.add(risk)
        self._safe_flush("Risk creation failed due to a data conflict.")
        self._log_event(project_id, "risk.created", "project_risk", risk.id, after_json=self._risk_json(risk))
        self.db.commit()
        self.db.refresh(risk)
        return risk

    def update_risk(self, project_id: uuid.UUID, risk_id: uuid.UUID, payload: ProjectRiskUpdate) -> ProjectRisk:
        project = self._get_project(project_id)
        risk = self.db.scalar(select(ProjectRisk).where(ProjectRisk.id == risk_id, ProjectRisk.project_id == project_id))
        if not risk:
            raise NotFoundError("Risk not found in project.")
        normalized_code = payload.code.strip()
        if not normalized_code:
            raise ValidationError("Risk code is required.")
        duplicate = self.db.scalar(
            select(ProjectRisk.id).where(
                ProjectRisk.project_id == project_id,
                ProjectRisk.id != risk_id,
                func.lower(ProjectRisk.code) == func.lower(normalized_code),
            )
        )
        if duplicate:
            raise ConflictError("Risk code must be unique within the project.")
        if payload.due_month is not None:
            self._validate_due_month(payload.due_month, project.duration_months, "Risk")
        self._validate_assignment(project_id, payload.owner_partner_id, payload.owner_member_id)

        before_json = self._risk_json(risk)
        risk.code = normalized_code
        risk.title = payload.title
        risk.description = payload.description
        risk.mitigation_plan = payload.mitigation_plan
        risk.status = self._normalize_risk_status(payload.status)
        risk.probability = self._normalize_risk_level(payload.probability)
        risk.impact = self._normalize_risk_level(payload.impact)
        risk.due_month = payload.due_month
        risk.owner_partner_id = payload.owner_partner_id
        risk.owner_member_id = payload.owner_member_id

        self._safe_flush("Risk update failed due to a data conflict.")
        self._log_event(
            project_id=project_id,
            event_type="risk.updated",
            entity_type="project_risk",
            entity_id=risk.id,
            before_json=before_json,
            after_json=self._risk_json(risk),
            reason="Risk updated",
        )
        self.db.commit()
        self.db.refresh(risk)
        return risk

    def list_risks(
        self,
        project_id: uuid.UUID,
        status_filter: str | None,
        owner_partner_id: uuid.UUID | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ProjectRisk], int]:
        self._get_project(project_id)
        stmt = select(ProjectRisk).where(ProjectRisk.project_id == project_id)
        if status_filter:
            stmt = stmt.where(ProjectRisk.status == self._normalize_risk_status(status_filter))
        if owner_partner_id:
            stmt = stmt.where(ProjectRisk.owner_partner_id == owner_partner_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(ProjectRisk.code.ilike(like), ProjectRisk.title.ilike(like)))
        stmt = stmt.order_by(ProjectRisk.updated_at.desc(), ProjectRisk.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_audit_events(
        self,
        project_id: uuid.UUID,
        event_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AuditEvent], int]:
        self._get_project(project_id)
        stmt = select(AuditEvent).where(AuditEvent.project_id == project_id)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        stmt = stmt.order_by(AuditEvent.created_at.desc())
        return self._paginate(stmt, page, page_size)

    def list_projects(self, status: ProjectStatus | None, search: str | None, page: int, page_size: int) -> tuple[list[Project], int]:
        stmt = select(Project)
        if status:
            stmt = stmt.where(Project.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Project.code.ilike(like), Project.title.ilike(like)))
        stmt = stmt.order_by(Project.created_at.desc())
        return self._paginate(stmt, page, page_size)

    def list_projects_for_user(
        self,
        user_id: uuid.UUID,
        platform_role: str,
        status: ProjectStatus | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Project], int]:
        stmt = select(Project)
        if platform_role != PlatformRole.super_admin.value:
            stmt = stmt.join(ProjectMembership, ProjectMembership.project_id == Project.id).where(ProjectMembership.user_id == user_id)
        if status:
            stmt = stmt.where(Project.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Project.code.ilike(like), Project.title.ilike(like)))
        stmt = stmt.order_by(Project.created_at.desc())
        return self._paginate(stmt, page, page_size)

    def list_partners(self, project_id: uuid.UUID, search: str | None, page: int, page_size: int) -> tuple[list[PartnerOrganization], int]:
        self._get_project(project_id)
        stmt = select(PartnerOrganization).where(PartnerOrganization.project_id == project_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(PartnerOrganization.short_name.ilike(like), PartnerOrganization.legal_name.ilike(like)))
        stmt = stmt.order_by(PartnerOrganization.short_name.asc())
        return self._paginate(stmt, page, page_size)

    def list_members(
        self,
        project_id: uuid.UUID,
        partner_id: uuid.UUID | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TeamMember], int]:
        self._get_project(project_id)
        stmt = select(TeamMember).where(TeamMember.project_id == project_id)
        if partner_id:
            stmt = stmt.where(TeamMember.organization_id == partner_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(TeamMember.full_name.ilike(like), TeamMember.email.ilike(like)))
        stmt = stmt.order_by(TeamMember.full_name.asc())
        return self._paginate(stmt, page, page_size)

    def list_work_packages(self, project_id: uuid.UUID, search: str | None, page: int, page_size: int) -> tuple[list[WorkPackage], int]:
        self._get_project(project_id)
        stmt = select(WorkPackage).where(WorkPackage.project_id == project_id, WorkPackage.is_trashed.is_(False))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(WorkPackage.code.ilike(like), WorkPackage.title.ilike(like)))
        stmt = stmt.order_by(WorkPackage.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_tasks(self, project_id: uuid.UUID, wp_id: uuid.UUID | None, search: str | None, page: int, page_size: int) -> tuple[list[Task], int]:
        self._get_project(project_id)
        stmt = select(Task).where(Task.project_id == project_id, Task.is_trashed.is_(False))
        if wp_id:
            stmt = stmt.where(Task.wp_id == wp_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Task.code.ilike(like), Task.title.ilike(like)))
        stmt = stmt.order_by(Task.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_milestones(self, project_id: uuid.UUID, search: str | None, page: int, page_size: int) -> tuple[list[Milestone], int]:
        self._get_project(project_id)
        stmt = select(Milestone).where(Milestone.project_id == project_id, Milestone.is_trashed.is_(False))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Milestone.code.ilike(like), Milestone.title.ilike(like)))
        stmt = stmt.order_by(Milestone.code.asc())
        return self._paginate(stmt, page, page_size)

    def list_deliverables(
        self, project_id: uuid.UUID, wp_id: uuid.UUID | None, search: str | None, page: int, page_size: int
    ) -> tuple[list[Deliverable], int]:
        self._get_project(project_id)
        stmt = select(Deliverable).where(Deliverable.project_id == project_id, Deliverable.is_trashed.is_(False))
        if wp_id:
            stmt = stmt.join(deliverable_wps, deliverable_wps.c.deliverable_id == Deliverable.id).where(deliverable_wps.c.wp_id == wp_id)
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
            stmt = select(model).where(model.project_id == project_id, model.is_trashed.is_(False))

            if wp_id:
                if selected == "task":
                    stmt = stmt.where(model.wp_id == wp_id)
                elif selected == "deliverable":
                    stmt = stmt.join(deliverable_wps, deliverable_wps.c.deliverable_id == model.id).where(deliverable_wps.c.wp_id == wp_id)
                elif selected == "milestone":
                    stmt = stmt.join(milestone_wps, milestone_wps.c.milestone_id == model.id).where(milestone_wps.c.wp_id == wp_id)
            if leader_organization_id:
                stmt = stmt.where(model.leader_organization_id == leader_organization_id)
            if responsible_person_id:
                stmt = stmt.where(model.responsible_person_id == responsible_person_id)

            entities = self.db.scalars(stmt.order_by(model.code.asc())).all()
            for entity in entities:
                collaborators = self.get_collaborators(definition["table"], definition["fk"], entity.id)
                linked_wps: list[uuid.UUID] = []
                if selected == "task" and hasattr(entity, "wp_id"):
                    linked_wps = [entity.wp_id]
                elif selected == "deliverable":
                    linked_wps = self.get_related_wps(deliverable_wps, "deliverable_id", entity.id)
                elif selected == "milestone":
                    linked_wps = self.get_related_wps(milestone_wps, "milestone_id", entity.id)
                rows.append(
                    {
                        "entity_type": selected,
                        "entity_id": str(entity.id),
                        "code": entity.code,
                        "title": entity.title,
                        "wp_id": str(linked_wps[0]) if linked_wps else None,
                        "leader_organization_id": str(entity.leader_organization_id),
                        "responsible_person_id": str(entity.responsible_person_id),
                        "collaborating_partner_ids": [str(partner_id) for partner_id in collaborators],
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
        collaborating_partner_ids: list[uuid.UUID],
    ) -> WorkPackage | Task | Milestone | Deliverable:
        self._get_project(project_id)
        if entity_type not in ENTITY_DEFINITION:
            raise ValidationError("entity_type must be one of: work_package, task, milestone, deliverable.")

        definition = ENTITY_DEFINITION[entity_type]
        model = definition["model"]
        table = definition["table"]
        foreign_key = definition["fk"]

        entity = self.db.scalar(
            select(model).where(model.id == entity_id, model.project_id == project_id, model.is_trashed.is_(False))
        )
        if not entity:
            raise NotFoundError(f"{entity_type} not found in project.")

        self._validate_assignment(project_id, leader_organization_id, responsible_person_id)

        before_json = self._work_json(entity)
        before_json["collaborating_partner_ids"] = [str(pid) for pid in self.get_collaborators(table, foreign_key, entity.id)]

        entity.leader_organization_id = leader_organization_id
        entity.responsible_person_id = responsible_person_id
        self._sync_collaborators(table, foreign_key, entity.id, project_id, collaborating_partner_ids)
        self._safe_flush("Assignment update failed due to a data conflict.")

        after_json = self._work_json(entity)
        after_json["collaborating_partner_ids"] = [str(pid) for pid in self.get_collaborators(table, foreign_key, entity.id)]

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

    def list_trashed_entities(
        self, project_id: uuid.UUID, search: str | None, page: int, page_size: int
    ) -> tuple[list[tuple[str, WorkPackage | Task | Milestone | Deliverable]], int]:
        self._get_project(project_id)
        entity_defs: list[tuple[str, type[WorkPackage | Task | Milestone | Deliverable]]] = [
            ("work_package", WorkPackage),
            ("task", Task),
            ("deliverable", Deliverable),
            ("milestone", Milestone),
        ]
        like = f"%{search}%" if search else None
        rows: list[tuple[str, WorkPackage | Task | Milestone | Deliverable]] = []
        for entity_type, model in entity_defs:
            stmt = select(model).where(model.project_id == project_id, model.is_trashed.is_(True))
            if like:
                stmt = stmt.where(or_(model.code.ilike(like), model.title.ilike(like)))
            items = self.db.scalars(stmt).all()
            rows.extend((entity_type, item) for item in items)

        rows.sort(
            key=lambda item: (
                item[1].trashed_at or datetime.min.replace(tzinfo=timezone.utc),
                item[0],
                item[1].code,
            ),
            reverse=True,
        )
        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        return rows[start:end], total

    def trash_entity(
        self, project_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> WorkPackage | Task | Milestone | Deliverable:
        if entity_type not in ENTITY_DEFINITION:
            raise ValidationError("entity_type must be one of: work_package, task, milestone, deliverable.")
        model = ENTITY_DEFINITION[entity_type]["model"]
        entity = self.db.scalar(select(model).where(model.id == entity_id, model.project_id == project_id))
        if not entity:
            raise NotFoundError(f"{entity_type} not found in project.")
        if entity.is_trashed:
            return entity

        timestamp = datetime.now(timezone.utc)
        entity.is_trashed = True
        entity.trashed_at = timestamp
        cascaded_counts: dict[str, int] = {}
        if entity_type == "work_package":
            cascaded_counts = self._cascade_trash_from_wp(project_id, entity.id, timestamp)

        after_json = self._work_json(entity)
        after_json["is_trashed"] = True
        after_json["trashed_at"] = timestamp.isoformat()
        if cascaded_counts:
            after_json["cascade"] = cascaded_counts
        self._log_event(
            project_id=project_id,
            event_type=f"{entity_type}.trashed",
            entity_type=entity_type,
            entity_id=entity.id,
            after_json=after_json,
            reason="Moved to trash",
        )
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def restore_entity(
        self, project_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> WorkPackage | Task | Milestone | Deliverable:
        if entity_type not in ENTITY_DEFINITION:
            raise ValidationError("entity_type must be one of: work_package, task, milestone, deliverable.")
        model = ENTITY_DEFINITION[entity_type]["model"]
        entity = self.db.scalar(select(model).where(model.id == entity_id, model.project_id == project_id))
        if not entity:
            raise NotFoundError(f"{entity_type} not found in project.")
        if not entity.is_trashed:
            return entity
        if entity_type == "task":
            parent_wp = self.db.scalar(select(WorkPackage).where(WorkPackage.id == entity.wp_id, WorkPackage.project_id == project_id))
            if not parent_wp or parent_wp.is_trashed:
                raise ValidationError("Task cannot be restored while its parent work package is trashed.")

        entity.is_trashed = False
        entity.trashed_at = None
        after_json = self._work_json(entity)
        after_json["is_trashed"] = False
        after_json["trashed_at"] = None
        self._log_event(
            project_id=project_id,
            event_type=f"{entity_type}.restored",
            entity_type=entity_type,
            entity_id=entity.id,
            after_json=after_json,
            reason="Restored from trash",
        )
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def validate_project(self, project_id: uuid.UUID) -> list[dict[str, str]]:
        project = self._get_project(project_id)
        errors: list[dict[str, str]] = []

        if project.project_mode == "proposal":
            return errors

        if not project.coordinator_partner_id:
            errors.append({
                "entity_type": "project",
                "entity_id": str(project.id),
                "code": "MISSING_COORDINATOR",
                "message": "Project must have a coordinator partner.",
            })
        if not project.principal_investigator_id:
            errors.append({
                "entity_type": "project",
                "entity_id": str(project.id),
                "code": "MISSING_PI",
                "message": "Project must have a principal investigator.",
            })
        if project.coordinator_partner_id and project.principal_investigator_id:
            pi = self.db.scalar(
                select(TeamMember).where(TeamMember.id == project.principal_investigator_id)
            )
            if pi and pi.organization_id != project.coordinator_partner_id:
                errors.append({
                    "entity_type": "project",
                    "entity_id": str(project.id),
                    "code": "PI_NOT_IN_COORDINATOR_ORG",
                    "message": "Principal investigator must belong to the coordinator organization.",
                })

        entity_checks = [
            ("work_package", WorkPackage, "work package"),
            ("task", Task, "task"),
            ("milestone", Milestone, "milestone"),
            ("deliverable", Deliverable, "deliverable"),
        ]
        for entity_type, model, label in entity_checks:
            entities = self.db.scalars(
                select(model).where(model.project_id == project_id, model.is_trashed.is_(False))
            ).all()
            for entity in entities:
                if not entity.leader_organization_id or not entity.responsible_person_id:
                    errors.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": str(entity.id),
                            "code": "MISSING_ASSIGNMENT",
                            "message": f"{label.title()} must have leader partner and responsible person.",
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
                            "message": "Responsible person must belong to the selected leader partner.",
                        }
                    )
                if hasattr(entity, "start_month") and hasattr(entity, "end_month"):
                    if entity.start_month > entity.end_month:
                        errors.append(
                            {
                                "entity_type": entity_type,
                                "entity_id": str(entity.id),
                                "code": "INVALID_MONTH_WINDOW",
                                "message": "start_month cannot be greater than end_month.",
                            }
                        )
                    if entity.end_month > project.duration_months:
                        errors.append(
                            {
                                "entity_type": entity_type,
                                "entity_id": str(entity.id),
                                "code": "MONTH_OUTSIDE_PROJECT",
                                "message": "Entity month window exceeds project duration.",
                            }
                        )
                if hasattr(entity, "due_month"):
                    if entity.due_month > project.duration_months:
                        errors.append(
                            {
                                "entity_type": entity_type,
                                "entity_id": str(entity.id),
                                "code": "DUE_MONTH_OUTSIDE_PROJECT",
                                "message": "Due month exceeds project duration.",
                            }
                        )
                if isinstance(entity, Task):
                    parent_wp = self.db.scalar(
                        select(WorkPackage).where(
                            WorkPackage.id == entity.wp_id,
                            WorkPackage.project_id == project_id,
                            WorkPackage.is_trashed.is_(False),
                        )
                    )
                    if parent_wp and (entity.start_month < parent_wp.start_month or entity.end_month > parent_wp.end_month):
                        errors.append(
                            {
                                "entity_type": entity_type,
                                "entity_id": str(entity.id),
                                "code": "TASK_OUTSIDE_WP_WINDOW",
                                "message": "Task month window must stay inside parent WP window.",
                            }
                        )
                if isinstance(entity, Deliverable):
                    linked_wps = self.get_related_wps(deliverable_wps, "deliverable_id", entity.id)
                    if not linked_wps:
                        errors.append(
                            {
                                "entity_type": entity_type,
                                "entity_id": str(entity.id),
                                "code": "DELIVERABLE_MISSING_WP",
                                "message": "Deliverable must be linked to at least one work package.",
                            }
                        )
                    else:
                        wp_end_months = [
                            wp.end_month
                            for wp in self.db.scalars(
                                select(WorkPackage).where(WorkPackage.id.in_(linked_wps), WorkPackage.project_id == project_id)
                            ).all()
                        ]
                        if wp_end_months and entity.due_month > min(wp_end_months):
                            errors.append(
                                {
                                    "entity_type": entity_type,
                                    "entity_id": str(entity.id),
                                    "code": "DELIVERABLE_AFTER_WP_END",
                                    "message": "Deliverable due month cannot be after the end month of linked work packages.",
                                }
                            )
                if isinstance(entity, Milestone):
                    linked_wps = self.get_related_wps(milestone_wps, "milestone_id", entity.id)
                    if linked_wps:
                        wp_end_months = [
                            wp.end_month
                            for wp in self.db.scalars(
                                select(WorkPackage).where(WorkPackage.id.in_(linked_wps), WorkPackage.project_id == project_id)
                            ).all()
                        ]
                        if wp_end_months and entity.due_month > min(wp_end_months):
                            errors.append(
                                {
                                    "entity_type": entity_type,
                                    "entity_id": str(entity.id),
                                    "code": "MILESTONE_AFTER_WP_END",
                                    "message": "Milestone due month cannot be after the end month of linked work packages.",
                                }
                            )
        # Proposal validation
        if project.proposal_template_id:
            proposal_sections = self.db.scalars(
                select(ProjectProposalSection).where(ProjectProposalSection.project_id == project_id)
            ).all()
            section_ids = [section.id for section in proposal_sections]
            doc_counts: dict[uuid.UUID, int] = {}
            if section_ids:
                doc_counts = dict(
                    self.db.execute(
                        select(ProjectDocument.proposal_section_id, func.count(ProjectDocument.id))
                        .where(
                            ProjectDocument.project_id == project_id,
                            ProjectDocument.proposal_section_id.in_(section_ids),
                        )
                        .group_by(ProjectDocument.proposal_section_id)
                    ).all()
                )
            today = date.today()
            for section in proposal_sections:
                if section.required and not section.owner_member_id:
                    errors.append({
                        "entity_type": "proposal_section",
                        "entity_id": str(section.id),
                        "code": "SECTION_MISSING_OWNER",
                        "message": f"Required proposal section '{section.title}' has no owner.",
                    })
                if section.required and not section.reviewer_member_id:
                    errors.append({
                        "entity_type": "proposal_section",
                        "entity_id": str(section.id),
                        "code": "SECTION_MISSING_REVIEWER",
                        "message": f"Required proposal section '{section.title}' has no reviewer.",
                    })
                if section.required and int(doc_counts.get(section.id, 0)) == 0:
                    errors.append({
                        "entity_type": "proposal_section",
                        "entity_id": str(section.id),
                        "code": "SECTION_MISSING_DOCUMENTS",
                        "message": f"Required proposal section '{section.title}' has no linked documents.",
                    })
                if section.due_date and section.due_date < today and section.status not in ("approved", "final"):
                    errors.append({
                        "entity_type": "proposal_section",
                        "entity_id": str(section.id),
                        "code": "SECTION_OVERDUE",
                        "message": f"Proposal section '{section.title}' is past its due date.",
                    })
                if section.due_date and section.status in ("not_started", "drafting"):
                    days_until = (section.due_date - today).days
                    if 0 < days_until <= 7:
                        errors.append({
                            "entity_type": "proposal_section",
                            "entity_id": str(section.id),
                            "code": "SECTION_STUCK_DRAFTING",
                            "message": f"Proposal section '{section.title}' is still in '{section.status}' with due date in {days_until} day(s).",
                        })

        return errors

    def activate_project(self, project_id: uuid.UUID) -> tuple[Project, AuditEvent]:
        project = self._get_project(project_id)
        errors = self.validate_project(project_id)
        if errors:
            raise ValidationError("Project cannot be activated because validation failed.")
        before_json = self._project_json(project)
        project.status = ProjectStatus.active
        project.baseline_version += 1
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
        rows = self.db.execute(select(table.c.partner_id).where(getattr(table.c, foreign_key) == entity_id)).all()
        return [row[0] for row in rows]

    def get_related_wps(self, table: Any, foreign_key: str, entity_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self.db.execute(select(table.c.wp_id).where(getattr(table.c, foreign_key) == entity_id)).all()
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

    def _get_partner(self, partner_id: uuid.UUID, project_id: uuid.UUID) -> PartnerOrganization:
        partner = self.db.scalar(
            select(PartnerOrganization).where(
                PartnerOrganization.id == partner_id, PartnerOrganization.project_id == project_id
            )
        )
        if not partner:
            raise NotFoundError("Partner not found in project.")
        return partner

    def _validate_assignment(self, project_id: uuid.UUID, leader_partner_id: uuid.UUID, responsible_person_id: uuid.UUID) -> None:
        self._get_partner(leader_partner_id, project_id)
        member = self.db.scalar(
            select(TeamMember).where(
                TeamMember.id == responsible_person_id, TeamMember.project_id == project_id, TeamMember.is_active.is_(True)
            )
        )
        if not member:
            raise ValidationError("Responsible person must be an active member of this project.")
        if member.organization_id != leader_partner_id:
            raise ValidationError("Responsible person must belong to leader partner.")

    def _validate_project_duration_change(self, project_id: uuid.UUID, duration_months: int) -> None:
        max_wp_end = self.db.scalar(
            select(func.max(WorkPackage.end_month)).where(WorkPackage.project_id == project_id, WorkPackage.is_trashed.is_(False))
        ) or 0
        max_task_end = self.db.scalar(
            select(func.max(Task.end_month)).where(Task.project_id == project_id, Task.is_trashed.is_(False))
        ) or 0
        max_milestone_due = (
            self.db.scalar(
                select(func.max(Milestone.due_month)).where(Milestone.project_id == project_id, Milestone.is_trashed.is_(False))
            )
            or 0
        )
        max_deliverable_due = (
            self.db.scalar(
                select(func.max(Deliverable.due_month)).where(
                    Deliverable.project_id == project_id, Deliverable.is_trashed.is_(False)
                )
            )
            or 0
        )
        max_required_month = max(max_wp_end, max_task_end, max_milestone_due, max_deliverable_due)
        max_risk_due = self.db.scalar(
            select(func.max(ProjectRisk.due_month)).where(ProjectRisk.project_id == project_id)
        ) or 0
        max_required_month = max(max_required_month, max_risk_due)
        if max_required_month > duration_months:
            raise ValidationError(
                f"Project duration cannot be less than M{max_required_month} because existing entities already use that month."
            )

    def _normalize_reporting_dates(
        self,
        start_date: date,
        duration_months: int,
        reporting_dates: list[date],
    ) -> list[date]:
        normalized = sorted(set(reporting_dates))
        if not normalized:
            return []

        project_end_date = self._project_end_date(start_date, duration_months)
        for item in normalized:
            if item < start_date:
                raise ValidationError("Reporting dates cannot be earlier than the project start date.")
            if item > project_end_date:
                raise ValidationError("Reporting dates cannot be beyond the project duration window.")
        return normalized

    @staticmethod
    def _project_end_date(start_date: date, duration_months: int) -> date:
        total_months = (start_date.year * 12 + (start_date.month - 1)) + max(duration_months, 1) - 1
        year = total_months // 12
        month = total_months % 12 + 1
        day = min(start_date.day, monthrange(year, month)[1])
        return date(year, month, day)

    @staticmethod
    def _normalize_deliverable_workflow_status(value: str) -> DeliverableWorkflowStatus:
        normalized = (value or DeliverableWorkflowStatus.draft.value).strip().lower()
        allowed = {item.value: item for item in DeliverableWorkflowStatus}
        if normalized not in allowed:
            raise ValidationError(
                f"Invalid deliverable workflow status. Allowed: {', '.join(sorted(allowed.keys()))}."
            )
        return allowed[normalized]

    def _normalize_work_execution_state(
        self,
        *,
        project_id: uuid.UUID,
        entity_label: str,
        execution_status: str,
        responsible_person_id: uuid.UUID,
        completed_by_member_id: uuid.UUID | None,
        completion_note: str | None,
    ) -> tuple[WorkExecutionStatus, datetime | None, uuid.UUID | None, str | None]:
        normalized = (execution_status or WorkExecutionStatus.planned.value).strip().lower()
        allowed = {item.value: item for item in WorkExecutionStatus}
        if normalized not in allowed:
            raise ValidationError(
                f"Invalid {entity_label.lower()} status. Allowed: {', '.join(sorted(allowed.keys()))}."
            )
        status = allowed[normalized]
        note = (completion_note or "").strip() or None

        if status == WorkExecutionStatus.closed:
            approver_id = completed_by_member_id or responsible_person_id
            member = self.db.get(TeamMember, approver_id)
            if not member or member.project_id != project_id or not member.is_active:
                raise ValidationError(f"{entity_label} closure approver is invalid.")
            if approver_id != responsible_person_id:
                raise ValidationError(f"{entity_label} can only be closed by its responsible person.")
            if not note:
                raise ValidationError(f"{entity_label} closure requires a completion note.")
            return status, datetime.now(timezone.utc), approver_id, note

        if completed_by_member_id:
            member = self.db.get(TeamMember, completed_by_member_id)
            if not member or member.project_id != project_id or not member.is_active:
                raise ValidationError(f"{entity_label} approver is invalid.")
        if status == WorkExecutionStatus.ready_for_closure and note:
            return status, None, completed_by_member_id, note
        return status, None, completed_by_member_id, note

    @staticmethod
    def _normalize_risk_level(value: str) -> RiskLevel:
        normalized = (value or RiskLevel.medium.value).strip().lower()
        allowed = {item.value: item for item in RiskLevel}
        if normalized not in allowed:
            raise ValidationError(f"Invalid risk level. Allowed: {', '.join(sorted(allowed.keys()))}.")
        return allowed[normalized]

    @staticmethod
    def _normalize_risk_status(value: str) -> RiskStatus:
        normalized = (value or RiskStatus.open.value).strip().lower()
        allowed = {item.value: item for item in RiskStatus}
        if normalized not in allowed:
            raise ValidationError(f"Invalid risk status. Allowed: {', '.join(sorted(allowed.keys()))}.")
        return allowed[normalized]

    @staticmethod
    def _validate_month_window(start_month: int, end_month: int, project_duration: int, entity_label: str) -> None:
        if start_month < 1 or end_month < 1:
            raise ValidationError(f"{entity_label} months must be >= M1.")
        if start_month > end_month:
            raise ValidationError(f"{entity_label} start month cannot be after end month.")
        if end_month > project_duration:
            raise ValidationError(f"{entity_label} end month cannot exceed project duration.")

    @staticmethod
    def _validate_due_month(due_month: int, project_duration: int, entity_label: str) -> None:
        if due_month < 1:
            raise ValidationError(f"{entity_label} due month must be >= M1.")
        if due_month > project_duration:
            raise ValidationError(f"{entity_label} due month cannot exceed project duration.")

    def _resolve_wps(self, project_id: uuid.UUID, wp_ids: list[uuid.UUID], required: bool) -> list[WorkPackage]:
        unique_ids = list(dict.fromkeys(wp_ids))
        if required and not unique_ids:
            raise ValidationError("At least one work package must be selected.")
        if not unique_ids:
            return []
        wps = self.db.scalars(
            select(WorkPackage).where(
                WorkPackage.id.in_(unique_ids),
                WorkPackage.project_id == project_id,
                WorkPackage.is_trashed.is_(False),
            )
        ).all()
        if len(wps) != len(unique_ids):
            raise NotFoundError("One or more work packages were not found in project.")
        return wps

    @staticmethod
    def _validate_due_month_against_wps(due_month: int, wps: list[WorkPackage], entity_label: str) -> None:
        if not wps:
            return
        min_wp_end = min(wp.end_month for wp in wps)
        if due_month > min_wp_end:
            raise ValidationError(f"{entity_label} due month cannot be after the end month of linked work packages.")

    @staticmethod
    def _validate_review_window(review_due_month: int | None, due_month: int) -> None:
        if review_due_month is None:
            return
        if review_due_month > due_month:
            raise ValidationError("Deliverable review due month cannot be after the deliverable due month.")

    def _validate_review_owner(self, project_id: uuid.UUID, review_owner_member_id: uuid.UUID | None) -> None:
        if not review_owner_member_id:
            return
        member = self.db.get(TeamMember, review_owner_member_id)
        if not member or member.project_id != project_id or not member.is_active:
            raise ValidationError("Selected deliverable review owner is invalid.")

    def _sync_collaborators(
        self,
        table: Any,
        foreign_key: str,
        entity_id: uuid.UUID,
        project_id: uuid.UUID,
        partner_ids: list[uuid.UUID],
    ) -> None:
        unique_ids = list(dict.fromkeys(partner_ids))
        self.db.execute(delete(table).where(getattr(table.c, foreign_key) == entity_id))
        if not unique_ids:
            return
        partners = self.db.scalars(
            select(PartnerOrganization).where(PartnerOrganization.id.in_(unique_ids), PartnerOrganization.project_id == project_id)
        ).all()
        if len(partners) != len(unique_ids):
            raise ValidationError("All collaborating partners must belong to this project.")
        values = [{foreign_key: entity_id, "partner_id": partner_id} for partner_id in unique_ids]
        self.db.execute(insert(table), values)

    def _sync_work_package_links(self, table: Any, foreign_key: str, entity_id: uuid.UUID, wp_ids: list[uuid.UUID]) -> None:
        unique_ids = list(dict.fromkeys(wp_ids))
        try:
            self.db.execute(delete(table).where(getattr(table.c, foreign_key) == entity_id))
            if not unique_ids:
                return
            values = [{foreign_key: entity_id, "wp_id": wp_id} for wp_id in unique_ids]
            self.db.execute(insert(table), values)
        except ProgrammingError as exc:
            details = str(getattr(exc, "orig", exc)).lower()
            if "does not exist" in details:
                table_name = getattr(table, "name", "wp link table")
                raise ValidationError(f"Database schema is outdated ({table_name} missing). Run alembic upgrade head.") from exc
            raise

    def _cascade_trash_from_wp(self, project_id: uuid.UUID, wp_id: uuid.UUID, timestamp: datetime) -> dict[str, int]:
        tasks = self.db.scalars(
            select(Task).where(Task.project_id == project_id, Task.wp_id == wp_id, Task.is_trashed.is_(False))
        ).all()
        for item in tasks:
            item.is_trashed = True
            item.trashed_at = timestamp

        deliverable_ids = self.db.scalars(
            select(deliverable_wps.c.deliverable_id).where(deliverable_wps.c.wp_id == wp_id)
        ).all()
        deliverables: list[Deliverable] = []
        if deliverable_ids:
            unique_deliverable_ids = list(dict.fromkeys(deliverable_ids))
            deliverables = self.db.scalars(
                select(Deliverable).where(
                    Deliverable.project_id == project_id,
                    Deliverable.id.in_(unique_deliverable_ids),
                    Deliverable.is_trashed.is_(False),
                )
            ).all()
            for item in deliverables:
                item.is_trashed = True
                item.trashed_at = timestamp

        milestone_ids = self.db.scalars(
            select(milestone_wps.c.milestone_id).where(milestone_wps.c.wp_id == wp_id)
        ).all()
        milestones: list[Milestone] = []
        if milestone_ids:
            unique_milestone_ids = list(dict.fromkeys(milestone_ids))
            milestones = self.db.scalars(
                select(Milestone).where(
                    Milestone.project_id == project_id,
                    Milestone.id.in_(unique_milestone_ids),
                    Milestone.is_trashed.is_(False),
                )
            ).all()
            for item in milestones:
                item.is_trashed = True
                item.trashed_at = timestamp

        return {
            "tasks": len(tasks),
            "deliverables": len(deliverables),
            "milestones": len(milestones),
        }

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
            actor_id=self._resolve_actor_member_id(project_id),
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

    def _resolve_actor_member_id(self, project_id: uuid.UUID) -> uuid.UUID | None:
        if not self.actor_user_id:
            return None
        member = self.db.scalar(
            select(TeamMember.id).where(
                TeamMember.project_id == project_id,
                TeamMember.user_account_id == self.actor_user_id,
            )
        )
        return member

    @staticmethod
    def _project_json(project: Project) -> dict[str, Any]:
        return {
            "id": str(project.id),
            "code": project.code,
            "title": project.title,
            "description": project.description,
            "start_date": project.start_date.isoformat(),
            "duration_months": project.duration_months,
            "reporting_dates": project.reporting_dates,
            "baseline_version": project.baseline_version,
            "status": project.status.value if isinstance(project.status, ProjectStatus) else str(project.status),
            "project_mode": project.project_mode,
            "coordinator_partner_id": str(project.coordinator_partner_id) if project.coordinator_partner_id else None,
            "principal_investigator_id": str(project.principal_investigator_id) if project.principal_investigator_id else None,
            "proposal_template_id": str(project.proposal_template_id) if project.proposal_template_id else None,
        }

    @staticmethod
    def _partner_json(partner: PartnerOrganization) -> dict[str, Any]:
        return {
            "id": str(partner.id),
            "project_id": str(partner.project_id),
            "short_name": partner.short_name,
            "legal_name": partner.legal_name,
            "partner_type": partner.partner_type,
            "country": partner.country,
            "expertise": partner.expertise,
        }

    @staticmethod
    def _member_json(member: TeamMember) -> dict[str, Any]:
        return {
            "id": str(member.id),
            "project_id": str(member.project_id),
            "partner_id": str(member.organization_id),
            "user_account_id": str(member.user_account_id) if member.user_account_id else None,
            "full_name": member.full_name,
            "email": member.email,
            "role": member.role,
            "is_active": member.is_active,
        }

    @staticmethod
    def _generate_temporary_password(length: int = 12) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _ensure_project_membership(self, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        existing = self.db.scalar(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        )
        if existing:
            return
        membership = ProjectMembership(project_id=project_id, user_id=user_id, role=ProjectRole.partner_member.value)
        self.db.add(membership)
        self._safe_flush("Project membership creation failed.")

    def _resolve_member_identity(
        self,
        *,
        user_id: uuid.UUID | None,
        full_name: str | None,
        email: str | None,
        create_user_if_missing: bool,
        temporary_password: str | None,
    ) -> tuple[uuid.UUID | None, str, str, str | None]:
        linked_user_id: uuid.UUID | None = None
        normalized_full_name = (full_name or "").strip()
        normalized_email = str(email).strip().lower() if email else ""
        generated_password: str | None = None

        if user_id:
            linked_user = self.db.get(UserAccount, user_id)
            if not linked_user:
                raise NotFoundError("Selected user not found.")
            if not linked_user.is_active:
                raise ValidationError("Selected user is inactive.")
            linked_user_id = linked_user.id
            normalized_full_name = linked_user.display_name
            normalized_email = linked_user.email
            return linked_user_id, normalized_full_name, normalized_email, generated_password

        if not normalized_email:
            raise ValidationError("Email is required when no existing user is selected.")
        if not normalized_full_name:
            raise ValidationError("Full name is required when no existing user is selected.")
        try:
            normalized_email = str(EMAIL_ADAPTER.validate_python(normalized_email))
        except PydanticValidationError as exc:
            raise ValidationError("Invalid email format.") from exc

        existing_user = self.db.scalar(select(UserAccount).where(UserAccount.email == normalized_email))
        if existing_user:
            if not existing_user.is_active:
                raise ValidationError("The selected email belongs to an inactive user.")
            linked_user_id = existing_user.id
            return linked_user_id, normalized_full_name, normalized_email, generated_password

        if create_user_if_missing:
            generated_password = temporary_password.strip() if temporary_password else self._generate_temporary_password()
            if len(generated_password) < 8:
                raise ValidationError("Temporary password must be at least 8 characters.")
            created_user = UserAccount(
                email=normalized_email,
                password_hash=hash_password(generated_password),
                display_name=normalized_full_name,
                platform_role=PlatformRole.user.value,
                is_active=True,
            )
            self.db.add(created_user)
            self._safe_flush("User with this email already exists.")
            linked_user_id = created_user.id

        return linked_user_id, normalized_full_name, normalized_email, generated_password

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
        if hasattr(entity, "start_month"):
            payload["start_month"] = entity.start_month
        if hasattr(entity, "end_month"):
            payload["end_month"] = entity.end_month
        if hasattr(entity, "due_month"):
            payload["due_month"] = entity.due_month
        if hasattr(entity, "execution_status"):
            execution_status = getattr(entity, "execution_status", None)
            payload["execution_status"] = execution_status.value if hasattr(execution_status, "value") else str(execution_status)
        if hasattr(entity, "completed_at"):
            payload["completed_at"] = entity.completed_at.isoformat() if entity.completed_at else None
        if hasattr(entity, "completed_by_member_id"):
            payload["completed_by_member_id"] = str(entity.completed_by_member_id) if entity.completed_by_member_id else None
        if hasattr(entity, "completion_note"):
            payload["completion_note"] = entity.completion_note
        if hasattr(entity, "workflow_status"):
            workflow_status = getattr(entity, "workflow_status", None)
            payload["workflow_status"] = workflow_status.value if hasattr(workflow_status, "value") else str(workflow_status)
        if hasattr(entity, "review_due_month"):
            payload["review_due_month"] = entity.review_due_month
        if hasattr(entity, "review_owner_member_id"):
            payload["review_owner_member_id"] = str(entity.review_owner_member_id) if entity.review_owner_member_id else None
        if hasattr(entity, "wp_id"):
            payload["wp_id"] = str(entity.wp_id) if entity.wp_id else None
        return payload

    @staticmethod
    def _risk_json(entity: ProjectRisk) -> dict[str, Any]:
        return {
            "id": str(entity.id),
            "project_id": str(entity.project_id),
            "code": entity.code,
            "title": entity.title,
            "description": entity.description,
            "mitigation_plan": entity.mitigation_plan,
            "status": entity.status.value if hasattr(entity.status, "value") else str(entity.status),
            "probability": entity.probability.value if hasattr(entity.probability, "value") else str(entity.probability),
            "impact": entity.impact.value if hasattr(entity.impact, "value") else str(entity.impact),
            "due_month": entity.due_month,
            "owner_partner_id": str(entity.owner_partner_id),
            "owner_member_id": str(entity.owner_member_id),
        }
