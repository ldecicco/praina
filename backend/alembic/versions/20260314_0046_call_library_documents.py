"""call library documents

Revision ID: 20260314_0046
Revises: 20260314_0045
Create Date: 2026-03-14 10:45:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260314_0046"
down_revision = "20260314_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_call_library_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "library_entry_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proposal_call_library_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_proposal_call_library_documents_library_entry_id",
        "proposal_call_library_documents",
        ["library_entry_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_proposal_call_library_documents_library_entry_id", table_name="proposal_call_library_documents")
    op.drop_table("proposal_call_library_documents")
