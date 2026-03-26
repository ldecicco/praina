from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.research import BibliographyReference
from app.models.course import Course
from app.schemas.teaching import (
    TeachingArtifactListRead,
    TeachingBackgroundMaterialListRead,
    TeachingProgressReportListRead,
    TeachingProjectArtifactCreate,
    TeachingProjectArtifactRead,
    TeachingProjectArtifactUpdate,
    TeachingProjectAssessmentRead,
    TeachingProjectAssessmentUpsert,
    TeachingProjectBackgroundMaterialCreate,
    TeachingProjectBackgroundMaterialRead,
    TeachingProjectBackgroundMaterialUpdate,
    TeachingProjectBlockerCreate,
    TeachingProjectBlockerRead,
    TeachingProjectBlockerUpdate,
    TeachingProjectProfileRead,
    TeachingProjectProfileUpdate,
    TeachingProjectStudentCreate,
    TeachingProjectStudentRead,
    TeachingProjectStudentUpdate,
    TeachingProjectMilestoneCreate,
    TeachingProjectMilestoneRead,
    TeachingProjectMilestoneUpdate,
    TeachingProgressReportCreate,
    TeachingProgressReportRead,
    TeachingProgressReportUpdate,
    TeachingStudentListRead,
    TeachingWorkspaceRead,
    TeachingMilestoneListRead,
    TeachingBlockerListRead,
)
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.teaching_service import TeachingService


def require_teaching_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not current_user.can_access_teaching:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Teaching.")


router = APIRouter(dependencies=[Depends(require_teaching_access)])


