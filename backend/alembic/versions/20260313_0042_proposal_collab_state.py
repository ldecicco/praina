"""proposal collaboration state

Revision ID: 20260313_0042
Revises: 20260313_0041
Create Date: 2026-03-13 12:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260313_0042"
down_revision = "20260313_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_proposal_sections", sa.Column("yjs_state", sa.LargeBinary(), nullable=True))

    op.create_table(
        "proposal_section_edit_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_proposal_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updates_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_proposal_section_edit_sessions_section_id",
        "proposal_section_edit_sessions",
        ["section_id"],
    )
    op.create_index(
        "ix_proposal_section_edit_sessions_user_id",
        "proposal_section_edit_sessions",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposal_section_edit_sessions_user_id", table_name="proposal_section_edit_sessions")
    op.drop_index("ix_proposal_section_edit_sessions_section_id", table_name="proposal_section_edit_sessions")
    op.drop_table("proposal_section_edit_sessions")
    op.drop_column("project_proposal_sections", "yjs_state")
