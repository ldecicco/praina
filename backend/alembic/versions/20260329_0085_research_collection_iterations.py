"""add study iterations to research collections

Revision ID: 20260329_0085
Revises: 20260328_0084
Create Date: 2026-03-29 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260329_0085"
down_revision = "20260328_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_collections",
        sa.Column(
            "study_iterations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute("UPDATE research_collections SET study_iterations = '[]'::jsonb WHERE study_iterations IS NULL")
    op.alter_column("research_collections", "study_iterations", server_default=None)


def downgrade() -> None:
    op.drop_column("research_collections", "study_iterations")
