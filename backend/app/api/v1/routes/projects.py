import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.project import ProjectStatus
from app.models.work import deliverable_collaborators, milestone_collaborators, task_collaborators, wp_collaborators
from app.schemas.organization import (
    PartnerCreate,
    PartnerListRead,
    PartnerRead,
    TeamCreate,
    TeamListRead,
    TeamMemberCreate,
    TeamMemberListRead,
    TeamMemberRead,
    TeamRead,
)
from app.schemas.project import (
    ActivationResultRead,
    ProjectCreate,
    ProjectListRead,
    ProjectRead,
    ValidationErrorRead,
    ValidationResultRead,
)
from app.schemas.work import (
    AssignmentMatrixRead,
    AssignmentMatrixRowRead,
    AssignmentUpdate,
    DeliverableCreate,
    MilestoneCreate,
    TaskCreate,
    WorkEntityListRead,
    WorkEntityRead,
    WorkPackageCreate,
)
from app.services.onboarding_service import ConflictError, NotFoundError, OnboardingService, ValidationError

router = APIRouter()


@router.post("", response_model=ProjectRead)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectRead:
    service = OnboardingService(db)
    try:
        project = service.create_project(payload)
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _project_read(project)


@router.get("", response_model=ProjectListRead)
def list_projects(
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ProjectListRead:
    service = OnboardingService(db)
    items, total = service.list_projects(status_filter, search, page, page_size)
    return ProjectListRead(items=[_project_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectRead:
    service = OnboardingService(db)
    try:
        project = service.get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _project_read(project)


@router.post("/{project_id}/partners", response_model=PartnerRead)
def create_partner(project_id: uuid.UUID, payload: PartnerCreate, db: Session = Depends(get_db)) -> PartnerRead:
    service = OnboardingService(db)
    try:
        partner = service.create_partner(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _partner_read(partner)


@router.get("/{project_id}/partners", response_model=PartnerListRead)
def list_partners(
    project_id: uuid.UUID,
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PartnerListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_partners(project_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PartnerListRead(items=[_partner_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/teams", response_model=TeamRead)
def create_team(project_id: uuid.UUID, payload: TeamCreate, db: Session = Depends(get_db)) -> TeamRead:
    service = OnboardingService(db)
    try:
        team = service.create_team(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _team_read(team)


@router.get("/{project_id}/teams", response_model=TeamListRead)
def list_teams(
    project_id: uuid.UUID,
    organization_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TeamListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_teams(project_id, organization_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TeamListRead(items=[_team_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/members", response_model=TeamMemberRead)
def create_member(project_id: uuid.UUID, payload: TeamMemberCreate, db: Session = Depends(get_db)) -> TeamMemberRead:
    service = OnboardingService(db)
    try:
        member = service.create_member(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _member_read(member)


@router.get("/{project_id}/members", response_model=TeamMemberListRead)
def list_members(
    project_id: uuid.UUID,
    organization_id: uuid.UUID | None = Query(default=None),
    team_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TeamMemberListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_members(project_id, organization_id, team_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TeamMemberListRead(items=[_member_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/work-packages", response_model=WorkEntityRead)
def create_work_package(project_id: uuid.UUID, payload: WorkPackageCreate, db: Session = Depends(get_db)) -> WorkEntityRead:
    service = OnboardingService(db)
    try:
        wp = service.create_wp(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    collaborators = service.get_collaborators(wp_collaborators, "wp_id", wp.id)
    return _work_read(wp, collaborators)


@router.get("/{project_id}/work-packages", response_model=WorkEntityListRead)
def list_work_packages(
    project_id: uuid.UUID,
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> WorkEntityListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_work_packages(project_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WorkEntityListRead(
        items=[_work_read(item, service.get_collaborators(wp_collaborators, "wp_id", item.id)) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/tasks", response_model=WorkEntityRead)
def create_task(project_id: uuid.UUID, payload: TaskCreate, db: Session = Depends(get_db)) -> WorkEntityRead:
    service = OnboardingService(db)
    try:
        task = service.create_task(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    collaborators = service.get_collaborators(task_collaborators, "task_id", task.id)
    return _work_read(task, collaborators)


@router.get("/{project_id}/tasks", response_model=WorkEntityListRead)
def list_tasks(
    project_id: uuid.UUID,
    wp_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> WorkEntityListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_tasks(project_id, wp_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WorkEntityListRead(
        items=[_work_read(item, service.get_collaborators(task_collaborators, "task_id", item.id)) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/milestones", response_model=WorkEntityRead)
def create_milestone(project_id: uuid.UUID, payload: MilestoneCreate, db: Session = Depends(get_db)) -> WorkEntityRead:
    service = OnboardingService(db)
    try:
        milestone = service.create_milestone(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    collaborators = service.get_collaborators(milestone_collaborators, "milestone_id", milestone.id)
    return _work_read(milestone, collaborators)


@router.get("/{project_id}/milestones", response_model=WorkEntityListRead)
def list_milestones(
    project_id: uuid.UUID,
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> WorkEntityListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_milestones(project_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WorkEntityListRead(
        items=[_work_read(item, service.get_collaborators(milestone_collaborators, "milestone_id", item.id)) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/deliverables", response_model=WorkEntityRead)
def create_deliverable(project_id: uuid.UUID, payload: DeliverableCreate, db: Session = Depends(get_db)) -> WorkEntityRead:
    service = OnboardingService(db)
    try:
        deliverable = service.create_deliverable(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    collaborators = service.get_collaborators(deliverable_collaborators, "deliverable_id", deliverable.id)
    return _work_read(deliverable, collaborators)


@router.get("/{project_id}/deliverables", response_model=WorkEntityListRead)
def list_deliverables(
    project_id: uuid.UUID,
    wp_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> WorkEntityListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_deliverables(project_id, wp_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WorkEntityListRead(
        items=[_work_read(item, service.get_collaborators(deliverable_collaborators, "deliverable_id", item.id)) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.patch("/{project_id}/work-packages/{entity_id}/assignment", response_model=WorkEntityRead)
def update_work_package_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "work_package", entity_id, payload, db)


@router.patch("/{project_id}/tasks/{entity_id}/assignment", response_model=WorkEntityRead)
def update_task_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "task", entity_id, payload, db)


@router.patch("/{project_id}/milestones/{entity_id}/assignment", response_model=WorkEntityRead)
def update_milestone_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "milestone", entity_id, payload, db)


@router.patch("/{project_id}/deliverables/{entity_id}/assignment", response_model=WorkEntityRead)
def update_deliverable_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "deliverable", entity_id, payload, db)


@router.get("/{project_id}/assignment-matrix", response_model=AssignmentMatrixRead)
def get_assignment_matrix(
    project_id: uuid.UUID,
    entity_type: str | None = Query(default=None),
    wp_id: uuid.UUID | None = Query(default=None),
    leader_organization_id: uuid.UUID | None = Query(default=None),
    responsible_person_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AssignmentMatrixRead:
    service = OnboardingService(db)
    try:
        items, total = service.get_assignment_matrix(
            project_id=project_id,
            entity_type=entity_type,
            wp_id=wp_id,
            leader_organization_id=leader_organization_id,
            responsible_person_id=responsible_person_id,
            page=page,
            page_size=page_size,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return AssignmentMatrixRead(
        items=[AssignmentMatrixRowRead(**item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/validate", response_model=ValidationResultRead)
def validate_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ValidationResultRead:
    service = OnboardingService(db)
    try:
        errors = service.validate_project(project_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ValidationResultRead(valid=len(errors) == 0, errors=[ValidationErrorRead(**error) for error in errors], warnings=[])


@router.post("/{project_id}/activate", response_model=ActivationResultRead)
def activate_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ActivationResultRead:
    service = OnboardingService(db)
    try:
        project, event = service.activate_project(project_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActivationResultRead(
        project_id=str(project.id),
        status=project.status.value if isinstance(project.status, ProjectStatus) else str(project.status),
        baseline_version=project.baseline_version,
        audit_event_id=str(event.id),
    )


def _update_assignment(
    project_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    db: Session,
) -> WorkEntityRead:
    service = OnboardingService(db)
    try:
        entity = service.update_assignment(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            leader_organization_id=payload.leader_organization_id,
            responsible_person_id=payload.responsible_person_id,
            collaborating_team_ids=payload.collaborating_team_ids,
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    collaborator_map = {
        "work_package": (wp_collaborators, "wp_id"),
        "task": (task_collaborators, "task_id"),
        "milestone": (milestone_collaborators, "milestone_id"),
        "deliverable": (deliverable_collaborators, "deliverable_id"),
    }
    table, foreign_key = collaborator_map[entity_type]
    collaborators = service.get_collaborators(table, foreign_key, entity.id)
    return _work_read(entity, collaborators)


def _project_read(project) -> ProjectRead:
    return ProjectRead(
        id=str(project.id),
        code=project.code,
        title=project.title,
        description=project.description,
        baseline_version=project.baseline_version,
        status=project.status.value if isinstance(project.status, ProjectStatus) else str(project.status),
    )


def _partner_read(partner) -> PartnerRead:
    return PartnerRead(
        id=str(partner.id),
        project_id=str(partner.project_id),
        short_name=partner.short_name,
        legal_name=partner.legal_name,
    )


def _team_read(team) -> TeamRead:
    return TeamRead(
        id=str(team.id),
        project_id=str(team.project_id),
        organization_id=str(team.organization_id),
        name=team.name,
    )


def _member_read(member) -> TeamMemberRead:
    return TeamMemberRead(
        id=str(member.id),
        project_id=str(member.project_id),
        organization_id=str(member.organization_id),
        team_id=str(member.team_id),
        full_name=member.full_name,
        email=member.email,
        role=member.role,
        is_active=member.is_active,
    )


def _work_read(entity, collaborators: list[uuid.UUID]) -> WorkEntityRead:
    wp_id = str(entity.wp_id) if hasattr(entity, "wp_id") and entity.wp_id else None
    return WorkEntityRead(
        id=str(entity.id),
        project_id=str(entity.project_id),
        code=entity.code,
        title=entity.title,
        description=entity.description,
        wp_id=wp_id,
        leader_organization_id=str(entity.leader_organization_id),
        responsible_person_id=str(entity.responsible_person_id),
        collaborating_team_ids=[str(team_id) for team_id in collaborators],
    )

