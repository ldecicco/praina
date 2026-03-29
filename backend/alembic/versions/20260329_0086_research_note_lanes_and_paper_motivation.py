"""add research note lanes and paper motivation

Revision ID: 20260329_0086
Revises: 20260329_0085
Create Date: 2026-03-29 09:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260329_0086"
down_revision = "20260329_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_notes", sa.Column("lane", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_research_notes_lane"), "research_notes", ["lane"], unique=False)
    op.add_column("research_collections", sa.Column("paper_motivation", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("research_collections", "paper_motivation")
    op.drop_index(op.f("ix_research_notes_lane"), table_name="research_notes")
    op.drop_column("research_notes", "lane")
