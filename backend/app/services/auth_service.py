import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.auth import PlatformRole, ProjectMembership, ProjectRole, UserAccount, UserPushDevice
from app.models.organization import TeamMember
from app.models.project import Project, ProjectKind
from app.models.course import Course, CourseTeachingAssistant
from app.models.teaching import TeachingProjectProfile
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.teaching_service import TeachingService

MANAGE_ROLES = {ProjectRole.project_owner.value, ProjectRole.project_manager.value}
SYSTEM_USER_EMAILS = {"project-bot@local", "project-bot@agenticpm.local"}


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def register(self, email: str, password: str, display_name: str) -> UserAccount:
        normalized = email.strip().lower()
        if not normalized:
            raise ValidationError("Email is required.")
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

        user = UserAccount(
            email=normalized,
            password_hash=hash_password(password),
            display_name=display_name.strip(),
            platform_role=PlatformRole.user.value,
            is_active=True,
            can_access_research=True,
            can_access_teaching=True,
        )
        self.db.add(user)
        try:
            self.db.flush()
            self._sync_project_access_for_user(user)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("User with this email already exists.") from exc
        self.db.refresh(user)
        return user

    def admin_create_user(
        self,
        actor_user_id: uuid.UUID,
        *,
        email: str,
        display_name: str,
        password: str | None = None,
        platform_role: str = PlatformRole.user.value,
        is_active: bool = True,
        can_access_research: bool = True,
        can_access_teaching: bool = True,
    ) -> tuple[UserAccount, str]:
        self._assert_super_admin(actor_user_id)
        normalized_email = email.strip().lower()
        if not normalized_email:
            raise ValidationError("Email is required.")
        cleaned_name = display_name.strip()
        if not cleaned_name:
            raise ValidationError("Display name is required.")
        normalized_role = platform_role.strip().lower()
        allowed_roles = {item.value for item in PlatformRole}
        if normalized_role not in allowed_roles:
            raise ValidationError(f"Invalid platform role. Allowed: {', '.join(sorted(allowed_roles))}.")

        generated_password = password.strip() if password else ""
        if not generated_password:
            generated_password = uuid.uuid4().hex[:12]
        if len(generated_password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

        user = UserAccount(
            email=normalized_email,
            password_hash=hash_password(generated_password),
            display_name=cleaned_name,
            platform_role=normalized_role,
            is_active=is_active,
            can_access_research=can_access_research,
            can_access_teaching=can_access_teaching,
        )
        self.db.add(user)
        try:
            self.db.flush()
            self._sync_project_access_for_user(user)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("User with this email already exists.") from exc
        self.db.refresh(user)
        return user, generated_password

    def login(self, email: str, password: str) -> tuple[UserAccount, str, str]:
        normalized = email.strip().lower()
        user = self.db.scalar(select(UserAccount).where(UserAccount.email == normalized))
        if not user or not user.is_active:
            raise ValidationError("Invalid credentials.")
        if not verify_password(password, user.password_hash):
            raise ValidationError("Invalid credentials.")

        user.last_login_at = datetime.now(timezone.utc)
        self._sync_project_access_for_user(user)
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)
        self.db.commit()
        self.db.refresh(user)
        return user, access_token, refresh_token

    def change_password(self, user_id: uuid.UUID, *, current_password: str, new_password: str) -> UserAccount:
        user = self.get_user_by_id(user_id)
        if not verify_password(current_password, user.password_hash):
            raise ValidationError("Current password is incorrect.")
        cleaned_new_password = new_password.strip()
        if len(cleaned_new_password) < 8:
            raise ValidationError("New password must be at least 8 characters.")
        if verify_password(cleaned_new_password, user.password_hash):
            raise ValidationError("New password must be different from the current password.")
        user.password_hash = hash_password(cleaned_new_password)
        self.db.commit()
        self.db.refresh(user)
        return user

    def start_telegram_verification(self, user_id: uuid.UUID, *, chat_id: str) -> tuple[UserAccount, str, datetime]:
        user = self.get_user_by_id(user_id)
        cleaned_chat_id = chat_id.strip()
        if not cleaned_chat_id:
            raise ValidationError("Telegram chat id is required.")
        existing = self.db.scalar(
            select(UserAccount).where(
                UserAccount.telegram_chat_id == cleaned_chat_id,
                UserAccount.id != user.id,
            )
        )
        if existing:
            raise ConflictError("This Telegram chat is already linked to another user.")
        code = uuid.uuid4().hex[:10].upper()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        user.telegram_pending_chat_id = cleaned_chat_id
        user.telegram_link_code = code
        user.telegram_link_code_expires_at = expires_at
        self.db.commit()
        self.db.refresh(user)
        return user, code, expires_at

    def start_telegram_discovery(self, user_id: uuid.UUID) -> tuple[UserAccount, str, datetime]:
        user = self.get_user_by_id(user_id)
        code = uuid.uuid4().hex[:10].upper()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        user.telegram_pending_chat_id = None
        user.telegram_link_code = code
        user.telegram_link_code_expires_at = expires_at
        self.db.commit()
        self.db.refresh(user)
        return user, code, expires_at

    def get_telegram_link_state(self, user_id: uuid.UUID):
        user = self.get_user_by_id(user_id)
        now = datetime.now(timezone.utc)
        pending_code = None
        pending_expires_at = None
        if user.telegram_link_code and user.telegram_link_code_expires_at and user.telegram_link_code_expires_at > now:
            pending_code = user.telegram_link_code
            pending_expires_at = user.telegram_link_code_expires_at
        return SimpleNamespace(
            linked=bool(user.telegram_chat_id),
            notifications_enabled=bool(user.telegram_notifications_enabled and user.telegram_chat_id),
            chat_id=user.telegram_chat_id,
            pending_chat_id=user.telegram_pending_chat_id,
            telegram_username=user.telegram_username,
            telegram_first_name=user.telegram_first_name,
            pending_code=pending_code,
            pending_code_expires_at=pending_expires_at,
        )

    def update_telegram_preferences(self, user_id: uuid.UUID, *, notifications_enabled: bool) -> UserAccount:
        user = self.get_user_by_id(user_id)
        if notifications_enabled and not user.telegram_chat_id:
            raise ValidationError("Link Telegram before enabling notifications.")
        user.telegram_notifications_enabled = notifications_enabled
        self.db.commit()
        self.db.refresh(user)
        return user

    def upsert_push_device(
        self,
        user_id: uuid.UUID,
        *,
        token: str,
        platform: str,
        device_id: str | None = None,
        app_version: str | None = None,
    ) -> UserPushDevice:
        user = self.get_user_by_id(user_id)
        cleaned_token = token.strip()
        cleaned_platform = platform.strip().lower()
        if not cleaned_token:
            raise ValidationError("Push token is required.")
        if cleaned_platform not in {"android", "ios"}:
            raise ValidationError("Invalid push platform.")

        existing = self.db.scalar(select(UserPushDevice).where(UserPushDevice.token == cleaned_token))
        if existing:
            existing.user_id = user.id
            existing.platform = cleaned_platform
            existing.device_id = device_id.strip() if device_id else None
            existing.app_version = app_version.strip() if app_version else None
            existing.enabled = True
            existing.last_seen_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        item = UserPushDevice(
            user_id=user.id,
            token=cleaned_token,
            platform=cleaned_platform,
            device_id=device_id.strip() if device_id else None,
            app_version=app_version.strip() if app_version else None,
            enabled=True,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def disable_push_device_tokens(self, tokens: list[str]) -> int:
        cleaned_tokens = [token.strip() for token in tokens if token and token.strip()]
        if not cleaned_tokens:
            return 0
        items = list(
            self.db.scalars(
                select(UserPushDevice).where(UserPushDevice.token.in_(cleaned_tokens))
            ).all()
        )
        if not items:
            return 0
        for item in items:
            item.enabled = False
        self.db.commit()
        return len(items)

    def disconnect_telegram(self, user_id: uuid.UUID) -> UserAccount:
        user = self.get_user_by_id(user_id)
        user.telegram_chat_id = None
        user.telegram_username = None
        user.telegram_first_name = None
        user.telegram_notifications_enabled = False
        user.telegram_pending_chat_id = None
        user.telegram_link_code = None
        user.telegram_link_code_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def confirm_telegram_verification(
        self,
        user_id: uuid.UUID,
        *,
        code: str,
    ) -> UserAccount:
        user = self.get_user_by_id(user_id)
        normalized = code.strip().upper()
        if not normalized:
            raise ValidationError("Verification code is required.")
        now = datetime.now(timezone.utc)
        if not user.telegram_pending_chat_id:
            raise ValidationError("No Telegram verification is pending.")
        if user.telegram_link_code != normalized:
            raise ValidationError("Invalid verification code.")
        if not user.telegram_link_code_expires_at or user.telegram_link_code_expires_at <= now:
            raise ValidationError("Verification code has expired.")
        existing = self.db.scalar(
            select(UserAccount).where(
                UserAccount.telegram_chat_id == user.telegram_pending_chat_id,
                UserAccount.id != user.id,
            )
        )
        if existing:
            raise ConflictError("This Telegram chat is already linked to another user.")
        user.telegram_chat_id = user.telegram_pending_chat_id
        user.telegram_notifications_enabled = True
        user.telegram_pending_chat_id = None
        user.telegram_link_code = None
        user.telegram_link_code_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def complete_telegram_discovery(
        self,
        user_id: uuid.UUID,
        *,
        chat_id: str,
        code: str,
        telegram_username: str | None = None,
        telegram_first_name: str | None = None,
    ) -> UserAccount:
        user = self.get_user_by_id(user_id)
        normalized = code.strip().upper()
        if not normalized:
            raise ValidationError("Verification code is required.")
        now = datetime.now(timezone.utc)
        if user.telegram_link_code != normalized:
            raise ValidationError("Invalid verification code.")
        if not user.telegram_link_code_expires_at or user.telegram_link_code_expires_at <= now:
            raise ValidationError("Verification code has expired.")
        cleaned_chat_id = chat_id.strip()
        if not cleaned_chat_id:
            raise ValidationError("Telegram chat id is required.")
        existing = self.db.scalar(
            select(UserAccount).where(
                UserAccount.telegram_chat_id == cleaned_chat_id,
                UserAccount.id != user.id,
            )
        )
        if existing:
            raise ConflictError("This Telegram chat is already linked to another user.")
        user.telegram_chat_id = cleaned_chat_id
        user.telegram_pending_chat_id = None
        user.telegram_username = telegram_username
        user.telegram_first_name = telegram_first_name
        user.telegram_notifications_enabled = True
        user.telegram_link_code = None
        user.telegram_link_code_expires_at = None
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_user_by_id(self, user_id: uuid.UUID) -> UserAccount:
        user = self.db.get(UserAccount, user_id)
        if not user:
            raise NotFoundError("User not found.")
        return user

    def sync_user_project_access(self, user_id: uuid.UUID) -> UserAccount:
        user = self.get_user_by_id(user_id)
        self._sync_project_access_for_user(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_memberships_for_user(self, user_id: uuid.UUID) -> list[ProjectMembership]:
        rows = self.db.scalars(
            select(ProjectMembership).where(ProjectMembership.user_id == user_id).order_by(ProjectMembership.created_at.asc())
        ).all()
        return list(rows)

    def list_project_memberships(self, project_id: uuid.UUID) -> list[ProjectMembership]:
        project = self._get_project(project_id)
        rows = list(
            self.db.scalars(
                select(ProjectMembership)
                .where(ProjectMembership.project_id == project_id)
                .order_by(ProjectMembership.created_at.asc())
            ).all()
        )
        if (getattr(project, "project_kind", ProjectKind.funded.value) or ProjectKind.funded.value) != ProjectKind.teaching.value:
            return rows
        return self._teaching_memberships(project_id, rows)

    def list_project_memberships_for_actor(self, project_id: uuid.UUID, actor_user_id: uuid.UUID) -> list[ProjectMembership]:
        project = self._get_project(project_id)
        actor = self.db.get(UserAccount, actor_user_id)
        if not actor:
            raise NotFoundError("Actor user not found.")
        if actor.platform_role != PlatformRole.super_admin.value:
            self._get_project_role(project_id, actor_user_id)
        rows = list(
            self.db.scalars(
                select(ProjectMembership)
                .where(ProjectMembership.project_id == project_id)
                .order_by(ProjectMembership.created_at.asc())
            ).all()
        )
        if (getattr(project, "project_kind", ProjectKind.funded.value) or ProjectKind.funded.value) != ProjectKind.teaching.value:
            return rows
        return self._teaching_memberships(project_id, rows)

    def list_project_memberships_with_users_for_actor(
        self, project_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> list[tuple[ProjectMembership, UserAccount]]:
        memberships = self.list_project_memberships_for_actor(project_id, actor_user_id)
        if not memberships:
            return []
        user_ids = [item.user_id for item in memberships]
        users = self.db.scalars(select(UserAccount).where(UserAccount.id.in_(user_ids))).all()
        by_id = {item.id: item for item in users}
        items: list[tuple[ProjectMembership, UserAccount]] = []
        for membership in memberships:
            user = by_id.get(membership.user_id)
            if user:
                items.append((membership, user))
        return items

    def upsert_membership(
        self, project_id: uuid.UUID, actor_user_id: uuid.UUID, user_id: uuid.UUID, role: str
    ) -> ProjectMembership:
        self._get_project(project_id)
        self._assert_manage_memberships(project_id, actor_user_id)
        normalized_role = self._normalize_project_role(role)
        self.get_user_by_id(user_id)

        membership = self.db.scalar(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        )
        if membership:
            membership.role = normalized_role
            self.db.commit()
            self.db.refresh(membership)
            return membership

        membership = ProjectMembership(project_id=project_id, user_id=user_id, role=normalized_role)
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def list_users(
        self, actor_user_id: uuid.UUID, page: int, page_size: int, search: str | None = None
    ) -> tuple[list[UserAccount], int]:
        self._assert_super_admin(actor_user_id)
        stmt = select(UserAccount).where(UserAccount.email.notin_(SYSTEM_USER_EMAILS))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                func.lower(UserAccount.email).like(func.lower(like))
                | func.lower(UserAccount.display_name).like(func.lower(like))
            )
        stmt = stmt.order_by(UserAccount.created_at.desc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def discover_users(
        self, actor_user_id: uuid.UUID, page: int, page_size: int, search: str | None = None
    ) -> tuple[list[UserAccount], int]:
        actor = self.db.get(UserAccount, actor_user_id)
        if not actor or not actor.is_active:
            raise NotFoundError("Actor user not found.")

        stmt = select(UserAccount).where(UserAccount.is_active.is_(True), UserAccount.email.notin_(SYSTEM_USER_EMAILS))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                func.lower(UserAccount.email).like(func.lower(like))
                | func.lower(UserAccount.display_name).like(func.lower(like))
            )
        stmt = stmt.order_by(UserAccount.display_name.asc(), UserAccount.email.asc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def update_user(
        self,
        actor_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
        *,
        display_name: str | None = None,
        platform_role: str | None = None,
        is_active: bool | None = None,
        can_access_research: bool | None = None,
        can_access_teaching: bool | None = None,
    ) -> UserAccount:
        self._assert_super_admin(actor_user_id)
        user = self.db.get(UserAccount, target_user_id)
        if not user:
            raise NotFoundError("User not found.")

        if display_name is not None:
            cleaned = display_name.strip()
            if not cleaned:
                raise ValidationError("display_name cannot be empty.")
            user.display_name = cleaned
        if platform_role is not None:
            normalized = platform_role.strip().lower()
            allowed = {item.value for item in PlatformRole}
            if normalized not in allowed:
                raise ValidationError(f"Invalid platform role. Allowed: {', '.join(sorted(allowed))}.")
            user.platform_role = normalized
        if is_active is not None:
            user.is_active = is_active
        if can_access_research is not None:
            user.can_access_research = can_access_research
        if can_access_teaching is not None:
            user.can_access_teaching = can_access_teaching

        self.db.commit()
        self.db.refresh(user)
        return user

    def _assert_manage_memberships(self, project_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        actor = self.db.get(UserAccount, actor_user_id)
        if actor and actor.platform_role == PlatformRole.super_admin.value:
            return
        role = self._get_project_role(project_id, actor_user_id)
        if role not in MANAGE_ROLES:
            raise ValidationError("Insufficient role to manage project memberships.")

    def _get_project_role(self, project_id: uuid.UUID, user_id: uuid.UUID) -> str:
        project = self._get_project(project_id)
        if (getattr(project, "project_kind", ProjectKind.funded.value) or ProjectKind.funded.value) == ProjectKind.teaching.value:
            user = self.db.get(UserAccount, user_id)
            teaching_service = TeachingService(self.db)
            if user and teaching_service.can_manage_project(project_id, user_id, user.platform_role):
                profile = teaching_service.ensure_profile(project_id)
                course = self.db.get(Course, profile.course_id) if profile and profile.course_id else None
                if course and course.teacher_user_id == user_id:
                    return ProjectRole.project_owner.value
                return ProjectRole.project_manager.value
        membership = self.db.scalar(
            select(ProjectMembership.role).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
        if not membership:
            raise NotFoundError("User is not a member of this project.")
        return membership

    def _normalize_project_role(self, role: str) -> str:
        normalized = role.strip().lower()
        allowed = {item.value for item in ProjectRole}
        if normalized not in allowed:
            raise ValidationError(f"Invalid project role. Allowed: {', '.join(sorted(allowed))}.")
        return normalized

    def _assert_super_admin(self, actor_user_id: uuid.UUID) -> None:
        actor = self.db.get(UserAccount, actor_user_id)
        if not actor:
            raise NotFoundError("Actor user not found.")
        if actor.platform_role != PlatformRole.super_admin.value:
            raise ValidationError("Super admin role is required.")

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _sync_project_access_for_user(self, user: UserAccount) -> None:
        members = self.db.scalars(
            select(TeamMember).where(func.lower(TeamMember.email) == func.lower(user.email), TeamMember.is_active.is_(True))
        ).all()
        for member in members:
            if member.user_account_id != user.id:
                member.user_account_id = user.id
            membership = self.db.scalar(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == member.project_id,
                    ProjectMembership.user_id == user.id,
                )
            )
            if not membership:
                self.db.add(
                    ProjectMembership(
                        project_id=member.project_id,
                        user_id=user.id,
                        role=ProjectRole.partner_member.value,
                    )
                )

    def _teaching_memberships(
        self,
        project_id: uuid.UUID,
        existing_rows: list[ProjectMembership],
    ) -> list[ProjectMembership]:
        by_user_id: dict[uuid.UUID, ProjectMembership] = {row.user_id: row for row in existing_rows}
        profile = self.db.scalar(select(TeachingProjectProfile).where(TeachingProjectProfile.project_id == project_id))
        if not profile or not profile.course_id:
            return existing_rows

        course = self.db.get(Course, profile.course_id)
        if course and course.teacher_user_id and course.teacher_user_id not in by_user_id:
            by_user_id[course.teacher_user_id] = self._synthetic_membership(
                project_id=project_id,
                user_id=course.teacher_user_id,
                role=ProjectRole.project_owner.value,
            )

        assistants = self.db.scalars(
            select(CourseTeachingAssistant).where(CourseTeachingAssistant.course_id == profile.course_id)
        ).all()
        for assignment in assistants:
            if assignment.user_id not in by_user_id:
                by_user_id[assignment.user_id] = self._synthetic_membership(
                    project_id=project_id,
                    user_id=assignment.user_id,
                    role=ProjectRole.project_manager.value,
                )

        rows = list(by_user_id.values())
        rows.sort(key=lambda item: (getattr(item, "created_at", datetime.now(timezone.utc)), str(item.user_id)))
        return rows

    def _synthetic_membership(self, *, project_id: uuid.UUID, user_id: uuid.UUID, role: str) -> ProjectMembership:
        stamp = datetime.now(timezone.utc)
        synthetic_id = uuid.uuid5(uuid.NAMESPACE_URL, f"teaching-membership:{project_id}:{user_id}:{role}")
        return SimpleNamespace(
            id=synthetic_id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            created_at=stamp,
            updated_at=stamp,
        )
