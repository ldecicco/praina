import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ReviewFindingType(str, enum.Enum):
    issue = "issue"
    warning = "warning"
    strength = "strength"
    comment = "comment"


class ReviewFindingStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"


class ReviewFindingSource(str, enum.Enum):
    manual = "manual"
    assistant = "assistant"


class DeliverableReviewFinding(Base, IdMixin, TimestampMixin):
    __tablename__ = "deliverable_review_findings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    deliverable_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliverables.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    finding_type: Mapped[ReviewFindingType] = mapped_column(Enum(ReviewFindingType), index=True)
    status: Mapped[ReviewFindingStatus] = mapped_column(Enum(ReviewFindingStatus), default=ReviewFindingStatus.open, index=True)
    source: Mapped[ReviewFindingSource] = mapped_column(Enum(ReviewFindingSource), default=ReviewFindingSource.manual, index=True)
    section_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ProposalReviewScope(str, enum.Enum):
    anchor = "anchor"
    section = "section"
    proposal = "proposal"


class ProposalReviewKind(str, enum.Enum):
    general = "general"
    call_compliance = "call_compliance"


class ProposalReviewFinding(Base, IdMixin, TimestampMixin):
    __tablename__ = "proposal_review_findings"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    proposal_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_proposal_sections.id", ondelete="CASCADE"), nullable=True, index=True
    )
    review_kind: Mapped[ProposalReviewKind] = mapped_column(
        Enum(ProposalReviewKind),
        default=ProposalReviewKind.general,
        index=True,
    )
    finding_type: Mapped[ReviewFindingType] = mapped_column(Enum(ReviewFindingType), index=True)
    status: Mapped[ReviewFindingStatus] = mapped_column(Enum(ReviewFindingStatus), default=ReviewFindingStatus.open, index=True)
    source: Mapped[ReviewFindingSource] = mapped_column(Enum(ReviewFindingSource), default=ReviewFindingSource.manual, index=True)
    scope: Mapped[ProposalReviewScope] = mapped_column(Enum(ProposalReviewScope), default=ProposalReviewScope.section, index=True)
    summary: Mapped[str] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_suffix: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_offset: Mapped[int | None] = mapped_column(nullable=True)
    end_offset: Mapped[int | None] = mapped_column(nullable=True)
    created_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parent_finding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposal_review_findings.id", ondelete="CASCADE"), nullable=True, index=True
    )
