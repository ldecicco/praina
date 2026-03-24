"""meeting action items and summary

Revision ID: 20260309_0020
Revises: 20260309_0019
Create Date: 2026-03-09 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260309_0020"
down_revision = "20260309_0019"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("meeting_records", sa.Column("summary", sa.Text(), nullable=True))
    op.execute("DO $$ BEGIN CREATE TYPE action_item_priority AS ENUM ('low', 'normal', 'high', 'urgent'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE action_item_status AS ENUM ('pending', 'in_progress', 'done', 'dismissed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE action_item_source AS ENUM ('manual', 'assistant'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    op.create_table(
        "meeting_action_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meeting_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assignee_name", sa.String(255), nullable=True),
        sa.Column("assignee_member_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("linked_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("ALTER TABLE meeting_action_items ALTER COLUMN priority DROP DEFAULT")
    op.execute("ALTER TABLE meeting_action_items ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE meeting_action_items ALTER COLUMN source DROP DEFAULT")
    op.execute(
        "ALTER TABLE meeting_action_items "
        "ALTER COLUMN priority TYPE action_item_priority USING priority::action_item_priority"
    )
    op.execute(
        "ALTER TABLE meeting_action_items "
        "ALTER COLUMN status TYPE action_item_status USING status::action_item_status"
    )
    op.execute(
        "ALTER TABLE meeting_action_items "
        "ALTER COLUMN source TYPE action_item_source USING source::action_item_source"
    )
    op.execute("ALTER TABLE meeting_action_items ALTER COLUMN priority SET DEFAULT 'normal'::action_item_priority")
    op.execute("ALTER TABLE meeting_action_items ALTER COLUMN status SET DEFAULT 'pending'::action_item_status")
    op.execute("ALTER TABLE meeting_action_items ALTER COLUMN source SET DEFAULT 'manual'::action_item_source")
    op.create_index("ix_meeting_action_items_project_id", "meeting_action_items", ["project_id"])
    op.create_index("ix_meeting_action_items_meeting_id", "meeting_action_items", ["meeting_id"])
    op.create_index("ix_meeting_action_items_assignee_member_id", "meeting_action_items", ["assignee_member_id"])
    op.create_index("ix_meeting_action_items_linked_task_id", "meeting_action_items", ["linked_task_id"])
    op.create_index("ix_meeting_action_items_status", "meeting_action_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_meeting_action_items_status", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_linked_task_id", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_assignee_member_id", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_meeting_id", table_name="meeting_action_items")
    op.drop_index("ix_meeting_action_items_project_id", table_name="meeting_action_items")
    op.drop_table("meeting_action_items")
    op.execute("DROP TYPE IF EXISTS action_item_source")
    op.execute("DROP TYPE IF EXISTS action_item_status")
    op.execute("DROP TYPE IF EXISTS action_item_priority")
    op.drop_column("meeting_records", "summary")
