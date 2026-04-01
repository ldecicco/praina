"""research study files

Revision ID: 20260401_0093
Revises: 20260401_0092
Create Date: 2026-04-01 22:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260401_0093"
down_revision = "20260401_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_study_files",
        sa.Column("research_space_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["research_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["research_space_id"], ["research_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_study_files_collection_id"), "research_study_files", ["collection_id"], unique=False)
    op.create_index(op.f("ix_research_study_files_project_id"), "research_study_files", ["project_id"], unique=False)
    op.create_index(op.f("ix_research_study_files_research_space_id"), "research_study_files", ["research_space_id"], unique=False)
    op.create_index(op.f("ix_research_study_files_uploaded_by_user_id"), "research_study_files", ["uploaded_by_user_id"], unique=False)

    op.create_table(
        "research_note_files",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["research_study_files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["note_id"], ["research_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("note_id", "file_id"),
    )


def downgrade() -> None:
    op.drop_table("research_note_files")
    op.drop_index(op.f("ix_research_study_files_uploaded_by_user_id"), table_name="research_study_files")
    op.drop_index(op.f("ix_research_study_files_research_space_id"), table_name="research_study_files")
    op.drop_index(op.f("ix_research_study_files_project_id"), table_name="research_study_files")
    op.drop_index(op.f("ix_research_study_files_collection_id"), table_name="research_study_files")
    op.drop_table("research_study_files")
