"""link teaching background materials to bibliography references

Revision ID: 20260325_0071
Revises: 20260325_0070
Create Date: 2026-03-25 22:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260325_0071"
down_revision = "20260325_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "teaching_project_background_materials",
        sa.Column("bibliography_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_teach_bg_mat_biblio_ref_id",
        "teaching_project_background_materials",
        ["bibliography_reference_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_teach_bg_mat_biblio_ref_id",
        "teaching_project_background_materials",
        "bibliography_references",
        ["bibliography_reference_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_teach_bg_mat_biblio_ref_id",
        "teaching_project_background_materials",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_teach_bg_mat_biblio_ref_id",
        table_name="teaching_project_background_materials",
    )
    op.drop_column("teaching_project_background_materials", "bibliography_reference_id")
