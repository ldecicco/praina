"""initial schema

Revision ID: 20260305_0001
Revises:
Create Date: 2026-03-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260305_0001"
down_revision = None
branch_labels = None
depends_on = None


project_status_enum = postgresql.ENUM("draft", "active", "archived", name="projectstatus", create_type=False)
document_scope_enum = postgresql.ENUM("project", "wp", "task", "deliverable", name="documentscope", create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TYPE projectstatus AS ENUM ('draft', 'active', 'archived');
        EXCEPTION
          WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TYPE documentscope AS ENUM ('project', 'wp', 'task', 'deliverable');
        EXCEPTION
          WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "projects",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("baseline_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", project_status_enum, nullable=False, server_default="draft"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_projects_code"), "projects", ["code"], unique=True)
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)

    op.create_table(
        "partner_organizations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("short_name", sa.String(length=32), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "short_name", name="uq_partner_short_name"),
    )
    op.create_index(op.f("ix_partner_organizations_project_id"), "partner_organizations", ["project_id"], unique=False)

    op.create_table(
        "team_members",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["partner_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_team_members_email"), "team_members", ["email"], unique=True)
    op.create_index(op.f("ix_team_members_organization_id"), "team_members", ["organization_id"], unique=False)
    op.create_index(op.f("ix_team_members_project_id"), "team_members", ["project_id"], unique=False)

    op.create_table(
        "work_packages",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leader_organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("responsible_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["leader_organization_id"], ["partner_organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_person_id"], ["team_members.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_wp_project_code"),
    )
    op.create_index(op.f("ix_work_packages_leader_organization_id"), "work_packages", ["leader_organization_id"], unique=False)
    op.create_index(op.f("ix_work_packages_project_id"), "work_packages", ["project_id"], unique=False)
    op.create_index(op.f("ix_work_packages_responsible_person_id"), "work_packages", ["responsible_person_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wp_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leader_organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("responsible_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["leader_organization_id"], ["partner_organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_person_id"], ["team_members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wp_id"], ["work_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_task_project_code"),
    )
    op.create_index(op.f("ix_tasks_leader_organization_id"), "tasks", ["leader_organization_id"], unique=False)
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_tasks_responsible_person_id"), "tasks", ["responsible_person_id"], unique=False)
    op.create_index(op.f("ix_tasks_wp_id"), "tasks", ["wp_id"], unique=False)

    op.create_table(
        "milestones",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leader_organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("responsible_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["leader_organization_id"], ["partner_organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_person_id"], ["team_members.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_milestone_project_code"),
    )
    op.create_index(op.f("ix_milestones_leader_organization_id"), "milestones", ["leader_organization_id"], unique=False)
    op.create_index(op.f("ix_milestones_project_id"), "milestones", ["project_id"], unique=False)
    op.create_index(op.f("ix_milestones_responsible_person_id"), "milestones", ["responsible_person_id"], unique=False)

    op.create_table(
        "deliverables",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wp_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leader_organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("responsible_person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["leader_organization_id"], ["partner_organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_person_id"], ["team_members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wp_id"], ["work_packages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_deliverable_project_code"),
    )
    op.create_index(op.f("ix_deliverables_leader_organization_id"), "deliverables", ["leader_organization_id"], unique=False)
    op.create_index(op.f("ix_deliverables_project_id"), "deliverables", ["project_id"], unique=False)
    op.create_index(op.f("ix_deliverables_responsible_person_id"), "deliverables", ["responsible_person_id"], unique=False)

    op.create_table(
        "wp_collaborators",
        sa.Column("wp_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partner_organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wp_id"], ["work_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("wp_id", "partner_id"),
    )

    op.create_table(
        "task_collaborators",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["partner_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "partner_id"),
    )

    op.create_table(
        "milestone_collaborators",
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["partner_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("milestone_id", "partner_id"),
    )

    op.create_table(
        "deliverable_collaborators",
        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["deliverable_id"], ["deliverables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["partner_id"], ["partner_organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("deliverable_id", "partner_id"),
    )

    op.create_table(
        "project_documents",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", document_scope_enum, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("wp_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["deliverable_id"], ["deliverables.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wp_id"], ["work_packages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_documents_project_id"), "project_documents", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_documents_scope"), "project_documents", ["scope"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["document_id"], ["project_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["actor_id"], ["team_members.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_entity_id"), "audit_events", ["entity_id"], unique=False)
    op.create_index(op.f("ix_audit_events_entity_type"), "audit_events", ["entity_type"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_project_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_entity_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_entity_id"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index(op.f("ix_project_documents_scope"), table_name="project_documents")
    op.drop_index(op.f("ix_project_documents_project_id"), table_name="project_documents")
    op.drop_table("project_documents")

    op.drop_table("deliverable_collaborators")
    op.drop_table("milestone_collaborators")
    op.drop_table("task_collaborators")
    op.drop_table("wp_collaborators")

    op.drop_index(op.f("ix_deliverables_responsible_person_id"), table_name="deliverables")
    op.drop_index(op.f("ix_deliverables_project_id"), table_name="deliverables")
    op.drop_index(op.f("ix_deliverables_leader_organization_id"), table_name="deliverables")
    op.drop_table("deliverables")

    op.drop_index(op.f("ix_milestones_responsible_person_id"), table_name="milestones")
    op.drop_index(op.f("ix_milestones_project_id"), table_name="milestones")
    op.drop_index(op.f("ix_milestones_leader_organization_id"), table_name="milestones")
    op.drop_table("milestones")

    op.drop_index(op.f("ix_tasks_wp_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_responsible_person_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_project_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_leader_organization_id"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index(op.f("ix_work_packages_responsible_person_id"), table_name="work_packages")
    op.drop_index(op.f("ix_work_packages_project_id"), table_name="work_packages")
    op.drop_index(op.f("ix_work_packages_leader_organization_id"), table_name="work_packages")
    op.drop_table("work_packages")

    op.drop_index(op.f("ix_team_members_project_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_organization_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_email"), table_name="team_members")
    op.drop_table("team_members")

    op.drop_index(op.f("ix_partner_organizations_project_id"), table_name="partner_organizations")
    op.drop_table("partner_organizations")

    op.drop_index(op.f("ix_projects_status"), table_name="projects")
    op.drop_index(op.f("ix_projects_code"), table_name="projects")
    op.drop_table("projects")

    op.execute("DROP TYPE IF EXISTS documentscope")
    op.execute("DROP TYPE IF EXISTS projectstatus")

