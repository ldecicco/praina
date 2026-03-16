"""add project_mode column

Revision ID: 20260310_0033
Revises: 20260310_0032
Create Date: 2026-03-10 18:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0033"
down_revision = "20260310_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("project_mode", sa.String(16), nullable=False, server_default="execution"),
    )


def downgrade() -> None:
    op.drop_column("projects", "project_mode")
