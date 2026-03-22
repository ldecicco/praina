"""teaching project support

Revision ID: 20260321_0053
Revises: 20260315_0052
Create Date: 2026-03-21 18:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID, JSONB

revision = "20260321_0053"
down_revision = "20260315_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("project_kind", sa.String(length=16), nullable=False, server_default="funded"))
    op.create_index("ix_projects_project_kind", "projects", ["project_kind"])

    op.execute("DO $$ BEGIN CREATE TYPE teaching_project_status AS ENUM ('draft', 'active', 'at_risk', 'blocked', 'completed', 'graded'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE teaching_project_health AS ENUM ('green', 'yellow', 'red'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE teaching_artifact_type AS ENUM ('report', 'repository', 'video', 'slides', 'dataset', 'other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE teaching_artifact_status AS ENUM ('missing', 'submitted', 'accepted', 'needs_revision'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE teaching_milestone_status AS ENUM ('pending', 'completed', 'missed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE teaching_blocker_severity AS ENUM ('low', 'medium', 'high'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE teaching_blocker_status AS ENUM ('open', 'monitoring', 'resolved'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    teaching_project_status = ENUM("draft", "active", "at_risk", "blocked", "completed", "graded", name="teaching_project_status", create_type=False)
    teaching_project_health = ENUM("green", "yellow", "red", name="teaching_project_health", create_type=False)
    teaching_artifact_type = ENUM("report", "repository", "video", "slides", "dataset", "other", name="teaching_artifact_type", create_type=False)
    teaching_artifact_status = ENUM("missing", "submitted", "accepted", "needs_revision", name="teaching_artifact_status", create_type=False)
    teaching_milestone_status = ENUM("pending", "completed", "missed", name="teaching_milestone_status", create_type=False)
    teaching_blocker_severity = ENUM("low", "medium", "high", name="teaching_blocker_severity", create_type=False)
    teaching_blocker_status = ENUM("open", "monitoring", "resolved", name="teaching_blocker_status", create_type=False)

    op.create_table(
        "teaching_project_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("course_code", sa.String(length=64), nullable=True),
        sa.Column("course_name", sa.String(length=255), nullable=True),
        sa.Column("academic_year", sa.String(length=32), nullable=True),
        sa.Column("term", sa.String(length=32), nullable=True),
        sa.Column("functional_objectives_markdown", sa.Text(), nullable=True),
        sa.Column("specifications_markdown", sa.Text(), nullable=True),
        sa.Column("responsible_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", teaching_project_status, nullable=False, server_default="draft"),
        sa.Column("health", teaching_project_health, nullable=False, server_default="green"),
        sa.Column("reporting_cadence_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("final_grade", sa.Float(), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teaching_project_profiles_project_id", "teaching_project_profiles", ["project_id"])

    op.create_table(
        "teaching_project_students",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teaching_project_students_project_id", "teaching_project_students", ["project_id"])

    op.create_table(
        "teaching_project_artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", teaching_artifact_type, nullable=False, server_default="other"),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", teaching_artifact_status, nullable=False, server_default="missing"),
        sa.Column("document_key", UUID(as_uuid=True), nullable=True),
        sa.Column("external_url", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teaching_project_artifacts_project_id", "teaching_project_artifacts", ["project_id"])
    op.create_index("ix_teaching_project_artifacts_document_key", "teaching_project_artifacts", ["document_key"])

    op.create_table(
        "teaching_progress_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("summary_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("completed_work", JSONB, nullable=False, server_default="[]"),
        sa.Column("current_blockers", JSONB, nullable=False, server_default="[]"),
        sa.Column("next_steps", JSONB, nullable=False, server_default="[]"),
        sa.Column("requested_support", JSONB, nullable=False, server_default="[]"),
        sa.Column("supervisor_feedback_markdown", sa.Text(), nullable=True),
        sa.Column("status_confidence", sa.String(length=32), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teaching_progress_reports_project_id", "teaching_progress_reports", ["project_id"])

    op.create_table(
        "teaching_project_milestones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", teaching_milestone_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teaching_project_milestones_project_id", "teaching_project_milestones", ["project_id"])
    op.create_index("ix_teaching_project_milestones_kind", "teaching_project_milestones", ["kind"])

    op.create_table(
        "teaching_project_assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("grade", sa.Float(), nullable=True),
        sa.Column("strengths_markdown", sa.Text(), nullable=True),
        sa.Column("weaknesses_markdown", sa.Text(), nullable=True),
        sa.Column("grading_rationale_markdown", sa.Text(), nullable=True),
        sa.Column("grader_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teaching_project_assessments_project_id", "teaching_project_assessments", ["project_id"])

    op.create_table(
        "teaching_project_blockers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", teaching_blocker_severity, nullable=False, server_default="medium"),
        sa.Column("status", teaching_blocker_status, nullable=False, server_default="open"),
        sa.Column("detected_from", sa.String(length=64), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "title", name="uq_teaching_project_blocker_title"),
    )
    op.create_index("ix_teaching_project_blockers_project_id", "teaching_project_blockers", ["project_id"])

    op.execute(
        """
        INSERT INTO teaching_project_profiles (id, project_id, status, health, reporting_cadence_days)
        SELECT gen_random_uuid(), id, 'draft', 'green', 14
        FROM projects
        WHERE project_kind = 'teaching'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_teaching_project_blockers_project_id", table_name="teaching_project_blockers")
    op.drop_table("teaching_project_blockers")
    op.drop_index("ix_teaching_project_assessments_project_id", table_name="teaching_project_assessments")
    op.drop_table("teaching_project_assessments")
    op.drop_index("ix_teaching_project_milestones_kind", table_name="teaching_project_milestones")
    op.drop_index("ix_teaching_project_milestones_project_id", table_name="teaching_project_milestones")
    op.drop_table("teaching_project_milestones")
    op.drop_index("ix_teaching_progress_reports_project_id", table_name="teaching_progress_reports")
    op.drop_table("teaching_progress_reports")
    op.drop_index("ix_teaching_project_artifacts_document_key", table_name="teaching_project_artifacts")
    op.drop_index("ix_teaching_project_artifacts_project_id", table_name="teaching_project_artifacts")
    op.drop_table("teaching_project_artifacts")
    op.drop_index("ix_teaching_project_students_project_id", table_name="teaching_project_students")
    op.drop_table("teaching_project_students")
    op.drop_index("ix_teaching_project_profiles_project_id", table_name="teaching_project_profiles")
    op.drop_table("teaching_project_profiles")

    op.execute("DROP TYPE IF EXISTS teaching_blocker_status")
    op.execute("DROP TYPE IF EXISTS teaching_blocker_severity")
    op.execute("DROP TYPE IF EXISTS teaching_milestone_status")
    op.execute("DROP TYPE IF EXISTS teaching_artifact_status")
    op.execute("DROP TYPE IF EXISTS teaching_artifact_type")
    op.execute("DROP TYPE IF EXISTS teaching_project_health")
    op.execute("DROP TYPE IF EXISTS teaching_project_status")

    op.drop_index("ix_projects_project_kind", table_name="projects")
    op.drop_column("projects", "project_kind")
