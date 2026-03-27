"""telegram notifications and linking

Revision ID: 20260326_0077
Revises: 20260326_0076
Create Date: 2026-03-26 22:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0077"
down_revision = "20260326_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_accounts", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
    op.add_column("user_accounts", sa.Column("telegram_pending_chat_id", sa.String(length=64), nullable=True))
    op.add_column("user_accounts", sa.Column("telegram_username", sa.String(length=128), nullable=True))
    op.add_column("user_accounts", sa.Column("telegram_first_name", sa.String(length=128), nullable=True))
    op.add_column("user_accounts", sa.Column("telegram_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_accounts", sa.Column("telegram_link_code", sa.String(length=64), nullable=True))
    op.add_column("user_accounts", sa.Column("telegram_link_code_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_user_accounts_telegram_chat_id", "user_accounts", ["telegram_chat_id"], unique=True)
    op.create_index("ix_user_accounts_telegram_link_code", "user_accounts", ["telegram_link_code"], unique=False)
    op.alter_column("user_accounts", "telegram_notifications_enabled", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_user_accounts_telegram_link_code", table_name="user_accounts")
    op.drop_index("ix_user_accounts_telegram_chat_id", table_name="user_accounts")
    op.drop_column("user_accounts", "telegram_link_code_expires_at")
    op.drop_column("user_accounts", "telegram_link_code")
    op.drop_column("user_accounts", "telegram_notifications_enabled")
    op.drop_column("user_accounts", "telegram_first_name")
    op.drop_column("user_accounts", "telegram_username")
    op.drop_column("user_accounts", "telegram_pending_chat_id")
    op.drop_column("user_accounts", "telegram_chat_id")
