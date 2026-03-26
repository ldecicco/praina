"""add bibliography notes and per-user reading status

Revision ID: 20260326_0075
Revises: 20260326_0074
Create Date: 2026-03-26 20:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260326_0075"
down_revision = "20260326_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bibliography_notes",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("bibliography_reference_id", sa.UUID(as_uuid=True), sa.ForeignKey("bibliography_references.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("note_type", sa.String(32), nullable=False, server_default="comment", index=True),
        sa.Column("visibility", postgresql.ENUM("private", "shared", name="bibliography_visibility", create_type=False), nullable=False, server_default="shared"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "bibliography_user_status",
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bibliography_reference_id", sa.UUID(as_uuid=True), sa.ForeignKey("bibliography_references.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reading_status", sa.String(32), nullable=False, server_default="unread"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bibliography_user_status")
    op.drop_table("bibliography_notes")
