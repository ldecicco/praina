"""work execution status for tasks and work packages

Revision ID: 20260308_0018
Revises: 20260308_0017
Create Date: 2026-03-08 23:35:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260308_0018"
down_revision = "20260308_0017"
branch_labels = None
depends_on = None

work_execution_status = sa.Enum(
    "planned",
    "in_progress",
    "blocked",
    "ready_for_closure",
    "closed",
    name="workexecutionstatus",
)
work_execution_status_ref = postgresql.ENUM(
    "planned",
    "in_progress",
    "blocked",
    "ready_for_closure",
    "closed",
    name="workexecutionstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    work_execution_status.create(bind, checkfirst=True)

    for table_name in ("work_packages", "tasks"):
        op.add_column(table_name, sa.Column("execution_status", work_execution_status_ref, nullable=False, server_default="planned"))
        op.add_column(table_name, sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table_name, sa.Column("completed_by_member_id", sa.UUID(), nullable=True))
        op.add_column(table_name, sa.Column("completion_note", sa.Text(), nullable=True))
        op.create_index(op.f(f"ix_{table_name}_execution_status"), table_name, ["execution_status"], unique=False)
        op.create_index(op.f(f"ix_{table_name}_completed_by_member_id"), table_name, ["completed_by_member_id"], unique=False)
        op.create_foreign_key(
            f"fk_{table_name}_completed_by_member_id_team_members",
            table_name,
            "team_members",
            ["completed_by_member_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.alter_column("work_packages", "execution_status", server_default=None)
    op.alter_column("tasks", "execution_status", server_default=None)


def downgrade() -> None:
    for table_name in ("tasks", "work_packages"):
        op.drop_constraint(f"fk_{table_name}_completed_by_member_id_team_members", table_name, type_="foreignkey")
        op.drop_index(op.f(f"ix_{table_name}_completed_by_member_id"), table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_execution_status"), table_name=table_name)
        op.drop_column(table_name, "completion_note")
        op.drop_column(table_name, "completed_by_member_id")
        op.drop_column(table_name, "completed_at")
        op.drop_column(table_name, "execution_status")

    work_execution_status.drop(op.get_bind(), checkfirst=True)
