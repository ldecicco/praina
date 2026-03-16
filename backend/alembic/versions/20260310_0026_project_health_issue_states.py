"""project health issue states

Revision ID: 20260310_0026
Revises: 20260310_0025
Create Date: 2026-03-10 00:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260310_0026"
down_revision = "20260310_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_health_issue_states",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "issue_key", name="uq_project_health_issue_project_key"),
    )
    op.create_index("ix_project_health_issue_states_project_id", "project_health_issue_states", ["project_id"])
    op.create_index("ix_project_health_issue_states_issue_key", "project_health_issue_states", ["issue_key"])
    op.create_index("ix_project_health_issue_states_status", "project_health_issue_states", ["status"])


def downgrade() -> None:
    op.drop_index("ix_project_health_issue_states_status", table_name="project_health_issue_states")
    op.drop_index("ix_project_health_issue_states_issue_key", table_name="project_health_issue_states")
    op.drop_index("ix_project_health_issue_states_project_id", table_name="project_health_issue_states")
    op.drop_table("project_health_issue_states")
