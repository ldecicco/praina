"""proposal templates and project proposal sections

Revision ID: 20260310_0030
Revises: 20260310_0029
Create Date: 2026-03-10 14:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0030"
down_revision = "20260310_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_templates",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("funding_program", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_proposal_templates_name"), "proposal_templates", ["name"], unique=True)
    op.create_index(op.f("ix_proposal_templates_funding_program"), "proposal_templates", ["funding_program"], unique=False)
    op.create_index(op.f("ix_proposal_templates_is_active"), "proposal_templates", ["is_active"], unique=False)

    op.create_table(
        "proposal_template_sections",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scope_hint", sa.String(length=32), nullable=False, server_default="project"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["proposal_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "key", name="uq_template_section_key"),
    )
    op.create_index(op.f("ix_proposal_template_sections_template_id"), "proposal_template_sections", ["template_id"], unique=False)

    op.add_column(
        "projects",
        sa.Column(
            "proposal_template_id",
            sa.UUID(),
            sa.ForeignKey("proposal_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "project_proposal_sections",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("template_section_id", sa.UUID(), nullable=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scope_hint", sa.String(length=32), nullable=False, server_default="project"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="not_started"),
        sa.Column("owner_member_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_member_id", sa.UUID(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_member_id"], ["team_members.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_member_id"], ["team_members.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_section_id"], ["proposal_template_sections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key", name="uq_project_proposal_section_key"),
    )
    op.create_index(op.f("ix_project_proposal_sections_owner_member_id"), "project_proposal_sections", ["owner_member_id"], unique=False)
    op.create_index(op.f("ix_project_proposal_sections_project_id"), "project_proposal_sections", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_proposal_sections_reviewer_member_id"), "project_proposal_sections", ["reviewer_member_id"], unique=False)
    op.create_index(op.f("ix_project_proposal_sections_status"), "project_proposal_sections", ["status"], unique=False)
    op.create_index(op.f("ix_project_proposal_sections_template_section_id"), "project_proposal_sections", ["template_section_id"], unique=False)

    op.add_column(
        "project_documents",
        sa.Column(
            "proposal_section_id",
            sa.UUID(),
            sa.ForeignKey("project_proposal_sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_documents", "proposal_section_id")
    op.drop_table("project_proposal_sections")
    op.drop_column("projects", "proposal_template_id")
    op.drop_table("proposal_template_sections")
    op.drop_table("proposal_templates")
