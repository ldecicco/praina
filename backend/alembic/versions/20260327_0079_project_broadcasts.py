"""project broadcasts

Revision ID: 20260327_0079
Revises: 20260326_0078
Create Date: 2026-03-27 14:25:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260327_0079"
down_revision = "20260326_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_broadcasts",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("deliver_telegram", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_broadcasts_project_id", "project_broadcasts", ["project_id"], unique=False)
    op.create_index("ix_project_broadcasts_author_user_id", "project_broadcasts", ["author_user_id"], unique=False)
    op.create_index("ix_project_broadcasts_severity", "project_broadcasts", ["severity"], unique=False)

    op.create_table(
        "project_broadcast_recipients",
        sa.Column("broadcast_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["broadcast_id"], ["project_broadcasts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broadcast_id", "user_id", name="uq_project_broadcast_recipient"),
    )
    op.create_index("ix_project_broadcast_recipients_broadcast_id", "project_broadcast_recipients", ["broadcast_id"], unique=False)
    op.create_index("ix_project_broadcast_recipients_user_id", "project_broadcast_recipients", ["user_id"], unique=False)
    op.create_index("ix_project_broadcast_recipients_notification_id", "project_broadcast_recipients", ["notification_id"], unique=False)

    op.alter_column("project_broadcasts", "body", server_default=None)
    op.alter_column("project_broadcasts", "severity", server_default=None)
    op.alter_column("project_broadcasts", "deliver_telegram", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_project_broadcast_recipients_notification_id", table_name="project_broadcast_recipients")
    op.drop_index("ix_project_broadcast_recipients_user_id", table_name="project_broadcast_recipients")
    op.drop_index("ix_project_broadcast_recipients_broadcast_id", table_name="project_broadcast_recipients")
    op.drop_table("project_broadcast_recipients")

    op.drop_index("ix_project_broadcasts_severity", table_name="project_broadcasts")
    op.drop_index("ix_project_broadcasts_author_user_id", table_name="project_broadcasts")
    op.drop_index("ix_project_broadcasts_project_id", table_name="project_broadcasts")
    op.drop_table("project_broadcasts")
