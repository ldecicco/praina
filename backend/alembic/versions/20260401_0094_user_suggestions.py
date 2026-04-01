"""user suggestions

Revision ID: 20260401_0094
Revises: 20260401_0093
Create Date: 2026-04-01 23:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260401_0094"
down_revision = "20260401_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_suggestions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_suggestions_status"), "user_suggestions", ["status"], unique=False)
    op.create_index(op.f("ix_user_suggestions_user_id"), "user_suggestions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_suggestions_user_id"), table_name="user_suggestions")
    op.drop_index(op.f("ix_user_suggestions_status"), table_name="user_suggestions")
    op.drop_table("user_suggestions")
