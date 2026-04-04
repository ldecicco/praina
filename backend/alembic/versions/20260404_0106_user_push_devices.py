"""user push devices

Revision ID: 20260404_0106
Revises: 20260403_0105
Create Date: 2026-04-04 18:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260404_0106"
down_revision = "20260403_0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_push_devices",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("token", sa.String(length=1024), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=True),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_user_push_devices_user_id", "user_push_devices", ["user_id"], unique=False)
    op.create_index("ix_user_push_devices_platform", "user_push_devices", ["platform"], unique=False)
    op.create_index("ix_user_push_devices_device_id", "user_push_devices", ["device_id"], unique=False)
    op.create_index("ix_user_push_devices_last_seen_at", "user_push_devices", ["last_seen_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_push_devices_last_seen_at", table_name="user_push_devices")
    op.drop_index("ix_user_push_devices_device_id", table_name="user_push_devices")
    op.drop_index("ix_user_push_devices_platform", table_name="user_push_devices")
    op.drop_index("ix_user_push_devices_user_id", table_name="user_push_devices")
    op.drop_table("user_push_devices")
