"""chat message cards

Revision ID: 20260308_0016
Revises: 20260308_0015
Create Date: 2026-03-08 20:30:00
"""

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

revision = "20260308_0016"
down_revision = "20260308_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("cards", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade() -> None:
    op.drop_column("chat_messages", "cards")
