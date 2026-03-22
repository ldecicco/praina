import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.project import ProjectKind
from app.models.organization import TeamMember
from app.models.project import ProjectStatus
from app.schemas.audit import AuditEventListRead, AuditEventRead
from app.models.work import (
    deliverable_collaborators,
    deliverable_wps,
    milestone_collaborators,
    milestone_wps,
    task_collaborators,
    wp_collaborators,
)
from app.schemas.organization import (
    PartnerCreate,
    PartnerListRead,
    PartnerRead,
    TeamMemberCreate,
    TeamMemberListRead,
    TeamMemberRead,
    PartnerUpdate,
    TeamMemberUpdate,
)
from app.schemas.project import (
    ActivationResultRead,
    MarkAsFundedPayload,
    ProjectCreate,
    ProjectListRead,
    ProjectRead,
    ProjectUpdate,
    ValidationErrorRead,
    ValidationResultRead,
    ValidationWarningRead,
)
from app.schemas.risk import ProjectRiskCreate, ProjectRiskListRead, ProjectRiskRead, ProjectRiskUpdate
from app.schemas.work import (
    AssignmentMatrixRead,
    AssignmentMatrixRowRead,
    AssignmentUpdate,
    DeliverableCreate,
    DeliverableUpdate,
    MilestoneCreate,
    MilestoneUpdate,
    TaskCreate,
    TaskUpdate,
    TrashedWorkEntityListRead,
    TrashedWorkEntityRead,
    WorkEntityListRead,
    WorkEntityRead,
    WorkPackageCreate,
    WorkPackageUpdate,
)
from app.services.onboarding_service import ConflictError, NotFoundError, OnboardingService, ValidationError
from app.services.proposal_service import ProposalService

router = APIRouter()


