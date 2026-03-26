from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class TeachingProjectStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    at_risk = "at_risk"
    blocked = "blocked"
    completed = "completed"
    graded = "graded"


class TeachingProjectHealth(str, enum.Enum):
    green = "green"
    yellow = "yellow"
    red = "red"


class TeachingArtifactType(str, enum.Enum):
    report = "report"
    repository = "repository"
    video = "video"
    slides = "slides"
    dataset = "dataset"
    other = "other"


class TeachingArtifactStatus(str, enum.Enum):
    missing = "missing"
    submitted = "submitted"
    accepted = "accepted"
    needs_revision = "needs_revision"


class TeachingMilestoneStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    missed = "missed"


class TeachingBlockerSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TeachingBlockerStatus(str, enum.Enum):
    open = "open"
    monitoring = "monitoring"
    resolved = "resolved"


class TeachingProjectProfile(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_profiles"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    academic_year: Mapped[str | None] = mapped_column(String(32), nullable=True)
    term: Mapped[str | None] = mapped_column(String(32), nullable=True)
    functional_objectives_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    specifications_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[TeachingProjectStatus] = mapped_column(
        Enum(TeachingProjectStatus, name="teaching_project_status"),
        default=TeachingProjectStatus.draft,
        index=True,
    )
    health: Mapped[TeachingProjectHealth] = mapped_column(
        Enum(TeachingProjectHealth, name="teaching_project_health"),
        default=TeachingProjectHealth.green,
        index=True,
    )
    reporting_cadence_days: Mapped[int] = mapped_column(Integer, default=14)
    final_grade: Mapped[float | None] = mapped_column(Float, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeachingProjectStudent(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_students"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TeachingProjectArtifact(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_artifacts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    artifact_type: Mapped[TeachingArtifactType] = mapped_column(
        Enum(TeachingArtifactType, name="teaching_artifact_type"),
        default=TeachingArtifactType.other,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(default=False)
    status: Mapped[TeachingArtifactStatus] = mapped_column(
        Enum(TeachingArtifactStatus, name="teaching_artifact_status"),
        default=TeachingArtifactStatus.missing,
        index=True,
    )
    document_key: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeachingProjectBackgroundMaterial(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_background_materials"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    material_type: Mapped[str] = mapped_column(String(32), default="other", index=True)
    title: Mapped[str] = mapped_column(String(255))
    bibliography_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bibliography_references.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_key: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TeachingProgressReport(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_progress_reports"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    report_date: Mapped[datetime | None] = mapped_column(Date, nullable=True, index=True)
    meeting_date: Mapped[datetime | None] = mapped_column(Date, nullable=True, index=True)
    work_done_markdown: Mapped[str] = mapped_column(Text, default="")
    next_steps_markdown: Mapped[str] = mapped_column(Text, default="")
    supervisor_feedback_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_document_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    transcript_document_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeachingProjectMilestone(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[TeachingMilestoneStatus] = mapped_column(
        Enum(TeachingMilestoneStatus, name="teaching_milestone_status"),
        default=TeachingMilestoneStatus.pending,
        index=True,
    )


class TeachingProjectAssessment(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_assessments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    grade: Mapped[float | None] = mapped_column(Float, nullable=True)
    strengths_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    weaknesses_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    grading_rationale_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    grader_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeachingProjectBlocker(Base, IdMixin, TimestampMixin):
    __tablename__ = "teaching_project_blockers"
    __table_args__ = (
        UniqueConstraint("project_id", "title", name="uq_teaching_project_blocker_title"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[TeachingBlockerSeverity] = mapped_column(
        Enum(TeachingBlockerSeverity, name="teaching_blocker_severity"),
        default=TeachingBlockerSeverity.medium,
        index=True,
    )
    status: Mapped[TeachingBlockerStatus] = mapped_column(
        Enum(TeachingBlockerStatus, name="teaching_blocker_status"),
        default=TeachingBlockerStatus.open,
        index=True,
    )
    detected_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teaching_progress_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    last_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teaching_progress_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeachingChunk(Base, IdMixin):
    __tablename__ = "teaching_chunks"

    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
