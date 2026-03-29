"""research collection results

Revision ID: 20260329_0087
Revises: 20260329_0086
Create Date: 2026-03-29 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260329_0087"
down_revision = "20260329_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_collections",
        sa.Column(
            "study_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute("UPDATE research_collections SET study_results = '[]'::jsonb WHERE study_results IS NULL")
    op.alter_column("research_collections", "study_results", server_default=None)


def downgrade() -> None:
    op.drop_column("research_collections", "study_results")
