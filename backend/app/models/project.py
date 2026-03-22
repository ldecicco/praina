import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ProjectStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class ProjectMode(str, enum.Enum):
    proposal = "proposal"
    execution = "execution"


class ProjectKind(str, enum.Enum):
    funded = "funded"
    research = "research"
    teaching = "teaching"


class ProjectLanguage(str, enum.Enum):
    en_GB = "en_GB"
    en_US = "en_US"
    it = "it"
    fr = "fr"
    de = "de"
    es = "es"
    pt = "pt"


class Project(Base, IdMixin, TimestampMixin):
    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date)
    duration_months: Mapped[int] = mapped_column(Integer)
    reporting_dates: Mapped[list[str]] = mapped_column(JSONB, default=list)
    baseline_version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.draft, index=True)
    project_mode: Mapped[str] = mapped_column(String(16), default="execution")
    project_kind: Mapped[str] = mapped_column(String(16), default=ProjectKind.funded.value, index=True)
    language: Mapped[str] = mapped_column(String(8), default="en_GB")
    coordinator_partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="SET NULL"), nullable=True
    )
    principal_investigator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True
    )
    proposal_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposal_templates.id", ondelete="SET NULL"), nullable=True
    )
