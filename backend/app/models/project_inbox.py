from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ProjectInboxStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    dismissed = "dismissed"


class ProjectInboxPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class ProjectInboxSource(str, enum.Enum):
    health_issue = "health_issue"
    manual = "manual"


class ProjectInboxItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_inbox_items"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectInboxStatus] = mapped_column(
        Enum(ProjectInboxStatus, name="project_inbox_status"), default=ProjectInboxStatus.open, index=True
    )
    priority: Mapped[ProjectInboxPriority] = mapped_column(
        Enum(ProjectInboxPriority, name="project_inbox_priority"), default=ProjectInboxPriority.normal, index=True
    )
    source_type: Mapped[ProjectInboxSource] = mapped_column(
        Enum(ProjectInboxSource, name="project_inbox_source"), default=ProjectInboxSource.manual, index=True
    )
    source_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "source_type", "source_key", name="uq_project_inbox_source"),)
