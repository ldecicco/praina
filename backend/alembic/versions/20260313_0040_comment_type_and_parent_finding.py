"""add comment finding type and parent_finding_id

Revision ID: 20260313_0040
Revises: 20260312_0039
Create Date: 2026-03-13 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260313_0040"
down_revision = "20260312_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE reviewfindingtype ADD VALUE IF NOT EXISTS 'comment'")
    op.add_column(
        "proposal_review_findings",
        sa.Column(
            "parent_finding_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proposal_review_findings.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_proposal_review_findings_parent_finding_id",
        "proposal_review_findings",
        ["parent_finding_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposal_review_findings_parent_finding_id", table_name="proposal_review_findings")
    op.drop_column("proposal_review_findings", "parent_finding_id")
