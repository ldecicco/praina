import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token, get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.schemas.auth import (
    AuthTokenRead,
    MeRead,
    MembershipWithUserListRead,
    MembershipWithUserRead,
    MembershipRead,
    TokenRefreshRequest,
    UserAdminCreateRequest,
    UserAdminUpdateRequest,
    UserListRead,
    UserLoginRequest,
    UserProfileUpdateRequest,
    UserRead,
    UserRegisterRequest,
)
from app.services.auth_service import AuthService
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))

router = APIRouter()


@router.post("/register", response_model=UserRead)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> UserRead:
    service = AuthService(db)
    try:
        user = service.register(payload.email, payload.password, payload.display_name)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _user_read(user)


@router.post("/login", response_model=AuthTokenRead)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> AuthTokenRead:
    service = AuthService(db)
    try:
        _, access_token, refresh_token = service.login(payload.email, payload.password)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AuthTokenRead(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in_seconds=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=AuthTokenRead)
def refresh(payload: TokenRefreshRequest, db: Session = Depends(get_db)) -> AuthTokenRead:
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    try:
        user_id = uuid.UUID(str(token_payload["sub"]))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject.") from exc
    service = AuthService(db)
    try:
        service.get_user_by_id(user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    from app.core.security import create_access_token, create_refresh_token

    return AuthTokenRead(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        token_type="bearer",
        expires_in_seconds=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=MeRead)
def me(current_user: UserAccount = Depends(get_current_user), db: Session = Depends(get_db)) -> MeRead:
    service = AuthService(db)
    synced_user = service.sync_user_project_access(current_user.id)
    memberships = service.list_memberships_for_user(synced_user.id)
    return MeRead(user=_user_read(synced_user), memberships=[_membership_read(item) for item in memberships])


@router.patch("/me", response_model=UserRead)
def update_my_profile(
    payload: UserProfileUpdateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    if payload.display_name is not None:
        current_user.display_name = payload.display_name
    if payload.job_title is not None:
        current_user.job_title = payload.job_title
    if payload.organization is not None:
        current_user.organization = payload.organization
    if payload.phone is not None:
        current_user.phone = payload.phone
    db.commit()
    db.refresh(current_user)
    return _user_read(current_user)


@router.post("/me/avatar")
def upload_my_avatar(
    file: UploadFile,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not file.content_type or file.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type. Allowed: {', '.join(sorted(ALLOWED_AVATAR_TYPES))}",
        )
    data = file.file.read()
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_AVATAR_SIZE // (1024 * 1024)} MB.",
        )
    file_id = uuid.uuid4()
    filename = file.filename or "avatar"
    relative_path = f"avatars/{current_user.id}/{file_id}/{filename}"
    full_path = STORAGE_ROOT / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(data)
    current_user.avatar_path = relative_path
    db.commit()
    db.refresh(current_user)
    avatar_url = f"/auth/users/{current_user.id}/avatar"
    return {"avatar_url": avatar_url}


@router.get("/users/{user_id}/avatar")
def get_user_avatar(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    user = db.get(UserAccount, user_id)
    if not user or not user.avatar_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found.")
    full_path = STORAGE_ROOT / user.avatar_path
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar file not found.")
    return FileResponse(str(full_path))


@router.get("/users", response_model=UserListRead)
def list_users(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserListRead:
    service = AuthService(db)
    try:
        items, total = service.list_users(current_user.id, page, page_size, search=search)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return UserListRead(items=[_user_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.get("/users/discovery", response_model=UserListRead)
def discover_users(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserListRead:
    service = AuthService(db)
    try:
        items, total = service.discover_users(current_user.id, page, page_size, search=search)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return UserListRead(items=[_user_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserAdminUpdateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    service = AuthService(db)
    try:
        user = service.update_user(
            actor_user_id=current_user.id,
            target_user_id=user_id,
            display_name=payload.display_name,
            platform_role=payload.platform_role,
            is_active=payload.is_active,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _user_read(user)


@router.post("/users", response_model=UserRead)
def create_user(
    payload: UserAdminCreateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    service = AuthService(db)
    try:
        user, generated_password = service.admin_create_user(
            actor_user_id=current_user.id,
            email=payload.email,
            display_name=payload.display_name,
            password=payload.password,
            platform_role=payload.platform_role,
            is_active=payload.is_active,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _user_read(user, temporary_password=generated_password)


@router.get("/projects/{project_id}/memberships", response_model=MembershipWithUserListRead)
def list_project_memberships_with_users(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipWithUserListRead:
    service = AuthService(db)
    try:
        items = service.list_project_memberships_with_users_for_actor(project_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    rendered = [MembershipWithUserRead(membership=_membership_read(mem), user=_user_read(user)) for mem, user in items]
    return MembershipWithUserListRead(items=rendered, page=1, page_size=max(1, len(rendered)), total=len(rendered))


def _user_read(user: UserAccount, temporary_password: str | None = None) -> UserRead:
    avatar_url = f"/auth/users/{user.id}/avatar" if user.avatar_path else None
    return UserRead(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        platform_role=user.platform_role,
        is_active=user.is_active,
        temporary_password=temporary_password,
        job_title=user.job_title,
        organization=user.organization,
        phone=user.phone,
        avatar_url=avatar_url,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _membership_read(item) -> MembershipRead:
    return MembershipRead(
        id=str(item.id),
        project_id=str(item.project_id),
        user_id=str(item.user_id),
        role=item.role,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
