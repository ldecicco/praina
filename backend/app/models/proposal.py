import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ProposalTemplate(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_templates"

    call_library_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposal_call_library_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    funding_program: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ProposalTemplateSection(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_template_sections"

    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposal_templates.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_hint: Mapped[str] = mapped_column(String(32), default="project")

    __table_args__ = (UniqueConstraint("template_id", "key", name="uq_template_section_key"),)


class ProjectProposalSection(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_proposal_sections"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    template_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposal_template_sections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_hint: Mapped[str] = mapped_column(String(32), default="project")
    status: Mapped[str] = mapped_column(String(32), default="not_started", index=True)
    owner_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    yjs_state: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_project_proposal_section_key"),)


class ProposalCallBrief(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_call_briefs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    source_call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposal_call_library_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    copied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    copied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    call_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    funder_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    programme_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reference_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    submission_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProposalCallLibraryEntry(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_call_library_entries"

    call_title: Mapped[str] = mapped_column(String(255), index=True)
    funder_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    programme_name: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    reference_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    submission_deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class ProposalCallLibraryDocument(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_call_library_documents"

    library_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposal_call_library_entries.id", ondelete="CASCADE"),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64), default="other", index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    indexing_status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(500))
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProposalCallLibraryDocumentChunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_call_library_document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposal_call_library_documents.id", ondelete="CASCADE"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)


class ProposalCallIngestJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_call_ingest_jobs"

    library_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposal_call_library_entries.id", ondelete="CASCADE"),
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposal_call_library_documents.id", ondelete="CASCADE"),
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stream_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProposalSectionEditSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_section_edit_sessions"

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_proposal_sections.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updates_count: Mapped[int] = mapped_column(Integer, default=0)


class ProposalSubmissionRequirement(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_submission_requirements"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposal_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str] = mapped_column(String(32), default="project", index=True)
    format_hint: Mapped[str] = mapped_column(String(32), default="online", index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)


class ProposalSubmissionItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_submission_items"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposal_submission_requirements.id", ondelete="CASCADE"),
        index=True,
    )
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="not_started", index=True)
    latest_uploaded_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("requirement_id", "partner_id", name="uq_submission_requirement_partner"),)
