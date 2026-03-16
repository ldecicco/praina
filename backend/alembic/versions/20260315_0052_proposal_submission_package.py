"""proposal submission package

Revision ID: 20260315_0052
Revises: 20260314_0051
Create Date: 2026-03-15 10:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260315_0052"
down_revision = "20260314_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_submission_requirements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("proposal_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_type", sa.String(length=32), nullable=False, server_default="project"),
        sa.Column("format_hint", sa.String(length=32), nullable=False, server_default="online"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposal_submission_requirements_project_id", "proposal_submission_requirements", ["project_id"])
    op.create_index("ix_proposal_submission_requirements_template_id", "proposal_submission_requirements", ["template_id"])
    op.create_index("ix_proposal_submission_requirements_document_type", "proposal_submission_requirements", ["document_type"])
    op.create_index("ix_proposal_submission_requirements_format_hint", "proposal_submission_requirements", ["format_hint"])
    op.create_index("ix_proposal_submission_requirements_required", "proposal_submission_requirements", ["required"])

    op.create_table(
        "proposal_submission_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "requirement_id",
            UUID(as_uuid=True),
            sa.ForeignKey("proposal_submission_requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("partner_id", UUID(as_uuid=True), sa.ForeignKey("partner_organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("assignee_member_id", UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "latest_uploaded_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("project_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="not_started"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("requirement_id", "partner_id", name="uq_submission_requirement_partner"),
    )
    op.create_index("ix_proposal_submission_items_project_id", "proposal_submission_items", ["project_id"])
    op.create_index("ix_proposal_submission_items_requirement_id", "proposal_submission_items", ["requirement_id"])
    op.create_index("ix_proposal_submission_items_partner_id", "proposal_submission_items", ["partner_id"])
    op.create_index("ix_proposal_submission_items_assignee_member_id", "proposal_submission_items", ["assignee_member_id"])
    op.create_index(
        "ix_proposal_submission_items_latest_uploaded_document_id",
        "proposal_submission_items",
        ["latest_uploaded_document_id"],
    )
    op.create_index("ix_proposal_submission_items_status", "proposal_submission_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_proposal_submission_items_status", table_name="proposal_submission_items")
    op.drop_index("ix_proposal_submission_items_latest_uploaded_document_id", table_name="proposal_submission_items")
    op.drop_index("ix_proposal_submission_items_assignee_member_id", table_name="proposal_submission_items")
    op.drop_index("ix_proposal_submission_items_partner_id", table_name="proposal_submission_items")
    op.drop_index("ix_proposal_submission_items_requirement_id", table_name="proposal_submission_items")
    op.drop_index("ix_proposal_submission_items_project_id", table_name="proposal_submission_items")
    op.drop_table("proposal_submission_items")

    op.drop_index("ix_proposal_submission_requirements_required", table_name="proposal_submission_requirements")
    op.drop_index("ix_proposal_submission_requirements_format_hint", table_name="proposal_submission_requirements")
    op.drop_index("ix_proposal_submission_requirements_document_type", table_name="proposal_submission_requirements")
    op.drop_index("ix_proposal_submission_requirements_template_id", table_name="proposal_submission_requirements")
    op.drop_index("ix_proposal_submission_requirements_project_id", table_name="proposal_submission_requirements")
    op.drop_table("proposal_submission_requirements")
