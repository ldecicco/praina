import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_token, get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount, UserSuggestion, UserSuggestionStatus
from app.schemas.auth import (
    AuthTokenRead,
    MeRead,
    MembershipWithUserListRead,
    MembershipWithUserRead,
    MembershipRead,
    PasswordChangeRequest,
    TelegramDiscoveryStartRead,
    TelegramLinkStateRead,
    TelegramPreferencesUpdateRequest,
    TokenRefreshRequest,
    UserAdminCreateRequest,
    UserAdminUpdateRequest,
    UserSuggestionCreateRequest,
    UserSuggestionListRead,
    UserSuggestionRead,
    UserSuggestionUpdateRequest,
    UserListRead,
    UserLoginRequest,
    UserProfileUpdateRequest,
    UserRead,
    UserRegisterRequest,
)
from app.services.auth_service import AuthService
from app.services.notification_service import NotificationService
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.telegram_service import TelegramService

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


@router.post("/me/password")
def change_my_password(
    payload: PasswordChangeRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    service = AuthService(db)
    try:
        service.change_password(
            current_user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/me/telegram", response_model=TelegramLinkStateRead)
def get_my_telegram_state(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramLinkStateRead:
    state = AuthService(db).get_telegram_link_state(current_user.id)
    return TelegramLinkStateRead(
        linked=state.linked,
        notifications_enabled=state.notifications_enabled,
        bot_username=settings.telegram_bot_username,
        chat_id=state.chat_id,
        pending_chat_id=state.pending_chat_id,
        telegram_username=state.telegram_username,
        telegram_first_name=state.telegram_first_name,
        pending_code=state.pending_code,
        pending_code_expires_at=state.pending_code_expires_at,
    )


@router.post("/me/telegram/discovery", response_model=TelegramDiscoveryStartRead)
def start_my_telegram_discovery(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramDiscoveryStartRead:
    bot_username = (settings.telegram_bot_username or "").strip() or None
    if not bot_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram bot username is not configured on the backend.",
        )
    service = AuthService(db)
    try:
        _, code, expires_at = service.start_telegram_discovery(current_user.id)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    start_url = f"https://t.me/{bot_username}?start={code}" if bot_username else None
    return TelegramDiscoveryStartRead(
        code=code,
        expires_at=expires_at,
        bot_username=bot_username,
        start_url=start_url,
    )


@router.post("/me/telegram/discovery/complete", response_model=TelegramLinkStateRead)
def complete_my_telegram_discovery(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramLinkStateRead:
    service = AuthService(db)
    state = service.get_telegram_link_state(current_user.id)
    if not state.pending_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Telegram discovery is pending.")
    match = TelegramService().find_chat_by_code(state.pending_code)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Telegram chat found for this code. Open the bot link, press Start, then try again.",
        )
    try:
        service.complete_telegram_discovery(
            current_user.id,
            chat_id=match.chat_id,
            code=state.pending_code,
            telegram_username=match.username,
            telegram_first_name=match.first_name,
        )
    except (ValidationError, ConflictError) as exc:
        code_status = status.HTTP_409_CONFLICT if isinstance(exc, ConflictError) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code_status, detail=str(exc)) from exc
    state = service.get_telegram_link_state(current_user.id)
    return TelegramLinkStateRead(
        linked=state.linked,
        notifications_enabled=state.notifications_enabled,
        bot_username=settings.telegram_bot_username,
        chat_id=state.chat_id,
        pending_chat_id=state.pending_chat_id,
        telegram_username=state.telegram_username,
        telegram_first_name=state.telegram_first_name,
        pending_code=state.pending_code,
        pending_code_expires_at=state.pending_code_expires_at,
    )


@router.patch("/me/telegram", response_model=TelegramLinkStateRead)
def update_my_telegram_preferences(
    payload: TelegramPreferencesUpdateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramLinkStateRead:
    service = AuthService(db)
    try:
        service.update_telegram_preferences(
            current_user.id,
            notifications_enabled=payload.notifications_enabled,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    state = service.get_telegram_link_state(current_user.id)
    return TelegramLinkStateRead(
        linked=state.linked,
        notifications_enabled=state.notifications_enabled,
        bot_username=settings.telegram_bot_username,
        chat_id=state.chat_id,
        pending_chat_id=state.pending_chat_id,
        telegram_username=state.telegram_username,
        telegram_first_name=state.telegram_first_name,
        pending_code=state.pending_code,
        pending_code_expires_at=state.pending_code_expires_at,
    )


@router.delete("/me/telegram", response_model=TelegramLinkStateRead)
def disconnect_my_telegram(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramLinkStateRead:
    service = AuthService(db)
    service.disconnect_telegram(current_user.id)
    state = service.get_telegram_link_state(current_user.id)
    return TelegramLinkStateRead(
        linked=state.linked,
        notifications_enabled=state.notifications_enabled,
        bot_username=settings.telegram_bot_username,
        chat_id=state.chat_id,
        pending_chat_id=state.pending_chat_id,
        telegram_username=state.telegram_username,
        telegram_first_name=state.telegram_first_name,
        pending_code=state.pending_code,
        pending_code_expires_at=state.pending_code_expires_at,
    )


@router.post("/me/telegram/test")
def send_my_telegram_test_notification(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.telegram_chat_id or not current_user.telegram_notifications_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link Telegram and enable notifications before sending a test notification.",
        )
    NotificationService(db).notify(
        current_user.id,
        title="Telegram test notification",
        body="If you received this message in Telegram, the integration is working.",
        link_type=None,
        link_id=None,
    )
    return {"ok": True}


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


@router.post("/me/suggestions", response_model=UserSuggestionRead)
def create_my_suggestion(
    payload: UserSuggestionCreateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSuggestionRead:
    item = UserSuggestion(
        user_id=current_user.id,
        content=payload.content.strip(),
        status=UserSuggestionStatus.new.value,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _suggestion_read(item, current_user)


@router.get("/admin/suggestions", response_model=UserSuggestionListRead)
def list_user_suggestions(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSuggestionListRead:
    if current_user.platform_role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Restricted to administrators.")
    stmt = select(UserSuggestion, UserAccount).join(UserAccount, UserAccount.id == UserSuggestion.user_id)
    if status_filter:
        stmt = stmt.where(UserSuggestion.status == status_filter.strip().lower())
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            UserSuggestion.content.ilike(like)
            | UserAccount.display_name.ilike(like)
            | UserAccount.email.ilike(like)
        )
    total = len(db.execute(stmt).all())
    rows = db.execute(
        stmt.order_by(UserSuggestion.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_suggestion_read(item, user) for item, user in rows]
    return UserSuggestionListRead(items=items, page=page, page_size=page_size, total=total)


@router.patch("/admin/suggestions/{suggestion_id}", response_model=UserSuggestionRead)
def update_user_suggestion(
    suggestion_id: uuid.UUID,
    payload: UserSuggestionUpdateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSuggestionRead:
    if current_user.platform_role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Restricted to administrators.")
    item = db.get(UserSuggestion, suggestion_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found.")
    normalized = payload.status.strip().lower()
    try:
        UserSuggestionStatus(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid suggestion status.") from exc
    item.status = normalized
    db.commit()
    db.refresh(item)
    user = db.get(UserAccount, item.user_id)
    return _suggestion_read(item, user)


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
            can_access_research=payload.can_access_research,
            can_access_teaching=payload.can_access_teaching,
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
            can_access_research=payload.can_access_research,
            can_access_teaching=payload.can_access_teaching,
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
        can_access_research=user.can_access_research,
        can_access_teaching=user.can_access_teaching,
        temporary_password=temporary_password,
        job_title=user.job_title,
        organization=user.organization,
        phone=user.phone,
        avatar_url=avatar_url,
        telegram_linked=bool(user.telegram_chat_id),
        telegram_notifications_enabled=bool(user.telegram_notifications_enabled and user.telegram_chat_id),
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


def _suggestion_read(item: UserSuggestion, user: UserAccount | None) -> UserSuggestionRead:
    return UserSuggestionRead(
        id=str(item.id),
        user_id=str(item.user_id),
        user_display_name=user.display_name if user else "Unknown",
        user_email=user.email if user else "unknown@example.com",
        content=item.content,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
