"""project inbox items

Revision ID: 20260310_0027
Revises: 20260310_0026
Create Date: 2026-03-10 02:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260310_0027"
down_revision = "20260310_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inbox_status = postgresql.ENUM("open", "in_progress", "done", "dismissed", name="project_inbox_status")
    inbox_priority = postgresql.ENUM("low", "normal", "high", "urgent", name="project_inbox_priority")
    inbox_source = postgresql.ENUM("health_issue", "manual", name="project_inbox_source")
    inbox_status.create(op.get_bind(), checkfirst=True)
    inbox_priority.create(op.get_bind(), checkfirst=True)
    inbox_source.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "project_inbox_items",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", postgresql.ENUM(name="project_inbox_status", create_type=False), nullable=False, server_default="open"),
        sa.Column("priority", postgresql.ENUM(name="project_inbox_priority", create_type=False), nullable=False, server_default="normal"),
        sa.Column("source_type", postgresql.ENUM(name="project_inbox_source", create_type=False), nullable=False, server_default="manual"),
        sa.Column("source_key", sa.String(length=64), nullable=True),
        sa.Column("assignee_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["assignee_member_id"], ["team_members.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "source_type", "source_key", name="uq_project_inbox_source"),
    )
    op.create_index("ix_project_inbox_items_project_id", "project_inbox_items", ["project_id"])
    op.create_index("ix_project_inbox_items_status", "project_inbox_items", ["status"])
    op.create_index("ix_project_inbox_items_priority", "project_inbox_items", ["priority"])
    op.create_index("ix_project_inbox_items_source_type", "project_inbox_items", ["source_type"])
    op.create_index("ix_project_inbox_items_source_key", "project_inbox_items", ["source_key"])
    op.create_index("ix_project_inbox_items_assignee_member_id", "project_inbox_items", ["assignee_member_id"])


def downgrade() -> None:
    op.drop_index("ix_project_inbox_items_assignee_member_id", table_name="project_inbox_items")
    op.drop_index("ix_project_inbox_items_source_key", table_name="project_inbox_items")
    op.drop_index("ix_project_inbox_items_source_type", table_name="project_inbox_items")
    op.drop_index("ix_project_inbox_items_priority", table_name="project_inbox_items")
    op.drop_index("ix_project_inbox_items_status", table_name="project_inbox_items")
    op.drop_index("ix_project_inbox_items_project_id", table_name="project_inbox_items")
    op.drop_table("project_inbox_items")
    postgresql.ENUM(name="project_inbox_source").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="project_inbox_priority").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="project_inbox_status").drop(op.get_bind(), checkfirst=True)
