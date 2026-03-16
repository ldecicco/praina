import uuid
import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class DocumentScope(str, enum.Enum):
    project = "project"
    wp = "wp"
    task = "task"
    deliverable = "deliverable"
    milestone = "milestone"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    indexed = "indexed"
    failed = "failed"


class ProjectDocument(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_documents"

    document_key: Mapped[uuid.UUID] = mapped_column(index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scope: Mapped[DocumentScope] = mapped_column(Enum(DocumentScope), index=True)
    title: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.uploaded.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    uploaded_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    proposal_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_proposal_sections.id", ondelete="SET NULL"), nullable=True
    )

    wp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("work_packages.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deliverables.id", ondelete="SET NULL"), nullable=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (UniqueConstraint("document_key", "version", name="uq_project_documents_document_key_version"),)


class DocumentChunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
