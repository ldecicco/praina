"""add research note starred flag

Revision ID: 20260403_0101
Revises: 20260403_0100
Create Date: 2026-04-03 14:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260403_0101"
down_revision = "20260403_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_notes",
        sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(op.f("ix_research_notes_starred"), "research_notes", ["starred"], unique=False)
    op.alter_column("research_notes", "starred", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_research_notes_starred"), table_name="research_notes")
    op.drop_column("research_notes", "starred")
