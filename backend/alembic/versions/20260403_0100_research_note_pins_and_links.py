"""add research note pins and links

Revision ID: 20260403_0100
Revises: 20260401_0099
Create Date: 2026-04-03 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260403_0100"
down_revision = "20260401_0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_notes",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(op.f("ix_research_notes_pinned"), "research_notes", ["pinned"], unique=False)
    op.alter_column("research_notes", "pinned", server_default=None)

    op.create_table(
        "research_note_links",
        sa.Column("source_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["source_note_id"], ["research_notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_note_id"], ["research_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_note_id", "target_note_id"),
    )


def downgrade() -> None:
    op.drop_table("research_note_links")
    op.drop_index(op.f("ix_research_notes_pinned"), table_name="research_notes")
    op.drop_column("research_notes", "pinned")
