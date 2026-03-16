"""meeting chunks and indexing fields

Revision ID: 20260309_0019
Revises: 20260308_0018
Create Date: 2026-03-09 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260309_0019"
down_revision = "20260308_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meeting_records", sa.Column("indexing_status", sa.String(32), nullable=False, server_default="pending"))
    op.add_column("meeting_records", sa.Column("original_filename", sa.String(255), nullable=True))

    op.create_table(
        "meeting_chunks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("meeting_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("meeting_records.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("meeting_chunks")
    op.drop_column("meeting_records", "original_filename")
    op.drop_column("meeting_records", "indexing_status")
