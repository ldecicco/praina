"""fix missing timestamp defaults

Revision ID: 20260309_0021
Revises: 20260309_0020
Create Date: 2026-03-09 18:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260309_0021"
down_revision = "20260309_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE meeting_records SET created_at = now() WHERE created_at IS NULL")
    op.execute("UPDATE meeting_records SET updated_at = now() WHERE updated_at IS NULL")
    op.alter_column("meeting_records", "created_at", server_default=sa.text("now()"))
    op.alter_column("meeting_records", "updated_at", server_default=sa.text("now()"))

    op.execute("UPDATE deliverable_review_findings SET created_at = now() WHERE created_at IS NULL")
    op.execute("UPDATE deliverable_review_findings SET updated_at = now() WHERE updated_at IS NULL")
    op.alter_column("deliverable_review_findings", "created_at", server_default=sa.text("now()"))
    op.alter_column("deliverable_review_findings", "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    op.alter_column("deliverable_review_findings", "updated_at", server_default=None)
    op.alter_column("deliverable_review_findings", "created_at", server_default=None)
    op.alter_column("meeting_records", "updated_at", server_default=None)
    op.alter_column("meeting_records", "created_at", server_default=None)
