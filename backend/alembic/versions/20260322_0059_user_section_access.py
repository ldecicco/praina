"""add user section access flags

Revision ID: 20260322_0059
Revises: 20260322_0058
Create Date: 2026-03-22 14:10:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260322_0059"
down_revision = "20260322_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_accounts", sa.Column("can_access_research", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("user_accounts", sa.Column("can_access_teaching", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("user_accounts", "can_access_teaching")
    op.drop_column("user_accounts", "can_access_research")
