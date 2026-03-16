import enum
import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ActionItemStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    dismissed = "dismissed"


class ActionItemPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class ActionItemSource(str, enum.Enum):
    manual = "manual"
    assistant = "assistant"


class MeetingActionItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "meeting_action_items"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meeting_records.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    assignee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[ActionItemPriority] = mapped_column(
        Enum(ActionItemPriority, name="action_item_priority"), default=ActionItemPriority.normal
    )
    status: Mapped[ActionItemStatus] = mapped_column(
        Enum(ActionItemStatus, name="action_item_status"), default=ActionItemStatus.pending, index=True
    )
    source: Mapped[ActionItemSource] = mapped_column(
        Enum(ActionItemSource, name="action_item_source"), default=ActionItemSource.manual
    )
    linked_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
