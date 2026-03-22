"""add teaching chunks for retrieval

Revision ID: 20260322_0062
Revises: 20260322_0061
Create Date: 2026-03-22 19:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260322_0062"
down_revision = "20260322_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teaching_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_index(op.f("ix_teaching_chunks_source_type"), "teaching_chunks", ["source_type"], unique=False)
    op.create_index(op.f("ix_teaching_chunks_source_id"), "teaching_chunks", ["source_id"], unique=False)
    op.create_index(op.f("ix_teaching_chunks_project_id"), "teaching_chunks", ["project_id"], unique=False)
    op.execute("ALTER TABLE teaching_chunks ADD COLUMN embedding vector(768)")


def downgrade() -> None:
    op.drop_index(op.f("ix_teaching_chunks_project_id"), table_name="teaching_chunks")
    op.drop_index(op.f("ix_teaching_chunks_source_id"), table_name="teaching_chunks")
    op.drop_index(op.f("ix_teaching_chunks_source_type"), table_name="teaching_chunks")
    op.drop_table("teaching_chunks")
