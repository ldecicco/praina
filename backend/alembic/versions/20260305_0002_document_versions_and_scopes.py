"""document versions and scoped linkage improvements

Revision ID: 20260305_0002
Revises: 20260305_0001
Create Date: 2026-03-05 20:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260305_0002"
down_revision = "20260305_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE documentscope ADD VALUE IF NOT EXISTS 'milestone'")

    op.add_column("project_documents", sa.Column("document_key", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("project_documents", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.add_column("project_documents", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("project_documents", sa.Column("uploaded_by_member_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("project_documents", sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("project_documents", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("project_documents", sa.Column("ingestion_error", sa.Text(), nullable=True))

    op.execute("UPDATE project_documents SET document_key = id WHERE document_key IS NULL")
    op.execute("UPDATE project_documents SET original_filename = title || '.bin' WHERE original_filename IS NULL")
    op.execute("UPDATE project_documents SET file_size_bytes = 0 WHERE file_size_bytes IS NULL")
    op.execute("UPDATE project_documents SET status = 'uploaded' WHERE status = 'draft' OR status IS NULL")

    op.alter_column("project_documents", "document_key", nullable=False)
    op.alter_column("project_documents", "original_filename", nullable=False)
    op.alter_column("project_documents", "file_size_bytes", nullable=False)
    op.alter_column("project_documents", "status", server_default="uploaded")

    op.create_foreign_key(
        "fk_project_documents_uploaded_by_member_id_team_members",
        "project_documents",
        "team_members",
        ["uploaded_by_member_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_project_documents_milestone_id_milestones",
        "project_documents",
        "milestones",
        ["milestone_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_project_documents_document_key"), "project_documents", ["document_key"], unique=False)
    op.create_index(op.f("ix_project_documents_milestone_id"), "project_documents", ["milestone_id"], unique=False)
    op.create_unique_constraint(
        "uq_project_documents_document_key_version", "project_documents", ["document_key", "version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_documents_document_key_version", "project_documents", type_="unique")
    op.drop_index(op.f("ix_project_documents_milestone_id"), table_name="project_documents")
    op.drop_index(op.f("ix_project_documents_document_key"), table_name="project_documents")

    op.drop_constraint(
        "fk_project_documents_milestone_id_milestones",
        "project_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_project_documents_uploaded_by_member_id_team_members",
        "project_documents",
        type_="foreignkey",
    )

    op.alter_column("project_documents", "status", server_default="draft")

    op.drop_column("project_documents", "ingestion_error")
    op.drop_column("project_documents", "indexed_at")
    op.drop_column("project_documents", "milestone_id")
    op.drop_column("project_documents", "uploaded_by_member_id")
    op.drop_column("project_documents", "file_size_bytes")
    op.drop_column("project_documents", "original_filename")
    op.drop_column("project_documents", "document_key")

