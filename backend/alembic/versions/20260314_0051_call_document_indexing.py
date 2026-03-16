"""call document indexing state and chunks

Revision ID: 20260314_0051
Revises: 20260314_0050
Create Date: 2026-03-14 22:10:00
"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260314_0051"
down_revision = "20260314_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "proposal_call_library_documents",
        sa.Column("indexing_status", sa.String(length=32), nullable=False, server_default="uploaded"),
    )
    op.add_column(
        "proposal_call_library_documents",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proposal_call_library_documents",
        sa.Column("ingestion_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_proposal_call_library_documents_indexing_status",
        "proposal_call_library_documents",
        ["indexing_status"],
    )

    op.create_table(
        "proposal_call_library_document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proposal_call_library_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_proposal_call_library_document_chunks_document_id",
        "proposal_call_library_document_chunks",
        ["document_id"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_proposal_call_library_document_chunks_embedding "
        "ON proposal_call_library_document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_proposal_call_library_document_chunks_embedding")
    op.drop_index(
        "ix_proposal_call_library_document_chunks_document_id",
        table_name="proposal_call_library_document_chunks",
    )
    op.drop_table("proposal_call_library_document_chunks")

    op.drop_index(
        "ix_proposal_call_library_documents_indexing_status",
        table_name="proposal_call_library_documents",
    )
    op.drop_column("proposal_call_library_documents", "ingestion_error")
    op.drop_column("proposal_call_library_documents", "indexed_at")
    op.drop_column("proposal_call_library_documents", "indexing_status")
