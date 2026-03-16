"""project health snapshots

Revision ID: 20260310_0025
Revises: 20260310_0024
Create Date: 2026-03-10 00:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260310_0025"
down_revision = "20260310_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_health_snapshots",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("health_score", sa.String(length=16), nullable=False),
        sa.Column("validation_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_warnings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coherence_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_items_pending", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risks_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_deliverables", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_health_snapshots_project_id", "project_health_snapshots", ["project_id"])
    op.create_index("ix_project_health_snapshots_health_score", "project_health_snapshots", ["health_score"])


def downgrade() -> None:
    op.drop_index("ix_project_health_snapshots_health_score", table_name="project_health_snapshots")
    op.drop_index("ix_project_health_snapshots_project_id", table_name="project_health_snapshots")
    op.drop_table("project_health_snapshots")
