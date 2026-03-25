"""teaching background materials and equipment materials

Revision ID: 20260325_0066
Revises: 20260324_0065
Create Date: 2026-03-25 11:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260325_0066"
down_revision = "20260324_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teaching_project_background_materials",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_type", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_key", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_url", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teaching_project_background_materials_project_id",
        "teaching_project_background_materials",
        ["project_id"],
    )
    op.create_index(
        "ix_teaching_project_background_materials_material_type",
        "teaching_project_background_materials",
        ["material_type"],
    )
    op.create_index(
        "ix_teaching_project_background_materials_document_key",
        "teaching_project_background_materials",
        ["document_key"],
    )

    op.create_table(
        "equipment_materials",
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("external_url", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_equipment_materials_equipment_id", "equipment_materials", ["equipment_id"])
    op.create_index("ix_equipment_materials_material_type", "equipment_materials", ["material_type"])


def downgrade() -> None:
    op.drop_index("ix_equipment_materials_material_type", table_name="equipment_materials")
    op.drop_index("ix_equipment_materials_equipment_id", table_name="equipment_materials")
    op.drop_table("equipment_materials")

    op.drop_index(
        "ix_teaching_project_background_materials_document_key",
        table_name="teaching_project_background_materials",
    )
    op.drop_index(
        "ix_teaching_project_background_materials_material_type",
        table_name="teaching_project_background_materials",
    )
    op.drop_index(
        "ix_teaching_project_background_materials_project_id",
        table_name="teaching_project_background_materials",
    )
    op.drop_table("teaching_project_background_materials")
