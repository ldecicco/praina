"""bibliography document pipeline

Revision ID: 20260325_0069
Revises: 20260325_0068
Create Date: 2026-03-25 22:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260325_0069"
down_revision = "20260325_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bibliography_references", sa.Column("source_project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("bibliography_references", sa.Column("document_key", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_bibliography_references_source_project_id"), "bibliography_references", ["source_project_id"], unique=False)
    op.create_index(op.f("ix_bibliography_references_document_key"), "bibliography_references", ["document_key"], unique=False)
    op.create_foreign_key(
        "fk_bibliography_references_source_project_id",
        "bibliography_references",
        "projects",
        ["source_project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_bibliography_references_source_project_id", "bibliography_references", type_="foreignkey")
    op.drop_index(op.f("ix_bibliography_references_document_key"), table_name="bibliography_references")
    op.drop_index(op.f("ix_bibliography_references_source_project_id"), table_name="bibliography_references")
    op.drop_column("bibliography_references", "document_key")
    op.drop_column("bibliography_references", "source_project_id")
