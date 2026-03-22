"""add teaching progress report attachments

Revision ID: 20260322_0058
Revises: 20260321_0057
Create Date: 2026-03-22 12:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260322_0058"
down_revision = "20260321_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teaching_progress_reports",
        sa.Column(
            "attachment_document_keys",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("teaching_progress_reports", "attachment_document_keys")
