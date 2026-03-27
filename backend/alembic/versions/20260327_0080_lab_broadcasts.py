"""lab broadcasts

Revision ID: 20260327_0080
Revises: 20260327_0079
Create Date: 2026-03-27 13:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260327_0080"
down_revision = "20260327_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_broadcasts",
        sa.Column("lab_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_project_broadcasts_lab_id", "project_broadcasts", ["lab_id"])
    op.create_foreign_key(
        "fk_project_broadcasts_lab_id",
        "project_broadcasts",
        "labs",
        ["lab_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("project_broadcasts", "project_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("project_broadcasts", "project_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("fk_project_broadcasts_lab_id", "project_broadcasts", type_="foreignkey")
    op.drop_index("ix_project_broadcasts_lab_id", table_name="project_broadcasts")
    op.drop_column("project_broadcasts", "lab_id")
