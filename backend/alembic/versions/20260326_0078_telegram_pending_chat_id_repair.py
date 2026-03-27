"""telegram pending chat id repair

Revision ID: 20260326_0078
Revises: 20260326_0077
Create Date: 2026-03-26 23:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0078"
down_revision = "20260326_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "telegram_pending_chat_id" not in columns:
        op.add_column("user_accounts", sa.Column("telegram_pending_chat_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "telegram_pending_chat_id" in columns:
        op.drop_column("user_accounts", "telegram_pending_chat_id")
