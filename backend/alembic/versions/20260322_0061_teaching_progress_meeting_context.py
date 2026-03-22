"""add teaching progress meeting context

Revision ID: 20260322_0061
Revises: 20260322_0060
Create Date: 2026-03-22 17:05:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260322_0061"
down_revision = "20260322_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teaching_progress_reports", sa.Column("meeting_date", sa.Date(), nullable=True))
    op.add_column(
        "teaching_progress_reports",
        sa.Column(
            "transcript_document_keys",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index(op.f("ix_teaching_progress_reports_meeting_date"), "teaching_progress_reports", ["meeting_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_teaching_progress_reports_meeting_date"), table_name="teaching_progress_reports")
    op.drop_column("teaching_progress_reports", "transcript_document_keys")
    op.drop_column("teaching_progress_reports", "meeting_date")
