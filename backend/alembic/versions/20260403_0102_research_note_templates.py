"""add research note templates

Revision ID: 20260403_0102
Revises: 20260403_0101
Create Date: 2026-04-03 18:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260403_0102"
down_revision = "20260403_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    note_type_enum = postgresql.ENUM(
        "observation",
        "discussion",
        "finding",
        "hypothesis",
        "method",
        "decision",
        "action_item",
        "literature_review",
        "conclusion",
        name="note_type",
        create_type=False,
    )
    op.create_table(
        "research_note_templates",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("lane", sa.String(length=32), nullable=True),
        sa.Column("note_type", note_type_enum, nullable=False, server_default="observation"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_note_templates_name"), "research_note_templates", ["name"], unique=False)
    op.create_index(op.f("ix_research_note_templates_lane"), "research_note_templates", ["lane"], unique=False)
    op.create_index(op.f("ix_research_note_templates_note_type"), "research_note_templates", ["note_type"], unique=False)
    op.create_index(op.f("ix_research_note_templates_is_system"), "research_note_templates", ["is_system"], unique=False)
    op.create_index(op.f("ix_research_note_templates_created_by_user_id"), "research_note_templates", ["created_by_user_id"], unique=False)
    op.alter_column("research_note_templates", "note_type", server_default=None)
    op.alter_column("research_note_templates", "tags", server_default=None)
    op.alter_column("research_note_templates", "is_system", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_research_note_templates_created_by_user_id"), table_name="research_note_templates")
    op.drop_index(op.f("ix_research_note_templates_is_system"), table_name="research_note_templates")
    op.drop_index(op.f("ix_research_note_templates_note_type"), table_name="research_note_templates")
    op.drop_index(op.f("ix_research_note_templates_lane"), table_name="research_note_templates")
    op.drop_index(op.f("ix_research_note_templates_name"), table_name="research_note_templates")
    op.drop_table("research_note_templates")
