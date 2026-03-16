import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class MeetingSourceType(str, enum.Enum):
    minutes = "minutes"
    transcript = "transcript"


class MeetingRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "meeting_records"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_type: Mapped[MeetingSourceType] = mapped_column(Enum(MeetingSourceType), index=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    participants_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    content_text: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calendar_import_batches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    indexing_status: Mapped[str] = mapped_column(String(32), default="pending")
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )


class MeetingChunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "meeting_chunks"

    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meeting_records.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
