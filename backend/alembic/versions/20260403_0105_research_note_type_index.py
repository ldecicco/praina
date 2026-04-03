"""add index research note type

Revision ID: 20260403_0105
Revises: 20260403_0104
Create Date: 2026-04-03 20:20:00.000000
"""

from alembic import op


revision = "20260403_0105"
down_revision = "20260403_0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE note_type ADD VALUE IF NOT EXISTS 'index'")


def downgrade() -> None:
    pass
