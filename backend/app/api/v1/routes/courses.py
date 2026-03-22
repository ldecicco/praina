from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.schemas.course import (
    CourseCreate,
    CourseListRead,
    CourseMaterialCreate,
    CourseMaterialRead,
    CourseMaterialUpdate,
    CourseRead,
    CourseStaffUserRead,
    CourseTeachingAssistantCreate,
    CourseUpdate,
)
from app.services.course_service import CourseService
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError


def require_teaching_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not current_user.can_access_teaching:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Teaching.")


router = APIRouter(dependencies=[Depends(require_teaching_access)])


@router.get("/courses", response_model=CourseListRead)
def list_courses(
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseListRead:
    service = CourseService(db)
    items, total = service.list_courses(
        search=search,
        active_only=active_only,
        page=page,
        page_size=page_size,
        actor_user_id=current_user.id,
        actor_platform_role=current_user.platform_role,
    )
    return CourseListRead(
        items=[_course_read(service, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseRead:
    _require_super_admin(current_user)
    service = CourseService(db)
    try:
        item = service.create_course(**payload.model_dump())
    except (ConflictError, NotFoundError) as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ConflictError) else 404, detail=str(exc)) from exc
    return _course_read(service, item)


@router.patch("/courses/{course_id}", response_model=CourseRead)
def update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseRead:
    _require_super_admin(current_user)
    service = CourseService(db)
    try:
        item = service.update_course(course_id, **payload.model_dump(exclude_unset=True))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _course_read(service, item)


@router.post("/courses/{course_id}/teaching-assistants", response_model=CourseRead)
def add_teaching_assistant(
    course_id: uuid.UUID,
    payload: CourseTeachingAssistantCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseRead:
    service = CourseService(db)
    _require_ta_manager(service, course_id, current_user)
    try:
        service.add_teaching_assistant(course_id, user_id=payload.user_id)
        course = service.get_course(course_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _course_read(service, course)


@router.delete("/courses/{course_id}/teaching-assistants/{user_id}", response_model=CourseRead)
def remove_teaching_assistant(
    course_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseRead:
    service = CourseService(db)
    _require_ta_manager(service, course_id, current_user)
    try:
        service.remove_teaching_assistant(course_id, user_id)
        course = service.get_course(course_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _course_read(service, course)


@router.post("/courses/{course_id}/materials", response_model=CourseMaterialRead, status_code=status.HTTP_201_CREATED)
def create_course_material(
    course_id: uuid.UUID,
    payload: CourseMaterialCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseMaterialRead:
    service = CourseService(db)
    _require_ta_manager(service, course_id, current_user)
    try:
        item = service.create_material(course_id, **payload.model_dump())
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _material_read(item)


@router.patch("/courses/{course_id}/materials/{material_id}", response_model=CourseMaterialRead)
def update_course_material(
    course_id: uuid.UUID,
    material_id: uuid.UUID,
    payload: CourseMaterialUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseMaterialRead:
    service = CourseService(db)
    _require_ta_manager(service, course_id, current_user)
    try:
        item = service.update_material(course_id, material_id, **payload.model_dump(exclude_unset=True))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _material_read(item)


@router.delete("/courses/{course_id}/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course_material(
    course_id: uuid.UUID,
    material_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    service = CourseService(db)
    _require_ta_manager(service, course_id, current_user)
    try:
        service.delete_material(course_id, material_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_super_admin(current_user)
    service = CourseService(db)
    try:
        service.delete_course(course_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_super_admin(current_user: UserAccount) -> None:
    if current_user.platform_role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super_admin can manage courses.")


def _require_ta_manager(service: CourseService, course_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = service.can_manage_tas(course_id, current_user.id, current_user.platform_role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the course teacher can manage teaching assistants.")


def _user_read(user: UserAccount | None) -> CourseStaffUserRead | None:
    if not user:
        return None
    return CourseStaffUserRead(user_id=str(user.id), display_name=user.display_name, email=user.email)


def _course_read(service: CourseService, item) -> CourseRead:
    teacher = service.get_teacher(item.id)
    assistants = service.list_teaching_assistants(item.id)
    materials = service.list_materials(item.id)
    return CourseRead(
        id=str(item.id),
        code=item.code,
        title=item.title,
        description=item.description,
        is_active=item.is_active,
        has_project_deadlines=item.has_project_deadlines,
        teacher=_user_read(teacher),
        teaching_assistants=[entry for entry in (_user_read(user) for user in assistants) if entry],
        materials=[_material_read(material) for material in materials],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _material_read(item) -> CourseMaterialRead:
    return CourseMaterialRead(
        id=str(item.id),
        course_id=str(item.course_id),
        material_type=item.material_type.value if hasattr(item.material_type, "value") else str(item.material_type),
        title=item.title,
        content_markdown=item.content_markdown,
        external_url=item.external_url,
        sort_order=item.sort_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
