"""vector dimension change (1536 -> 2560) and HNSW indices

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
    # Change embedding dimension from 1536 to 768 (nomic-embed-text)
    # Must drop and recreate since pgvector Vector type is fixed-width
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(2560)")

    op.execute("ALTER TABLE meeting_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE meeting_chunks ADD COLUMN embedding vector(2560)")

    # Create HNSW indices for cosine similarity search
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meeting_chunks_embedding "
        "ON meeting_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_meeting_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")

    op.execute("ALTER TABLE meeting_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE meeting_chunks ADD COLUMN embedding vector(1536)")

    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(1536)")
