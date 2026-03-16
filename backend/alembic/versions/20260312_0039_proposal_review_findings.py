"""add proposal review findings

Revision ID: 20260312_0039
Revises: 20260312_0038
Create Date: 2026-03-12 13:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID


revision = "20260312_0039"
down_revision = "20260312_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE proposal_review_scope AS ENUM ('anchor', 'section', 'proposal'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    finding_type = ENUM("issue", "warning", "strength", name="reviewfindingtype", create_type=False)
    finding_status = ENUM("open", "resolved", name="reviewfindingstatus", create_type=False)
    finding_source = ENUM("manual", "assistant", name="reviewfindingsource", create_type=False)
    review_scope = ENUM("anchor", "section", "proposal", name="proposal_review_scope", create_type=False)

    op.create_table(
        "proposal_review_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proposal_section_id", UUID(as_uuid=True), sa.ForeignKey("project_proposal_sections.id", ondelete="CASCADE"), nullable=True),
        sa.Column("finding_type", finding_type, nullable=False),
        sa.Column("status", finding_status, nullable=False, server_default="open"),
        sa.Column("source", finding_source, nullable=False, server_default="manual"),
        sa.Column("scope", review_scope, nullable=False, server_default="section"),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("anchor_text", sa.Text(), nullable=True),
        sa.Column("anchor_prefix", sa.Text(), nullable=True),
        sa.Column("anchor_suffix", sa.Text(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("created_by_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposal_review_findings_project_id", "proposal_review_findings", ["project_id"])
    op.create_index("ix_proposal_review_findings_proposal_section_id", "proposal_review_findings", ["proposal_section_id"])
    op.create_index("ix_proposal_review_findings_status", "proposal_review_findings", ["status"])
    op.create_index("ix_proposal_review_findings_scope", "proposal_review_findings", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_proposal_review_findings_scope", table_name="proposal_review_findings")
    op.drop_index("ix_proposal_review_findings_status", table_name="proposal_review_findings")
    op.drop_index("ix_proposal_review_findings_proposal_section_id", table_name="proposal_review_findings")
    op.drop_index("ix_proposal_review_findings_project_id", table_name="proposal_review_findings")
    op.drop_table("proposal_review_findings")
    op.execute("DROP TYPE IF EXISTS proposal_review_scope")
