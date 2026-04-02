"""add to_review reading status

Revision ID: 20260401_0099
Revises: 20260401_0098
Create Date: 2026-04-01 22:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260401_0099"
down_revision = "20260401_0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE reading_status ADD VALUE IF NOT EXISTS 'to_review'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; leave as is.
    pass
