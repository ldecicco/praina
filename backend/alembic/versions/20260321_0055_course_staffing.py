"""add course staffing

Revision ID: 20260321_0055
Revises: 20260321_0054
Create Date: 2026-03-21 22:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260321_0055"
down_revision = "20260321_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("teacher_user_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_courses_teacher_user_id", "courses", ["teacher_user_id"])
    op.create_foreign_key(
        "fk_courses_teacher_user_id",
        "courses",
        "user_accounts",
        ["teacher_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "course_teaching_assistants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_teaching_assistant"),
    )
    op.create_index("ix_course_teaching_assistants_course_id", "course_teaching_assistants", ["course_id"])
    op.create_index("ix_course_teaching_assistants_user_id", "course_teaching_assistants", ["user_id"])

    op.add_column("teaching_project_profiles", sa.Column("responsible_user_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_teaching_project_profiles_responsible_user_id", "teaching_project_profiles", ["responsible_user_id"])
    op.create_foreign_key(
        "fk_teaching_project_profiles_responsible_user_id",
        "teaching_project_profiles",
        "user_accounts",
        ["responsible_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("teaching_project_assessments", sa.Column("grader_user_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_teaching_project_assessments_grader_user_id", "teaching_project_assessments", ["grader_user_id"])
    op.create_foreign_key(
        "fk_teaching_project_assessments_grader_user_id",
        "teaching_project_assessments",
        "user_accounts",
        ["grader_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE teaching_project_profiles tp
        SET responsible_user_id = tm.user_account_id
        FROM team_members tm
        WHERE tp.responsible_member_id = tm.id
          AND tm.user_account_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE teaching_project_assessments ta
        SET grader_user_id = tm.user_account_id
        FROM team_members tm
        WHERE ta.grader_member_id = tm.id
          AND tm.user_account_id IS NOT NULL
        """
    )

    op.drop_constraint("teaching_project_profiles_responsible_member_id_fkey", "teaching_project_profiles", type_="foreignkey")
    op.drop_column("teaching_project_profiles", "responsible_member_id")

    op.drop_constraint("teaching_project_assessments_grader_member_id_fkey", "teaching_project_assessments", type_="foreignkey")
    op.drop_column("teaching_project_assessments", "grader_member_id")


def downgrade() -> None:
    op.add_column("teaching_project_profiles", sa.Column("responsible_member_id", UUID(as_uuid=True), nullable=True))
    op.add_column("teaching_project_assessments", sa.Column("grader_member_id", UUID(as_uuid=True), nullable=True))

    op.drop_constraint("fk_teaching_project_profiles_responsible_user_id", "teaching_project_profiles", type_="foreignkey")
    op.drop_index("ix_teaching_project_profiles_responsible_user_id", table_name="teaching_project_profiles")
    op.drop_column("teaching_project_profiles", "responsible_user_id")

    op.drop_constraint("fk_teaching_project_assessments_grader_user_id", "teaching_project_assessments", type_="foreignkey")
    op.drop_index("ix_teaching_project_assessments_grader_user_id", table_name="teaching_project_assessments")
    op.drop_column("teaching_project_assessments", "grader_user_id")

    op.drop_index("ix_course_teaching_assistants_user_id", table_name="course_teaching_assistants")
    op.drop_index("ix_course_teaching_assistants_course_id", table_name="course_teaching_assistants")
    op.drop_table("course_teaching_assistants")

    op.drop_constraint("fk_courses_teacher_user_id", "courses", type_="foreignkey")
    op.drop_index("ix_courses_teacher_user_id", table_name="courses")
    op.drop_column("courses", "teacher_user_id")
