"""bibliography concepts

Revision ID: 20260328_0082
Revises: 20260328_0081
Create Date: 2026-03-28 13:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260328_0082"
down_revision = "20260328_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bibliography_concepts",
        sa.Column("label", sa.String(length=96), nullable=False),
        sa.Column("slug", sa.String(length=96), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("label", name="uq_bibliography_concepts_label"),
        sa.UniqueConstraint("slug", name="uq_bibliography_concepts_slug"),
    )
    op.create_index("ix_biblio_concepts_label", "bibliography_concepts", ["label"], unique=False)
    op.create_index("ix_biblio_concepts_slug", "bibliography_concepts", ["slug"], unique=False)

    op.create_table(
        "bibliography_reference_concepts",
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["reference_id"], ["bibliography_references.id"], ondelete="CASCADE", name="fk_biblio_ref_concepts_ref"),
        sa.ForeignKeyConstraint(["concept_id"], ["bibliography_concepts.id"], ondelete="CASCADE", name="fk_biblio_ref_concepts_concept"),
        sa.PrimaryKeyConstraint("reference_id", "concept_id", name="pk_biblio_ref_concepts"),
    )


def downgrade() -> None:
    op.drop_table("bibliography_reference_concepts")
    op.drop_index("ix_biblio_concepts_slug", table_name="bibliography_concepts")
    op.drop_index("ix_biblio_concepts_label", table_name="bibliography_concepts")
    op.drop_table("bibliography_concepts")
