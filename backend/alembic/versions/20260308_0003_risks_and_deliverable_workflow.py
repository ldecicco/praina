"""risks and deliverable workflow

Revision ID: 20260308_0013
Revises: 20260306_0012
Create Date: 2026-03-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260308_0013"
down_revision = "20260306_0012"
branch_labels = None
depends_on = None


deliverableworkflowstatus = postgresql.ENUM(
    "draft",
    "in_review",
    "changes_requested",
    "approved",
    "submitted",
    name="deliverableworkflowstatus",
    create_type=False,
)
risklevel = postgresql.ENUM("low", "medium", "high", "critical", name="risklevel", create_type=False)
riskstatus = postgresql.ENUM("open", "monitoring", "mitigated", "closed", name="riskstatus", create_type=False)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TYPE deliverableworkflowstatus AS ENUM ('draft', 'in_review', 'changes_requested', 'approved', 'submitted');
        EXCEPTION
          WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TYPE risklevel AS ENUM ('low', 'medium', 'high', 'critical');
        EXCEPTION
          WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          CREATE TYPE riskstatus AS ENUM ('open', 'monitoring', 'mitigated', 'closed');
        EXCEPTION
          WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.add_column(
        "deliverables",
        sa.Column("workflow_status", deliverableworkflowstatus, nullable=False, server_default="draft"),
    )
    op.create_index(op.f("ix_deliverables_workflow_status"), "deliverables", ["workflow_status"], unique=False)

    op.create_table(
        "project_risks",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mitigation_plan", sa.Text(), nullable=True),
        sa.Column("status", riskstatus, nullable=False, server_default="open"),
        sa.Column("probability", risklevel, nullable=False, server_default="medium"),
        sa.Column("impact", risklevel, nullable=False, server_default="medium"),
        sa.Column("due_month", sa.Integer(), nullable=True),
        sa.Column("owner_partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["owner_member_id"], ["team_members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_partner_id"], ["partner_organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "code", name="uq_project_risk_code"),
    )
    op.create_index(op.f("ix_project_risks_project_id"), "project_risks", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_risks_status"), "project_risks", ["status"], unique=False)
    op.create_index(op.f("ix_project_risks_probability"), "project_risks", ["probability"], unique=False)
    op.create_index(op.f("ix_project_risks_impact"), "project_risks", ["impact"], unique=False)
    op.create_index(op.f("ix_project_risks_owner_partner_id"), "project_risks", ["owner_partner_id"], unique=False)
    op.create_index(op.f("ix_project_risks_owner_member_id"), "project_risks", ["owner_member_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_risks_owner_member_id"), table_name="project_risks")
    op.drop_index(op.f("ix_project_risks_owner_partner_id"), table_name="project_risks")
    op.drop_index(op.f("ix_project_risks_impact"), table_name="project_risks")
    op.drop_index(op.f("ix_project_risks_probability"), table_name="project_risks")
    op.drop_index(op.f("ix_project_risks_status"), table_name="project_risks")
    op.drop_index(op.f("ix_project_risks_project_id"), table_name="project_risks")
    op.drop_table("project_risks")

    op.drop_index(op.f("ix_deliverables_workflow_status"), table_name="deliverables")
    op.drop_column("deliverables", "workflow_status")

    riskstatus.drop(op.get_bind(), checkfirst=False)
    risklevel.drop(op.get_bind(), checkfirst=False)
    deliverableworkflowstatus.drop(op.get_bind(), checkfirst=False)
