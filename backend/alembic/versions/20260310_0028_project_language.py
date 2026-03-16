"""project language setting

Revision ID: 20260310_0028
Revises: 20260310_0027
Create Date: 2026-03-10 03:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0028"
down_revision = "20260310_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("language", sa.String(8), nullable=False, server_default="en_GB"),
    )


def downgrade() -> None:
    op.drop_column("projects", "language")
