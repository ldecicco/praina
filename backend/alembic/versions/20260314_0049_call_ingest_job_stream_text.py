"""add stream text to proposal call ingest jobs

Revision ID: 20260314_0049
Revises: 20260314_0048
Create Date: 2026-03-14 18:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0049"
down_revision = "20260314_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposal_call_ingest_jobs", sa.Column("stream_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposal_call_ingest_jobs", "stream_text")
