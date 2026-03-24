"""vector dimension change (1536 -> 2560)

Revision ID: 20260311_0035
Revises: 20260310_0034
Create Date: 2026-03-11 10:00:00
"""

from alembic import op


revision = "20260311_0035"
down_revision = "20260310_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change embedding dimension from 1536 to 2560.
    # pgvector HNSW indices do not support vectors above 2000 dimensions,
    # so this migration intentionally does not create ANN indices.
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(2560)")

    op.execute("ALTER TABLE meeting_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE meeting_chunks ADD COLUMN embedding vector(2560)")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_meeting_chunks_embedding")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_meeting_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")

    op.execute("ALTER TABLE meeting_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE meeting_chunks ADD COLUMN embedding vector(1536)")

    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1536)")
