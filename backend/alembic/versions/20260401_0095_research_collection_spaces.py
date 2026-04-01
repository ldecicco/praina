"""research collection spaces

Revision ID: 20260401_0095
Revises: 20260401_0094
Create Date: 2026-04-01 13:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260401_0095"
down_revision = "20260401_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_collection_spaces",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_collections.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_spaces.id", ondelete="CASCADE"), primary_key=True, nullable=False),
    )
    op.execute(
        """
        INSERT INTO research_collection_spaces (collection_id, space_id)
        SELECT id, research_space_id
        FROM research_collections
        WHERE research_space_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_table("research_collection_spaces")
