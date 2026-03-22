"""normalize teaching courses

Revision ID: 20260321_0054
Revises: 20260321_0053
Create Date: 2026-03-21 20:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260321_0054"
down_revision = "20260321_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_courses_code"),
    )
    op.create_index("ix_courses_code", "courses", ["code"])
    op.create_index("ix_courses_title", "courses", ["title"])
    op.create_index("ix_courses_is_active", "courses", ["is_active"])

    op.add_column("teaching_project_profiles", sa.Column("course_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_teaching_project_profiles_course_id", "teaching_project_profiles", ["course_id"])
    op.create_foreign_key(
        "fk_teaching_project_profiles_course_id",
        "teaching_project_profiles",
        "courses",
        ["course_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        INSERT INTO courses (id, code, title, is_active)
        SELECT gen_random_uuid(),
               COALESCE(NULLIF(course_code, ''), 'COURSE-' || substr(project_id::text, 1, 8)),
               COALESCE(NULLIF(course_name, ''), COALESCE(NULLIF(course_code, ''), 'Untitled course')),
               true
        FROM (
            SELECT DISTINCT course_code, course_name, project_id
            FROM teaching_project_profiles
            WHERE course_code IS NOT NULL OR course_name IS NOT NULL
        ) src
        ON CONFLICT (code) DO NOTHING
        """
    )

    op.execute(
        """
        UPDATE teaching_project_profiles tp
        SET course_id = c.id
        FROM courses c
        WHERE tp.course_id IS NULL
          AND c.code = COALESCE(NULLIF(tp.course_code, ''), 'COURSE-' || substr(tp.project_id::text, 1, 8))
        """
    )

    op.drop_column("teaching_project_profiles", "course_name")
    op.drop_column("teaching_project_profiles", "course_code")


def downgrade() -> None:
    op.add_column("teaching_project_profiles", sa.Column("course_code", sa.String(length=64), nullable=True))
    op.add_column("teaching_project_profiles", sa.Column("course_name", sa.String(length=255), nullable=True))

    op.execute(
        """
        UPDATE teaching_project_profiles tp
        SET course_code = c.code,
            course_name = c.title
        FROM courses c
        WHERE tp.course_id = c.id
        """
    )

    op.drop_constraint("fk_teaching_project_profiles_course_id", "teaching_project_profiles", type_="foreignkey")
    op.drop_index("ix_teaching_project_profiles_course_id", table_name="teaching_project_profiles")
    op.drop_column("teaching_project_profiles", "course_id")

    op.drop_index("ix_courses_is_active", table_name="courses")
    op.drop_index("ix_courses_title", table_name="courses")
    op.drop_index("ix_courses_code", table_name="courses")
    op.drop_table("courses")
