"""research workspace tables

Revision ID: 20260311_0036
Revises: 20260311_0035
Create Date: 2026-03-11 14:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID, JSONB

revision = "20260311_0036"
down_revision = "20260311_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums (create via raw SQL, then reference with create_type=False) ──
    op.execute("DO $$ BEGIN CREATE TYPE collection_status AS ENUM ('active', 'archived', 'completed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE collection_member_role AS ENUM ('lead', 'contributor', 'reviewer'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE reading_status AS ENUM ('unread', 'reading', 'read', 'reviewed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE note_type AS ENUM ('observation', 'finding', 'hypothesis', 'method', 'literature_review', 'conclusion'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    collection_status = ENUM("active", "archived", "completed", name="collection_status", create_type=False)
    collection_member_role = ENUM("lead", "contributor", "reviewer", name="collection_member_role", create_type=False)
    reading_status = ENUM("unread", "reading", "read", "reviewed", name="reading_status", create_type=False)
    note_type = ENUM("observation", "finding", "hypothesis", "method", "literature_review", "conclusion", name="note_type", create_type=False)

    # ── research_collections ──
    op.create_table(
        "research_collections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("hypothesis", sa.Text, nullable=True),
        sa.Column("status", collection_status, nullable=False, server_default="active", index=True),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("created_by_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_synthesis", sa.Text, nullable=True),
        sa.Column("ai_synthesis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── research_collection_members ──
    op.create_table(
        "research_collection_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", collection_member_role, nullable=False, server_default="contributor"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("collection_id", "member_id", name="uq_collection_member"),
    )

    # ── WBS junction tables ──
    op.create_table(
        "research_collection_wps",
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("wp_id", UUID(as_uuid=True), sa.ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "research_collection_tasks",
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "research_collection_deliverables",
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("deliverable_id", UUID(as_uuid=True), sa.ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── research_references ──
    op.create_table(
        "research_references",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("authors", JSONB, server_default="[]"),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("venue", sa.String(512), nullable=True),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("url", sa.String(512), nullable=True),
        sa.Column("abstract", sa.Text, nullable=True),
        sa.Column("document_key", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("reading_status", reading_status, nullable=False, server_default="unread", index=True),
        sa.Column("added_by_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_summary_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── research_notes ──
    op.create_table(
        "research_notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("author_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("note_type", note_type, nullable=False, server_default="observation", index=True),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── research_note_references (junction) ──
    op.create_table(
        "research_note_references",
        sa.Column("note_id", UUID(as_uuid=True), sa.ForeignKey("research_notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reference_id", UUID(as_uuid=True), sa.ForeignKey("research_references.id", ondelete="CASCADE"), primary_key=True),
    )

    # ── research_annotations ──
    op.create_table(
        "research_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("reference_id", UUID(as_uuid=True), sa.ForeignKey("research_references.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("page_ref", sa.String(64), nullable=True),
        sa.Column("highlight_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── research_chunks (for RAG embeddings) ──
    op.create_table(
        "research_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(32), nullable=False, index=True),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content", sa.Text, nullable=False),
    )

    # Add embedding vector column (pgvector indexes limited to 2000 dims; at 2560 dims we rely on sequential scan)
    op.execute("ALTER TABLE research_chunks ADD COLUMN embedding vector(2560)")


def downgrade() -> None:
    op.drop_table("research_chunks")
    op.drop_table("research_annotations")
    op.drop_table("research_note_references")
    op.drop_table("research_notes")
    op.drop_table("research_references")
    op.drop_table("research_collection_deliverables")
    op.drop_table("research_collection_tasks")
    op.drop_table("research_collection_wps")
    op.drop_table("research_collection_members")
    op.drop_table("research_collections")

    op.execute("DROP TYPE IF EXISTS note_type")
    op.execute("DROP TYPE IF EXISTS reading_status")
    op.execute("DROP TYPE IF EXISTS collection_member_role")
    op.execute("DROP TYPE IF EXISTS collection_status")
