"""Notification model for in-app alerts."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class NotificationChannel(str, enum.Enum):
    in_app = "in_app"
    email = "email"
    both = "both"


class NotificationStatus(str, enum.Enum):
    unread = "unread"
    read = "read"
    dismissed = "dismissed"


class Notification(Base, IdMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(
        String(16),
        default=NotificationChannel.in_app.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=NotificationStatus.unread.value,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    link_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
