"""add proposal call ingest jobs

Revision ID: 20260314_0048
Revises: 20260314_0047
Create Date: 2026-03-14 16:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260314_0048"
down_revision = "20260314_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_call_ingest_jobs",
        sa.Column("library_entry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["proposal_call_library_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["library_entry_id"], ["proposal_call_library_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposal_call_ingest_jobs_library_entry_id", "proposal_call_ingest_jobs", ["library_entry_id"])
    op.create_index("ix_proposal_call_ingest_jobs_document_id", "proposal_call_ingest_jobs", ["document_id"])
    op.create_index("ix_proposal_call_ingest_jobs_created_by_user_id", "proposal_call_ingest_jobs", ["created_by_user_id"])
    op.create_index("ix_proposal_call_ingest_jobs_status", "proposal_call_ingest_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_proposal_call_ingest_jobs_status", table_name="proposal_call_ingest_jobs")
    op.drop_index("ix_proposal_call_ingest_jobs_created_by_user_id", table_name="proposal_call_ingest_jobs")
    op.drop_index("ix_proposal_call_ingest_jobs_document_id", table_name="proposal_call_ingest_jobs")
    op.drop_index("ix_proposal_call_ingest_jobs_library_entry_id", table_name="proposal_call_ingest_jobs")
    op.drop_table("proposal_call_ingest_jobs")
