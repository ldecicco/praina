import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class PlatformRole(str, enum.Enum):
    super_admin = "super_admin"
    project_creator = "project_creator"
    user = "user"


class ProjectRole(str, enum.Enum):
    project_owner = "project_owner"
    project_manager = "project_manager"
    partner_lead = "partner_lead"
    partner_member = "partner_member"
    reviewer = "reviewer"
    viewer = "viewer"


class UserAccount(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_accounts"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(120))
    platform_role: Mapped[str] = mapped_column(String(32), default=PlatformRole.user.value, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ProjectMembership(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_memberships"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default=ProjectRole.viewer.value, index=True)

    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_membership"),)
