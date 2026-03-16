"""deliverable review findings

Revision ID: 20260308_0017
Revises: 20260308_0016
Create Date: 2026-03-08 21:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260308_0017"
down_revision = "20260308_0016"
branch_labels = None
depends_on = None

review_finding_type = sa.Enum("issue", "warning", "strength", name="reviewfindingtype")
review_finding_status = sa.Enum("open", "resolved", name="reviewfindingstatus")
review_finding_source = sa.Enum("manual", "assistant", name="reviewfindingsource")
review_finding_type_ref = postgresql.ENUM("issue", "warning", "strength", name="reviewfindingtype", create_type=False)
review_finding_status_ref = postgresql.ENUM("open", "resolved", name="reviewfindingstatus", create_type=False)
review_finding_source_ref = postgresql.ENUM("manual", "assistant", name="reviewfindingsource", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    review_finding_type.create(bind, checkfirst=True)
    review_finding_status.create(bind, checkfirst=True)
    review_finding_source.create(bind, checkfirst=True)
    op.create_table(
        "deliverable_review_findings",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("deliverable_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("finding_type", review_finding_type_ref, nullable=False),
        sa.Column("status", review_finding_status_ref, nullable=False),
        sa.Column("source", review_finding_source_ref, nullable=False),
        sa.Column("section_ref", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_by_member_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deliverable_id"], ["deliverables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["project_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_member_id"], ["team_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deliverable_review_findings_project_id"), "deliverable_review_findings", ["project_id"], unique=False)
    op.create_index(op.f("ix_deliverable_review_findings_deliverable_id"), "deliverable_review_findings", ["deliverable_id"], unique=False)
    op.create_index(op.f("ix_deliverable_review_findings_document_id"), "deliverable_review_findings", ["document_id"], unique=False)
    op.create_index(op.f("ix_deliverable_review_findings_finding_type"), "deliverable_review_findings", ["finding_type"], unique=False)
    op.create_index(op.f("ix_deliverable_review_findings_status"), "deliverable_review_findings", ["status"], unique=False)
    op.create_index(op.f("ix_deliverable_review_findings_source"), "deliverable_review_findings", ["source"], unique=False)
    op.create_index(op.f("ix_deliverable_review_findings_created_by_member_id"), "deliverable_review_findings", ["created_by_member_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deliverable_review_findings_created_by_member_id"), table_name="deliverable_review_findings")
    op.drop_index(op.f("ix_deliverable_review_findings_source"), table_name="deliverable_review_findings")
    op.drop_index(op.f("ix_deliverable_review_findings_status"), table_name="deliverable_review_findings")
    op.drop_index(op.f("ix_deliverable_review_findings_finding_type"), table_name="deliverable_review_findings")
    op.drop_index(op.f("ix_deliverable_review_findings_document_id"), table_name="deliverable_review_findings")
    op.drop_index(op.f("ix_deliverable_review_findings_deliverable_id"), table_name="deliverable_review_findings")
    op.drop_index(op.f("ix_deliverable_review_findings_project_id"), table_name="deliverable_review_findings")
    op.drop_table("deliverable_review_findings")
    review_finding_source.drop(op.get_bind(), checkfirst=True)
    review_finding_status.drop(op.get_bind(), checkfirst=True)
    review_finding_type.drop(op.get_bind(), checkfirst=True)