@router.get("/{project_id}/teaching", response_model=TeachingWorkspaceRead)
def get_teaching_workspace(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingWorkspaceRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        workspace = svc.get_workspace(project_id)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return TeachingWorkspaceRead(
        profile=_profile_read(db, workspace["profile"]),
        students=[_student_read(item) for item in workspace["students"]],
        artifacts=[_artifact_read(item) for item in workspace["artifacts"]],
        background_materials=[_background_material_read(db, item) for item in workspace["background_materials"]],
        progress_reports=[_report_read(svc, item) for item in workspace["progress_reports"]],
        milestones=[_milestone_read(item) for item in workspace["milestones"]],
        blockers=[_blocker_read(item) for item in workspace["blockers"]],
        assessment=_assessment_read(workspace["assessment"]) if workspace["assessment"] else None,
    )


@router.put("/{project_id}/teaching/profile", response_model=TeachingProjectProfileRead)
def update_teaching_profile(
    project_id: uuid.UUID,
    payload: TeachingProjectProfileUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectProfileRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_profile(project_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _profile_read(db, item)


@router.get("/{project_id}/teaching/students", response_model=TeachingStudentListRead)
def list_teaching_students(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingStudentListRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        items, total = svc.list_students(project_id, page=page, page_size=page_size)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return TeachingStudentListRead(items=[_student_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/teaching/students", response_model=TeachingProjectStudentRead, status_code=status.HTTP_201_CREATED)
def create_teaching_student(
    project_id: uuid.UUID,
    payload: TeachingProjectStudentCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectStudentRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.create_student(project_id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _student_read(item)


@router.patch("/{project_id}/teaching/students/{student_id}", response_model=TeachingProjectStudentRead)
def update_teaching_student(
    project_id: uuid.UUID,
    student_id: uuid.UUID,
    payload: TeachingProjectStudentUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectStudentRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_student(project_id, student_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _student_read(item)


@router.delete("/{project_id}/teaching/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teaching_student(
    project_id: uuid.UUID,
    student_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        svc.delete_student(project_id, student_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{project_id}/teaching/artifacts", response_model=TeachingArtifactListRead)
def list_teaching_artifacts(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingArtifactListRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        items, total = svc.list_artifacts(project_id, page=page, page_size=page_size)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return TeachingArtifactListRead(items=[_artifact_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/teaching/artifacts", response_model=TeachingProjectArtifactRead, status_code=status.HTTP_201_CREATED)
def create_teaching_artifact(
    project_id: uuid.UUID,
    payload: TeachingProjectArtifactCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectArtifactRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.create_artifact(project_id, **payload.model_dump())
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _artifact_read(item)


@router.patch("/{project_id}/teaching/artifacts/{artifact_id}", response_model=TeachingProjectArtifactRead)
def update_teaching_artifact(
    project_id: uuid.UUID,
    artifact_id: uuid.UUID,
    payload: TeachingProjectArtifactUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectArtifactRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_artifact(project_id, artifact_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _artifact_read(item)


@router.delete("/{project_id}/teaching/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teaching_artifact(
    project_id: uuid.UUID,
    artifact_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        svc.delete_artifact(project_id, artifact_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{project_id}/teaching/background-materials", response_model=TeachingBackgroundMaterialListRead)
def list_teaching_background_materials(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingBackgroundMaterialListRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        items, total = svc.list_background_materials(project_id, page=page, page_size=page_size)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return TeachingBackgroundMaterialListRead(
        items=[_background_material_read(db, item) for item in items], page=page, page_size=page_size, total=total
    )


@router.post(
    "/{project_id}/teaching/background-materials",
    response_model=TeachingProjectBackgroundMaterialRead,
    status_code=status.HTTP_201_CREATED,
)
def create_teaching_background_material(
    project_id: uuid.UUID,
    payload: TeachingProjectBackgroundMaterialCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectBackgroundMaterialRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.create_background_material(project_id, **payload.model_dump())
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _background_material_read(db, item)


@router.patch(
    "/{project_id}/teaching/background-materials/{material_id}",
    response_model=TeachingProjectBackgroundMaterialRead,
)
def update_teaching_background_material(
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    payload: TeachingProjectBackgroundMaterialUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectBackgroundMaterialRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_background_material(project_id, material_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _background_material_read(db, item)


@router.delete("/{project_id}/teaching/background-materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teaching_background_material(
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        svc.delete_background_material(project_id, material_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{project_id}/teaching/progress-reports", response_model=TeachingProgressReportListRead)
def list_teaching_progress_reports(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProgressReportListRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        items, total = svc.list_progress_reports(project_id, page=page, page_size=page_size)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return TeachingProgressReportListRead(items=[_report_read(svc, item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/teaching/progress-reports", response_model=TeachingProgressReportRead, status_code=status.HTTP_201_CREATED)
def create_teaching_progress_report(
    project_id: uuid.UUID,
    payload: TeachingProgressReportCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProgressReportRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.create_progress_report(project_id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _report_read(svc, item)


@router.patch("/{project_id}/teaching/progress-reports/{report_id}", response_model=TeachingProgressReportRead)
def update_teaching_progress_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    payload: TeachingProgressReportUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProgressReportRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_progress_report(project_id, report_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _report_read(svc, item)


@router.delete("/{project_id}/teaching/progress-reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teaching_progress_report(
    project_id: uuid.UUID,
    report_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        svc.delete_progress_report(project_id, report_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{project_id}/teaching/milestones", response_model=TeachingMilestoneListRead)
def list_teaching_milestones(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingMilestoneListRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        items, total = svc.list_milestones(project_id, page=page, page_size=page_size)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return TeachingMilestoneListRead(items=[_milestone_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/teaching/milestones", response_model=TeachingProjectMilestoneRead, status_code=status.HTTP_201_CREATED)
def create_teaching_milestone(
    project_id: uuid.UUID,
    payload: TeachingProjectMilestoneCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectMilestoneRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.create_milestone(project_id, **payload.model_dump())
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _milestone_read(item)


@router.patch("/{project_id}/teaching/milestones/{milestone_id}", response_model=TeachingProjectMilestoneRead)
def update_teaching_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: TeachingProjectMilestoneUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectMilestoneRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_milestone(project_id, milestone_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _milestone_read(item)


@router.delete("/{project_id}/teaching/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teaching_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        svc.delete_milestone(project_id, milestone_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/{project_id}/teaching/blockers", response_model=TeachingBlockerListRead)
def list_teaching_blockers(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingBlockerListRead:
    svc = TeachingService(db)
    _require_teaching_viewer(svc, project_id, current_user)
    try:
        items, total = svc.list_blockers(project_id, page=page, page_size=page_size)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return TeachingBlockerListRead(items=[_blocker_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/teaching/blockers", response_model=TeachingProjectBlockerRead, status_code=status.HTTP_201_CREATED)
def create_teaching_blocker(
    project_id: uuid.UUID,
    payload: TeachingProjectBlockerCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectBlockerRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.create_blocker(project_id, **payload.model_dump())
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _blocker_read(item)


@router.patch("/{project_id}/teaching/blockers/{blocker_id}", response_model=TeachingProjectBlockerRead)
def update_teaching_blocker(
    project_id: uuid.UUID,
    blocker_id: uuid.UUID,
    payload: TeachingProjectBlockerUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectBlockerRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.update_blocker(project_id, blocker_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _blocker_read(item)


@router.delete("/{project_id}/teaching/blockers/{blocker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teaching_blocker(
    project_id: uuid.UUID,
    blocker_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        svc.delete_blocker(project_id, blocker_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.put("/{project_id}/teaching/assessment", response_model=TeachingProjectAssessmentRead)
def upsert_teaching_assessment(
    project_id: uuid.UUID,
    payload: TeachingProjectAssessmentUpsert,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeachingProjectAssessmentRead:
    svc = TeachingService(db)
    _require_teaching_manager(svc, project_id, current_user)
    try:
        item = svc.upsert_assessment(project_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _assessment_read(item)


def _require_teaching_manager(svc: TeachingService, project_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_manage_project(project_id, current_user.id, current_user.platform_role)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the course teacher or a teaching assistant can manage this project.")


def _require_teaching_viewer(svc: TeachingService, project_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_manage_project(project_id, current_user.id, current_user.platform_role)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the course teacher or a teaching assistant can access this project.")


def _profile_read(db: Session, item) -> TeachingProjectProfileRead:
    course = db.get(Course, item.course_id) if item.course_id else None
    responsible_user = db.get(UserAccount, item.responsible_user_id) if item.responsible_user_id else None
    return TeachingProjectProfileRead(
        id=str(item.id),
        project_id=str(item.project_id),
        course_id=str(item.course_id) if item.course_id else None,
        course_code=course.code if course else None,
        course_title=course.title if course else None,
        academic_year=item.academic_year,
        term=item.term,
        functional_objectives_markdown=item.functional_objectives_markdown,
        specifications_markdown=item.specifications_markdown,
        responsible_user_id=str(item.responsible_user_id) if item.responsible_user_id else None,
        responsible_user=(
            {
                "user_id": str(responsible_user.id),
                "display_name": responsible_user.display_name,
                "email": responsible_user.email,
            }
            if responsible_user
            else None
        ),
        status=item.status.value,
        health=item.health.value,
        reporting_cadence_days=item.reporting_cadence_days,
        final_grade=item.final_grade,
        finalized_at=item.finalized_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _student_read(item) -> TeachingProjectStudentRead:
    return TeachingProjectStudentRead(
        id=str(item.id),
        project_id=str(item.project_id),
        full_name=item.full_name,
        email=item.email,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _artifact_read(item) -> TeachingProjectArtifactRead:
    return TeachingProjectArtifactRead(
        id=str(item.id),
        project_id=str(item.project_id),
        artifact_type=item.artifact_type.value,
        label=item.label,
        required=item.required,
        status=item.status.value,
        document_key=str(item.document_key) if item.document_key else None,
        external_url=item.external_url,
        notes=item.notes,
        submitted_at=item.submitted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _background_material_read(db: Session, item) -> TeachingProjectBackgroundMaterialRead:
    bibliography = db.get(BibliographyReference, item.bibliography_reference_id) if item.bibliography_reference_id else None
    return TeachingProjectBackgroundMaterialRead(
        id=str(item.id),
        project_id=str(item.project_id),
        material_type=item.material_type,
        title=item.title,
        bibliography_reference_id=str(item.bibliography_reference_id) if item.bibliography_reference_id else None,
        bibliography_title=bibliography.title if bibliography else None,
        bibliography_url=bibliography.url if bibliography else None,
        bibliography_attachment_filename=bibliography.attachment_filename if bibliography else None,
        document_key=str(item.document_key) if item.document_key else None,
        external_url=item.external_url,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _report_read(svc: TeachingService, item) -> TeachingProgressReportRead:
    return TeachingProgressReportRead(
        id=str(item.id),
        project_id=str(item.project_id),
        report_date=item.report_date,
        meeting_date=item.meeting_date,
        work_done_markdown=item.work_done_markdown,
        next_steps_markdown=item.next_steps_markdown,
        blockers=[_blocker_read(blocker) for blocker in svc.list_blockers_for_report(item.project_id, item.id)],
        supervisor_feedback_markdown=item.supervisor_feedback_markdown,
        attachment_document_keys=list(item.attachment_document_keys or []),
        transcript_document_keys=list(item.transcript_document_keys or []),
        submitted_at=item.submitted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _milestone_read(item) -> TeachingProjectMilestoneRead:
    return TeachingProjectMilestoneRead(
        id=str(item.id),
        project_id=str(item.project_id),
        kind=item.kind,
        label=item.label,
        due_at=item.due_at,
        completed_at=item.completed_at,
        status=item.status.value,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _assessment_read(item) -> TeachingProjectAssessmentRead:
    return TeachingProjectAssessmentRead(
        id=str(item.id),
        project_id=str(item.project_id),
        grade=item.grade,
        strengths_markdown=item.strengths_markdown,
        weaknesses_markdown=item.weaknesses_markdown,
        grading_rationale_markdown=item.grading_rationale_markdown,
        grader_user_id=str(item.grader_user_id) if item.grader_user_id else None,
        graded_at=item.graded_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _blocker_read(item) -> TeachingProjectBlockerRead:
    return TeachingProjectBlockerRead(
        id=str(item.id),
        project_id=str(item.project_id),
        title=item.title,
        description=item.description,
        severity=item.severity.value,
        status=item.status.value,
        detected_from=item.detected_from,
        opened_at=item.opened_at,
        resolved_at=item.resolved_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
