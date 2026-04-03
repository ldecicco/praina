"""add research note action status

Revision ID: 20260403_0104
Revises: 20260403_0103
Create Date: 2026-04-03 22:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260403_0104"
down_revision = "20260403_0103"
branch_labels = None
depends_on = None


action_status = postgresql.ENUM("open", "doing", "done", name="research_note_action_status")


def upgrade() -> None:
    action_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "research_note_action_items",
        sa.Column(
            "status",
            action_status,
            nullable=False,
            server_default="open",
        ),
    )
    op.create_index(
        op.f("ix_research_note_action_items_status"),
        "research_note_action_items",
        ["status"],
        unique=False,
    )
    op.execute(
        "UPDATE research_note_action_items "
        "SET status = CASE WHEN is_done THEN 'done' ELSE 'open' END::research_note_action_status"
    )
    op.alter_column("research_note_action_items", "status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_research_note_action_items_status"), table_name="research_note_action_items")
    op.drop_column("research_note_action_items", "status")
    action_status.drop(op.get_bind(), checkfirst=True)
