"""extend research collections with output context and meeting links

Revision ID: 20260312_0038
Revises: 20260311_0037
Create Date: 2026-03-12 11:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID


revision = "20260312_0038"
down_revision = "20260311_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE note_type ADD VALUE IF NOT EXISTS 'discussion'"
    )
    op.execute(
        "ALTER TYPE note_type ADD VALUE IF NOT EXISTS 'decision'"
    )
    op.execute(
        "ALTER TYPE note_type ADD VALUE IF NOT EXISTS 'action_item'"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE research_output_status AS ENUM "
        "('not_started', 'drafting', 'internal_review', 'submitted', 'published'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    output_status = ENUM(
        "not_started",
        "drafting",
        "internal_review",
        "submitted",
        "published",
        name="research_output_status",
        create_type=False,
    )

    op.add_column(
        "research_collections",
        sa.Column("open_questions", JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "research_collections",
        sa.Column("overleaf_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "research_collections",
        sa.Column("target_output_title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "research_collections",
        sa.Column("output_status", output_status, nullable=False, server_default="not_started"),
    )
    op.create_index(
        "ix_research_collections_output_status",
        "research_collections",
        ["output_status"],
        unique=False,
    )

    op.create_table(
        "research_collection_meetings",
        sa.Column(
            "collection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research_collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "meeting_id",
            UUID(as_uuid=True),
            sa.ForeignKey("meeting_records.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("research_collection_meetings")
    op.drop_index("ix_research_collections_output_status", table_name="research_collections")
    op.drop_column("research_collections", "output_status")
    op.drop_column("research_collections", "target_output_title")
    op.drop_column("research_collections", "overleaf_url")
    op.drop_column("research_collections", "open_questions")
    op.execute("DROP TYPE IF EXISTS research_output_status")
