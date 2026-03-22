"""add course deadline policy

Revision ID: 20260321_0056
Revises: 20260321_0055
Create Date: 2026-03-21 22:35:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260321_0056"
down_revision = "20260321_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("has_project_deadlines", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("courses", "has_project_deadlines")
