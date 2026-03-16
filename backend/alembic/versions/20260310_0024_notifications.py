"""notifications table

Revision ID: 20260310_0024
Revises: 20260309_0023
Create Date: 2026-03-10 10:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20260310_0024"
down_revision = "20260309_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("channel", sa.String(16), nullable=False, server_default="in_app"),
        sa.Column("status", sa.String(16), nullable=False, server_default="unread", index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("link_type", sa.String(64), nullable=True),
        sa.Column("link_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notifications")
