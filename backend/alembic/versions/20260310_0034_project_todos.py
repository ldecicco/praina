"""project todos

Revision ID: 20260310_0034
Revises: 20260310_0033
Create Date: 2026-03-10 20:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260310_0034"
down_revision = "20260310_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DO $$ BEGIN CREATE TYPE todo_status AS ENUM ('pending', 'in_progress', 'done', 'dismissed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    op.execute("DO $$ BEGIN CREATE TYPE todo_priority AS ENUM ('low', 'normal', 'high', 'urgent'); EXCEPTION WHEN duplicate_object THEN NULL; END $$")

    todo_status = postgresql.ENUM("pending", "in_progress", "done", "dismissed", name="todo_status", create_type=False)
    todo_priority = postgresql.ENUM("low", "normal", "high", "urgent", name="todo_priority", create_type=False)

    op.create_table(
        "project_todos",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", todo_status, nullable=False, server_default="pending", index=True),
        sa.Column("priority", todo_priority, nullable=False, server_default="normal"),
        sa.Column("creator_member_id", sa.Uuid(), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("assignee_member_id", sa.Uuid(), sa.ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("wp_id", sa.Uuid(), sa.ForeignKey("work_packages.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("project_todos")
    sa.Enum(name="todo_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="todo_priority").drop(op.get_bind(), checkfirst=True)
