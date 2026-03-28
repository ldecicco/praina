"""bibliography ai summary

Revision ID: 20260328_0081
Revises: 20260327_0080
Create Date: 2026-03-28 09:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260328_0081"
down_revision = "20260327_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bibliography_references", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("bibliography_references", sa.Column("ai_summary_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bibliography_references", "ai_summary_at")
    op.drop_column("bibliography_references", "ai_summary")
