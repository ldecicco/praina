"""call library and project brief provenance

Revision ID: 20260314_0045
Revises: 20260313_0044
Create Date: 2026-03-14 10:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260314_0045"
down_revision = "20260313_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_call_library_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("call_title", sa.String(length=255), nullable=False),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposal_call_library_entries_call_title", "proposal_call_library_entries", ["call_title"])
    op.create_index("ix_proposal_call_library_entries_funder_name", "proposal_call_library_entries", ["funder_name"])
    op.create_index(
        "ix_proposal_call_library_entries_programme_name",
        "proposal_call_library_entries",
        ["programme_name"],
    )
    op.create_index(
        "ix_proposal_call_library_entries_reference_code",
        "proposal_call_library_entries",
        ["reference_code"],
    )
    op.create_index(
        "ix_proposal_call_library_entries_submission_deadline",
        "proposal_call_library_entries",
        ["submission_deadline"],
    )
    op.create_index("ix_proposal_call_library_entries_is_active", "proposal_call_library_entries", ["is_active"])

    op.add_column("proposal_call_briefs", sa.Column("source_call_id", UUID(as_uuid=True), nullable=True))
    op.add_column("proposal_call_briefs", sa.Column("source_version", sa.Integer(), nullable=True))
    op.add_column("proposal_call_briefs", sa.Column("copied_by_user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("proposal_call_briefs", sa.Column("copied_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_proposal_call_briefs_source_call_id",
        "proposal_call_briefs",
        "proposal_call_library_entries",
        ["source_call_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_proposal_call_briefs_copied_by_user_id",
        "proposal_call_briefs",
        "user_accounts",
        ["copied_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_proposal_call_briefs_source_call_id", "proposal_call_briefs", ["source_call_id"])
    op.create_index("ix_proposal_call_briefs_copied_by_user_id", "proposal_call_briefs", ["copied_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_proposal_call_briefs_copied_by_user_id", table_name="proposal_call_briefs")
    op.drop_index("ix_proposal_call_briefs_source_call_id", table_name="proposal_call_briefs")
    op.drop_constraint("fk_proposal_call_briefs_copied_by_user_id", "proposal_call_briefs", type_="foreignkey")
    op.drop_constraint("fk_proposal_call_briefs_source_call_id", "proposal_call_briefs", type_="foreignkey")
    op.drop_column("proposal_call_briefs", "copied_at")
    op.drop_column("proposal_call_briefs", "copied_by_user_id")
    op.drop_column("proposal_call_briefs", "source_version")
    op.drop_column("proposal_call_briefs", "source_call_id")

    op.drop_index("ix_proposal_call_library_entries_is_active", table_name="proposal_call_library_entries")
    op.drop_index("ix_proposal_call_library_entries_submission_deadline", table_name="proposal_call_library_entries")
    op.drop_index("ix_proposal_call_library_entries_reference_code", table_name="proposal_call_library_entries")
    op.drop_index("ix_proposal_call_library_entries_programme_name", table_name="proposal_call_library_entries")
    op.drop_index("ix_proposal_call_library_entries_funder_name", table_name="proposal_call_library_entries")
    op.drop_index("ix_proposal_call_library_entries_call_title", table_name="proposal_call_library_entries")
    op.drop_table("proposal_call_library_entries")
