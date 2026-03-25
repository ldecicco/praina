from __future__ import annotations

import enum
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


# ── Enums ──────────────────────────────────────────────────────────────

class CollectionStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    completed = "completed"


class CollectionMemberRole(str, enum.Enum):
    lead = "lead"
    contributor = "contributor"
    reviewer = "reviewer"


class ReadingStatus(str, enum.Enum):
    unread = "unread"
    reading = "reading"
    read = "read"
    reviewed = "reviewed"


class NoteType(str, enum.Enum):
    observation = "observation"
    discussion = "discussion"
    finding = "finding"
    hypothesis = "hypothesis"
    method = "method"
    decision = "decision"
    action_item = "action_item"
    literature_review = "literature_review"
    conclusion = "conclusion"


class OutputStatus(str, enum.Enum):
    not_started = "not_started"
    drafting = "drafting"
    internal_review = "internal_review"
    submitted = "submitted"
    published = "published"


class BibliographyVisibility(str, enum.Enum):
    private = "private"
    shared = "shared"


# ── Junction tables (plain Table) ─────────────────────────────────────

research_collection_wps = Table(
    "research_collection_wps",
    Base.metadata,
    Column("collection_id", UUID(as_uuid=True), ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
    Column("wp_id", UUID(as_uuid=True), ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
)

research_collection_tasks = Table(
    "research_collection_tasks",
    Base.metadata,
    Column("collection_id", UUID(as_uuid=True), ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
    Column("task_id", UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
)

research_collection_deliverables = Table(
    "research_collection_deliverables",
    Base.metadata,
    Column("collection_id", UUID(as_uuid=True), ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
    Column("deliverable_id", UUID(as_uuid=True), ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True),
)

research_collection_meetings = Table(
    "research_collection_meetings",
    Base.metadata,
    Column("collection_id", UUID(as_uuid=True), ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
    Column("meeting_id", UUID(as_uuid=True), ForeignKey("meeting_records.id", ondelete="CASCADE"), primary_key=True),
)

research_note_references = Table(
    "research_note_references",
    Base.metadata,
    Column("note_id", UUID(as_uuid=True), ForeignKey("research_notes.id", ondelete="CASCADE"), primary_key=True),
    Column("reference_id", UUID(as_uuid=True), ForeignKey("research_references.id", ondelete="CASCADE"), primary_key=True),
)


# ── Models ─────────────────────────────────────────────────────────────

class ResearchCollection(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_collections"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_questions: Mapped[list | None] = mapped_column(JSONB, default=list)
    status: Mapped[CollectionStatus] = mapped_column(
        Enum(CollectionStatus, name="collection_status"), default=CollectionStatus.active, index=True,
    )
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    overleaf_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_output_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_status: Mapped[OutputStatus] = mapped_column(
        Enum(OutputStatus, name="research_output_status"),
        default=OutputStatus.not_started,
        index=True,
    )
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True,
    )
    ai_synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_synthesis_at: Mapped[uuid.UUID | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchCollectionMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_collection_members"
    __table_args__ = (
        {"extend_existing": True},
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_collections.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("team_members.id", ondelete="CASCADE"), index=True)
    role: Mapped[CollectionMemberRole] = mapped_column(
        Enum(CollectionMemberRole, name="collection_member_role"), default=CollectionMemberRole.contributor,
    )


class ResearchReference(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_references"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    bibliography_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bibliography_references.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_collections.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(512))
    authors: Mapped[list | None] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)
    reading_status: Mapped[ReadingStatus] = mapped_column(
        Enum(ReadingStatus, name="reading_status"), default=ReadingStatus.unread, index=True,
    )
    added_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True,
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_at: Mapped[uuid.UUID | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BibliographyReference(Base, IdMixin, TimestampMixin):
    __tablename__ = "bibliography_references"

    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    authors: Mapped[list | None] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    bibtex_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visibility: Mapped[BibliographyVisibility] = mapped_column(
        Enum(BibliographyVisibility, name="bibliography_visibility"),
        default=BibliographyVisibility.shared,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ResearchNote(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_notes"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_collections.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    author_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    note_type: Mapped[NoteType] = mapped_column(
        Enum(NoteType, name="note_type"), default=NoteType.observation, index=True,
    )
    tags: Mapped[list | None] = mapped_column(JSONB, default=list)


class ResearchAnnotation(Base, IdMixin, TimestampMixin):
    __tablename__ = "research_annotations"

    reference_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_references.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True,
    )
    content: Mapped[str] = mapped_column(Text)
    page_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    highlight_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchChunk(Base, IdMixin):
    __tablename__ = "research_chunks"

    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
