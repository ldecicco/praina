"""switch embedding vectors to 768 dimensions for nomic-embed-text-v2-moe

Revision ID: 20260311_0037
Revises: 20260311_0036
Create Date: 2026-03-11 19:30:00
"""

from alembic import op


revision = "20260311_0037"
down_revision = "20260311_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_research_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_meeting_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")

    op.execute("ALTER TABLE research_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE research_chunks ADD COLUMN embedding vector(768)")

    op.execute("ALTER TABLE meeting_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE meeting_chunks ADD COLUMN embedding vector(768)")

    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(768)")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meeting_chunks_embedding "
        "ON meeting_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_research_chunks_embedding "
        "ON research_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_research_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_meeting_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")

    op.execute("ALTER TABLE research_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE research_chunks ADD COLUMN embedding vector(2560)")

    op.execute("ALTER TABLE meeting_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE meeting_chunks ADD COLUMN embedding vector(2560)")

    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE document_chunks ADD COLUMN embedding vector(2560)")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meeting_chunks_embedding "
        "ON meeting_chunks USING hnsw (embedding vector_cosine_ops)"
    )
