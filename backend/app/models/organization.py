import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class PartnerOrganization(Base, IdMixin, TimestampMixin):
    __tablename__ = "partner_organizations"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    short_name: Mapped[str] = mapped_column(String(32))
    legal_name: Mapped[str] = mapped_column(String(255))
    partner_type: Mapped[str] = mapped_column(String(32), default="beneficiary")
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    expertise: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "short_name", name="uq_partner_short_name"),)


class TeamMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "team_members"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "email", name="uq_team_member_project_email"),)
