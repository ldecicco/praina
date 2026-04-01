"""suggestion category

Revision ID: 20260401_0097
Revises: 20260401_0096
Create Date: 2026-04-01 20:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0097"
down_revision = "20260401_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_suggestions",
        sa.Column("category", sa.String(length=16), nullable=False, server_default="feature"),
    )
    op.create_index(op.f("ix_user_suggestions_category"), "user_suggestions", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_suggestions_category"), table_name="user_suggestions")
    op.drop_column("user_suggestions", "category")
