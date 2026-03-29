"""research collection paper workspace

Revision ID: 20260328_0083
Revises: 20260328_0082
Create Date: 2026-03-28 14:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260328_0083"
down_revision = "20260328_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_collections", sa.Column("target_venue", sa.String(length=255), nullable=True))
    op.add_column("research_collections", sa.Column("registration_deadline", sa.Date(), nullable=True))
    op.add_column("research_collections", sa.Column("submission_deadline", sa.Date(), nullable=True))
    op.add_column("research_collections", sa.Column("decision_date", sa.Date(), nullable=True))
    op.add_column(
        "research_collections",
        sa.Column("paper_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "research_collections",
        sa.Column("paper_claims", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "research_collections",
        sa.Column("paper_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.alter_column("research_collections", "paper_questions", server_default=None)
    op.alter_column("research_collections", "paper_claims", server_default=None)
    op.alter_column("research_collections", "paper_sections", server_default=None)


def downgrade() -> None:
    op.drop_column("research_collections", "paper_sections")
    op.drop_column("research_collections", "paper_claims")
    op.drop_column("research_collections", "paper_questions")
    op.drop_column("research_collections", "decision_date")
    op.drop_column("research_collections", "submission_deadline")
    op.drop_column("research_collections", "registration_deadline")
    op.drop_column("research_collections", "target_venue")
