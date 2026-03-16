"""proposal call brief and review kind

Revision ID: 20260313_0044
Revises: 20260313_0043
Create Date: 2026-03-13 20:35:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260313_0044"
down_revision = "20260313_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    proposal_review_kind = sa.Enum("general", "call_compliance", name="proposalreviewkind")
    proposal_review_kind.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "proposal_review_findings",
        sa.Column(
            "review_kind",
            proposal_review_kind,
            nullable=False,
            server_default="general",
        ),
    )
    op.create_index(
        "ix_proposal_review_findings_review_kind",
        "proposal_review_findings",
        ["review_kind"],
    )

    op.create_table(
        "proposal_call_briefs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("call_title", sa.String(length=255), nullable=True),
        sa.Column("funder_name", sa.String(length=160), nullable=True),
        sa.Column("programme_name", sa.String(length=160), nullable=True),
        sa.Column("reference_code", sa.String(length=120), nullable=True),
        sa.Column("submission_deadline", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("eligibility_notes", sa.Text(), nullable=True),
        sa.Column("budget_notes", sa.Text(), nullable=True),
        sa.Column("scoring_notes", sa.Text(), nullable=True),
        sa.Column("requirements_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposal_call_briefs_project_id", "proposal_call_briefs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_proposal_call_briefs_project_id", table_name="proposal_call_briefs")
    op.drop_table("proposal_call_briefs")

    op.drop_index("ix_proposal_review_findings_review_kind", table_name="proposal_review_findings")
    op.drop_column("proposal_review_findings", "review_kind")

    proposal_review_kind = sa.Enum("general", "call_compliance", name="proposalreviewkind")
    proposal_review_kind.drop(op.get_bind(), checkfirst=True)
