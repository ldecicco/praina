"""add research note action items

Revision ID: 20260403_0103
Revises: 20260403_0102
Create Date: 2026-04-03 18:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260403_0103"
down_revision = "20260403_0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_note_action_items",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["user_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["note_id"], ["research_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_note_action_items_note_id"), "research_note_action_items", ["note_id"], unique=False)
    op.create_index(op.f("ix_research_note_action_items_assignee_user_id"), "research_note_action_items", ["assignee_user_id"], unique=False)
    op.create_index(op.f("ix_research_note_action_items_due_date"), "research_note_action_items", ["due_date"], unique=False)
    op.create_index(op.f("ix_research_note_action_items_is_done"), "research_note_action_items", ["is_done"], unique=False)
    op.alter_column("research_note_action_items", "is_done", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_research_note_action_items_is_done"), table_name="research_note_action_items")
    op.drop_index(op.f("ix_research_note_action_items_due_date"), table_name="research_note_action_items")
    op.drop_index(op.f("ix_research_note_action_items_assignee_user_id"), table_name="research_note_action_items")
    op.drop_index(op.f("ix_research_note_action_items_note_id"), table_name="research_note_action_items")
    op.drop_table("research_note_action_items")