@router.post("", response_model=ProjectRead)
def create_project(
    payload: ProjectCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRead:
    if current_user.platform_role not in {"super_admin", "project_creator"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super_admin or project_creator can create projects.",
        )
    requested_kind = (payload.project_kind or ProjectKind.funded.value).strip().lower()
    if requested_kind == ProjectKind.teaching.value and not current_user.can_access_teaching:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Teaching.")
    if requested_kind != ProjectKind.teaching.value and not current_user.can_access_research:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Research.")
    service = OnboardingService(db)
    try:
        project = service.create_project(payload, actor_user_id=current_user.id)
        if payload.proposal_template_id:
            proposal_service = ProposalService(db)
            proposal_service.apply_template_to_project(project.id, payload.proposal_template_id)
            project = service.get_project(project.id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _project_read(project)


@router.get("", response_model=ProjectListRead)
def list_projects(
    status_filter: ProjectStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectListRead:
    service = OnboardingService(db)
    items, total = service.list_projects_for_user(
        user_id=current_user.id,
        platform_role=current_user.platform_role,
        can_access_research=current_user.can_access_research,
        can_access_teaching=current_user.can_access_teaching,
        status=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )
    return ProjectListRead(items=[_project_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectRead:
    service = OnboardingService(db)
    try:
        project = service.get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _project_read(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        project = service.update_project(project_id, payload)
        if "proposal_template_id" in payload.model_dump(exclude_unset=True):
            proposal_service = ProposalService(db)
            proposal_service.apply_template_to_project(project_id, payload.proposal_template_id)
            project = service.get_project(project.id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _project_read(project)


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        project = service.archive_project(project_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _project_read(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def hard_delete_project(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        service.hard_delete_project(project_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/{project_id}/partners", response_model=PartnerRead)
def create_partner(
    project_id: uuid.UUID,
    payload: PartnerCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PartnerRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        partner = service.create_partner(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _partner_read(partner)


@router.patch("/{project_id}/partners/{partner_id}", response_model=PartnerRead)
def update_partner(
    project_id: uuid.UUID,
    partner_id: uuid.UUID,
    payload: PartnerUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PartnerRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        partner = service.update_partner(project_id, partner_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _partner_read(partner)


@router.delete("/{project_id}/partners/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_partner(
    project_id: uuid.UUID,
    partner_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        service.delete_partner(project_id, partner_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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


@router.post("/{project_id}/members", response_model=TeamMemberRead)
def create_member(
    project_id: uuid.UUID,
    payload: TeamMemberCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
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


@router.patch("/{project_id}/members/{member_id}", response_model=TeamMemberRead)
def update_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: TeamMemberUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMemberRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        member = service.update_member(project_id, member_id, payload)
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


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        service.delete_member(project_id, member_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{project_id}/members", response_model=TeamMemberListRead)
def list_members(
    project_id: uuid.UUID,
    partner_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TeamMemberListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_members(project_id, partner_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TeamMemberListRead(items=[_member_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/work-packages", response_model=WorkEntityRead)
def create_work_package(
    project_id: uuid.UUID,
    payload: WorkPackageCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
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


@router.patch("/{project_id}/work-packages/{entity_id}", response_model=WorkEntityRead)
def update_work_package(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: WorkPackageUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        wp = service.update_wp(project_id, entity_id, payload)
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


@router.post("/{project_id}/risks", response_model=ProjectRiskRead)
def create_risk(
    project_id: uuid.UUID,
    payload: ProjectRiskCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRiskRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        risk = service.create_risk(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _risk_read(risk)


@router.patch("/{project_id}/risks/{risk_id}", response_model=ProjectRiskRead)
def update_risk(
    project_id: uuid.UUID,
    risk_id: uuid.UUID,
    payload: ProjectRiskUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRiskRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        risk = service.update_risk(project_id, risk_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _risk_read(risk)


@router.get("/{project_id}/risks", response_model=ProjectRiskListRead)
def list_risks(
    project_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    owner_partner_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ProjectRiskListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_risks(project_id, status_filter, owner_partner_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProjectRiskListRead(items=[_risk_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.get("/{project_id}/activity", response_model=AuditEventListRead)
def list_activity(
    project_id: uuid.UUID,
    event_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AuditEventListRead:
    service = OnboardingService(db)
    try:
        items, total = service.list_audit_events(project_id, event_type, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AuditEventListRead(items=[_audit_read(item, service) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/tasks", response_model=WorkEntityRead)
def create_task(
    project_id: uuid.UUID,
    payload: TaskCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
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


@router.patch("/{project_id}/tasks/{entity_id}", response_model=WorkEntityRead)
def update_task(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: TaskUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        task = service.update_task(project_id, entity_id, payload)
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
def create_milestone(
    project_id: uuid.UUID,
    payload: MilestoneCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
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
    wp_ids = service.get_related_wps(milestone_wps, "milestone_id", milestone.id)
    return _work_read(milestone, collaborators, wp_ids)


@router.patch("/{project_id}/milestones/{entity_id}", response_model=WorkEntityRead)
def update_milestone(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: MilestoneUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        milestone = service.update_milestone(project_id, entity_id, payload)
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
    wp_ids = service.get_related_wps(milestone_wps, "milestone_id", milestone.id)
    return _work_read(milestone, collaborators, wp_ids)


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
        items=[
            _work_read(
                item,
                service.get_collaborators(milestone_collaborators, "milestone_id", item.id),
                service.get_related_wps(milestone_wps, "milestone_id", item.id),
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/deliverables", response_model=WorkEntityRead)
def create_deliverable(
    project_id: uuid.UUID,
    payload: DeliverableCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
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
    wp_ids = service.get_related_wps(deliverable_wps, "deliverable_id", deliverable.id)
    return _work_read(deliverable, collaborators, wp_ids)


@router.patch("/{project_id}/deliverables/{entity_id}", response_model=WorkEntityRead)
def update_deliverable(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: DeliverableUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        deliverable = service.update_deliverable(project_id, entity_id, payload)
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
    wp_ids = service.get_related_wps(deliverable_wps, "deliverable_id", deliverable.id)
    return _work_read(deliverable, collaborators, wp_ids)


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
        items=[
            _work_read(
                item,
                service.get_collaborators(deliverable_collaborators, "deliverable_id", item.id),
                service.get_related_wps(deliverable_wps, "deliverable_id", item.id),
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/work-packages/{entity_id}/trash", response_model=WorkEntityRead)
def trash_work_package(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "work_package", entity_id, trashed=True, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/work-packages/{entity_id}/restore", response_model=WorkEntityRead)
def restore_work_package(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "work_package", entity_id, trashed=False, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/tasks/{entity_id}/trash", response_model=WorkEntityRead)
def trash_task(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "task", entity_id, trashed=True, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/tasks/{entity_id}/restore", response_model=WorkEntityRead)
def restore_task(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "task", entity_id, trashed=False, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/milestones/{entity_id}/trash", response_model=WorkEntityRead)
def trash_milestone(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "milestone", entity_id, trashed=True, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/milestones/{entity_id}/restore", response_model=WorkEntityRead)
def restore_milestone(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "milestone", entity_id, trashed=False, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/deliverables/{entity_id}/trash", response_model=WorkEntityRead)
def trash_deliverable(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "deliverable", entity_id, trashed=True, db=db, actor_user_id=current_user.id)


@router.post("/{project_id}/deliverables/{entity_id}/restore", response_model=WorkEntityRead)
def restore_deliverable(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _set_trashed_state(project_id, "deliverable", entity_id, trashed=False, db=db, actor_user_id=current_user.id)


@router.get("/{project_id}/trash", response_model=TrashedWorkEntityListRead)
def list_trashed_entities(
    project_id: uuid.UUID,
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> TrashedWorkEntityListRead:
    service = OnboardingService(db)
    try:
        rows, total = service.list_trashed_entities(project_id, search, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    collaborator_map = {
        "work_package": (wp_collaborators, "wp_id"),
        "task": (task_collaborators, "task_id"),
        "milestone": (milestone_collaborators, "milestone_id"),
        "deliverable": (deliverable_collaborators, "deliverable_id"),
    }
    rendered: list[TrashedWorkEntityRead] = []
    for entity_type, entity in rows:
        table, foreign_key = collaborator_map[entity_type]
        collaborators = service.get_collaborators(table, foreign_key, entity.id)
        wp_ids: list[uuid.UUID] = []
        if entity_type == "deliverable":
            wp_ids = service.get_related_wps(deliverable_wps, "deliverable_id", entity.id)
        elif entity_type == "milestone":
            wp_ids = service.get_related_wps(milestone_wps, "milestone_id", entity.id)
        rendered.append(TrashedWorkEntityRead(entity_type=entity_type, entity=_work_read(entity, collaborators, wp_ids)))

    return TrashedWorkEntityListRead(items=rendered, page=page, page_size=page_size, total=total)


@router.patch("/{project_id}/work-packages/{entity_id}/assignment", response_model=WorkEntityRead)
def update_work_package_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "work_package", entity_id, payload, db, actor_user_id=current_user.id)


@router.patch("/{project_id}/tasks/{entity_id}/assignment", response_model=WorkEntityRead)
def update_task_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "task", entity_id, payload, db, actor_user_id=current_user.id)


@router.patch("/{project_id}/milestones/{entity_id}/assignment", response_model=WorkEntityRead)
def update_milestone_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "milestone", entity_id, payload, db, actor_user_id=current_user.id)


@router.patch("/{project_id}/deliverables/{entity_id}/assignment", response_model=WorkEntityRead)
def update_deliverable_assignment(
    project_id: uuid.UUID,
    entity_id: uuid.UUID,
    payload: AssignmentUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkEntityRead:
    return _update_assignment(project_id, "deliverable", entity_id, payload, db, actor_user_id=current_user.id)


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
    from app.agents.validation_agent import ValidationAgent

    try:
        report = ValidationAgent().run(project_id, db)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    errors = [
        ValidationErrorRead(
            entity_type=i.entity_type, entity_id=i.entity_id, code=i.code, message=i.message
        )
        for i in report.errors
    ]
    warnings = [
        ValidationWarningRead(
            entity_type=i.entity_type, entity_id=i.entity_id, code=i.code,
            field=i.field, message=i.message,
        )
        for i in report.warnings
    ]
    return ValidationResultRead(valid=report.is_valid, errors=errors, warnings=warnings)


@router.post("/{project_id}/activate", response_model=ActivationResultRead)
def activate_project(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivationResultRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
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


@router.post("/{project_id}/mark-as-funded", response_model=ActivationResultRead)
def mark_as_funded(
    project_id: uuid.UUID,
    payload: MarkAsFundedPayload,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivationResultRead:
    service = OnboardingService(db, actor_user_id=current_user.id)
    try:
        project, event = service.mark_as_funded(
            project_id=project_id,
            start_date=payload.start_date,
            duration_months=payload.duration_months,
            reporting_dates=payload.reporting_dates,
        )
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
    actor_user_id: uuid.UUID | None = None,
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=actor_user_id)
    try:
        entity = service.update_assignment(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            leader_organization_id=payload.leader_organization_id,
            responsible_person_id=payload.responsible_person_id,
            collaborating_partner_ids=payload.collaborating_partner_ids,
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
    wp_ids: list[uuid.UUID] = []
    if entity_type == "deliverable":
        wp_ids = service.get_related_wps(deliverable_wps, "deliverable_id", entity.id)
    elif entity_type == "milestone":
        wp_ids = service.get_related_wps(milestone_wps, "milestone_id", entity.id)
    return _work_read(entity, collaborators, wp_ids)


def _set_trashed_state(
    project_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    *,
    trashed: bool,
    db: Session,
    actor_user_id: uuid.UUID | None = None,
) -> WorkEntityRead:
    service = OnboardingService(db, actor_user_id=actor_user_id)
    try:
        entity = (
            service.trash_entity(project_id, entity_type, entity_id)
            if trashed
            else service.restore_entity(project_id, entity_type, entity_id)
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    collaborator_map = {
        "work_package": (wp_collaborators, "wp_id"),
        "task": (task_collaborators, "task_id"),
        "milestone": (milestone_collaborators, "milestone_id"),
        "deliverable": (deliverable_collaborators, "deliverable_id"),
    }
    table, foreign_key = collaborator_map[entity_type]
    collaborators = service.get_collaborators(table, foreign_key, entity.id)
    wp_ids: list[uuid.UUID] = []
    if entity_type == "deliverable":
        wp_ids = service.get_related_wps(deliverable_wps, "deliverable_id", entity.id)
    elif entity_type == "milestone":
        wp_ids = service.get_related_wps(milestone_wps, "milestone_id", entity.id)
    return _work_read(entity, collaborators, wp_ids)


def _project_read(project) -> ProjectRead:
    return ProjectRead(
        id=str(project.id),
        code=project.code,
        title=project.title,
        description=project.description,
        start_date=project.start_date,
        duration_months=project.duration_months,
        reporting_dates=project.reporting_dates,
        baseline_version=project.baseline_version,
        status=project.status.value if isinstance(project.status, ProjectStatus) else str(project.status),
        language=getattr(project, "language", "en_GB") or "en_GB",
        project_mode=getattr(project, "project_mode", "execution") or "execution",
        project_kind=getattr(project, "project_kind", "funded") or "funded",
        coordinator_partner_id=str(project.coordinator_partner_id) if project.coordinator_partner_id else None,
        principal_investigator_id=str(project.principal_investigator_id) if project.principal_investigator_id else None,
        proposal_template_id=str(project.proposal_template_id) if getattr(project, "proposal_template_id", None) else None,
    )


def _partner_read(partner) -> PartnerRead:
    return PartnerRead(
        id=str(partner.id),
        project_id=str(partner.project_id),
        short_name=partner.short_name,
        legal_name=partner.legal_name,
        partner_type=getattr(partner, "partner_type", "beneficiary") or "beneficiary",
        country=getattr(partner, "country", None),
        expertise=getattr(partner, "expertise", None),
    )


def _member_read(member) -> TeamMemberRead:
    return TeamMemberRead(
        id=str(member.id),
        project_id=str(member.project_id),
        partner_id=str(member.organization_id),
        user_account_id=str(member.user_account_id) if member.user_account_id else None,
        full_name=member.full_name,
        email=member.email,
        role=member.role,
        is_active=member.is_active,
        temporary_password=getattr(member, "temporary_password", None),
    )


def _work_read(entity, collaborators: list[uuid.UUID], wp_ids: list[uuid.UUID] | None = None) -> WorkEntityRead:
    related_wp_ids = wp_ids or []
    if not related_wp_ids and hasattr(entity, "wp_id") and entity.wp_id:
        related_wp_ids = [entity.wp_id]
    wp_id = str(related_wp_ids[0]) if related_wp_ids else None
    return WorkEntityRead(
        id=str(entity.id),
        project_id=str(entity.project_id),
        code=entity.code,
        title=entity.title,
        description=entity.description,
        wp_id=wp_id,
        wp_ids=[str(item) for item in related_wp_ids],
        start_month=entity.start_month if hasattr(entity, "start_month") else None,
        end_month=entity.end_month if hasattr(entity, "end_month") else None,
        due_month=entity.due_month if hasattr(entity, "due_month") else None,
        execution_status=(
            entity.execution_status.value if hasattr(getattr(entity, "execution_status", None), "value") else getattr(entity, "execution_status", None)
        ),
        completed_at=getattr(entity, "completed_at", None),
        completed_by_member_id=str(entity.completed_by_member_id) if getattr(entity, "completed_by_member_id", None) else None,
        completion_note=getattr(entity, "completion_note", None),
        workflow_status=(
            entity.workflow_status.value if hasattr(getattr(entity, "workflow_status", None), "value") else getattr(entity, "workflow_status", None)
        ),
        review_due_month=getattr(entity, "review_due_month", None),
        review_owner_member_id=str(entity.review_owner_member_id) if getattr(entity, "review_owner_member_id", None) else None,
        is_trashed=bool(getattr(entity, "is_trashed", False)),
        trashed_at=getattr(entity, "trashed_at", None),
        leader_organization_id=str(entity.leader_organization_id),
        responsible_person_id=str(entity.responsible_person_id),
        collaborating_partner_ids=[str(partner_id) for partner_id in collaborators],
    )


def _audit_read(event, service: OnboardingService) -> AuditEventRead:
    actor_name = None
    if event.actor_id:
        actor = service.db.get(TeamMember, event.actor_id)
        actor_name = actor.full_name if actor else None
    return AuditEventRead(
        id=str(event.id),
        project_id=str(event.project_id),
        actor_id=str(event.actor_id) if event.actor_id else None,
        actor_name=actor_name,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        reason=event.reason,
        before_json=event.before_json,
        after_json=event.after_json,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _risk_read(risk) -> ProjectRiskRead:
    return ProjectRiskRead(
        id=str(risk.id),
        project_id=str(risk.project_id),
        code=risk.code,
        title=risk.title,
        description=risk.description,
        mitigation_plan=risk.mitigation_plan,
        status=risk.status.value if hasattr(risk.status, "value") else str(risk.status),
        probability=risk.probability.value if hasattr(risk.probability, "value") else str(risk.probability),
        impact=risk.impact.value if hasattr(risk.impact, "value") else str(risk.impact),
        due_month=risk.due_month,
        owner_partner_id=str(risk.owner_partner_id),
        owner_member_id=str(risk.owner_member_id),
        created_at=risk.created_at,
        updated_at=risk.updated_at,
    )
