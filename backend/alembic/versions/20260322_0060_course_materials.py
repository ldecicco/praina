"""add course materials

Revision ID: 20260322_0060
Revises: 20260322_0059
Create Date: 2026-03-22 16:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260322_0060"
down_revision = "20260322_0059"
branch_labels = None
depends_on = None


course_material_type_column = postgresql.ENUM(
    "instructions",
    "rubric",
    "template",
    "schedule",
    "resource",
    "other",
    name="course_material_type",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'course_material_type'
            ) THEN
                CREATE TYPE course_material_type AS ENUM (
                    'instructions',
                    'rubric',
                    'template',
                    'schedule',
                    'resource',
                    'other'
                );
            END IF;
        END
        $$;
        """
    )
    op.create_table(
        "course_materials",
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("material_type", course_material_type_column, nullable=False, server_default="instructions"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("external_url", sa.String(length=512), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_course_materials_course_id"), "course_materials", ["course_id"], unique=False)
    op.create_index(op.f("ix_course_materials_material_type"), "course_materials", ["material_type"], unique=False)
    op.create_index(op.f("ix_course_materials_sort_order"), "course_materials", ["sort_order"], unique=False)
    op.create_index(op.f("ix_course_materials_title"), "course_materials", ["title"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_course_materials_title"), table_name="course_materials")
    op.drop_index(op.f("ix_course_materials_sort_order"), table_name="course_materials")
    op.drop_index(op.f("ix_course_materials_material_type"), table_name="course_materials")
    op.drop_index(op.f("ix_course_materials_course_id"), table_name="course_materials")
    op.drop_table("course_materials")
    op.execute("DROP TYPE IF EXISTS course_material_type")
