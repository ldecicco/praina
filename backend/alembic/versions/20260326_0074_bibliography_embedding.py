"""add embedding column to bibliography_references

Revision ID: 20260326_0074
Revises: 20260326_0073
Create Date: 2026-03-26 19:00:00
"""

from alembic import op

revision = "20260326_0074"
down_revision = "20260326_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE bibliography_references ADD COLUMN IF NOT EXISTS embedding vector(768)")


def downgrade() -> None:
    op.drop_column("bibliography_references", "embedding")
