import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class CalendarProvider(str, enum.Enum):
    microsoft365 = "microsoft365"
    google = "google"


class CalendarSyncStatus(str, enum.Enum):
    disconnected = "disconnected"
    connected = "connected"
    syncing = "syncing"
    sync_error = "sync_error"


class CalendarIntegration(Base, IdMixin, TimestampMixin):
    __tablename__ = "calendar_integrations"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[CalendarProvider] = mapped_column(Enum(CalendarProvider, name="calendar_provider"), index=True)
    connected_account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    oauth_state: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[CalendarSyncStatus] = mapped_column(
        Enum(CalendarSyncStatus, name="calendar_sync_status"),
        default=CalendarSyncStatus.disconnected,
        index=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_calendar_integration_project_provider"),)
