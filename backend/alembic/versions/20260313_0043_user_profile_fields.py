"""user profile fields

Revision ID: 20260313_0043
Revises: 20260313_0042
Create Date: 2026-03-13 18:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260313_0043"
down_revision = "20260313_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_accounts", sa.Column("job_title", sa.String(120), nullable=True))
    op.add_column("user_accounts", sa.Column("organization", sa.String(160), nullable=True))
    op.add_column("user_accounts", sa.Column("phone", sa.String(40), nullable=True))
    op.add_column("user_accounts", sa.Column("avatar_path", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("user_accounts", "avatar_path")
    op.drop_column("user_accounts", "phone")
    op.drop_column("user_accounts", "organization")
    op.drop_column("user_accounts", "job_title")
