"""add paper authors to research collections

Revision ID: 20260328_0084
Revises: 20260328_0083
Create Date: 2026-03-28 18:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260328_0084"
down_revision = "20260328_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_collections",
        sa.Column(
            "paper_authors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute("UPDATE research_collections SET paper_authors = '[]'::jsonb WHERE paper_authors IS NULL")
    op.alter_column("research_collections", "paper_authors", server_default=None)


def downgrade() -> None:
    op.drop_column("research_collections", "paper_authors")
