"""proposal images

Revision ID: 20260313_0041
Revises: 20260313_0040
Create Date: 2026-03-13 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260313_0041"
down_revision = "20260313_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposal_images_project_id", "proposal_images", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_proposal_images_project_id", table_name="proposal_images")
    op.drop_table("proposal_images")
