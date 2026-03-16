"""add timeline fields for projects and work entities

Revision ID: 20260305_0004
Revises: 20260305_0003
Create Date: 2026-03-05 23:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260305_0004"
down_revision = "20260305_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("start_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
    )
    op.add_column(
        "projects",
        sa.Column("duration_months", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "projects",
        sa.Column(
            "reporting_dates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.add_column("work_packages", sa.Column("start_month", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("work_packages", sa.Column("end_month", sa.Integer(), nullable=False, server_default="1"))

    op.add_column("tasks", sa.Column("start_month", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tasks", sa.Column("end_month", sa.Integer(), nullable=False, server_default="1"))

    op.add_column("milestones", sa.Column("due_month", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("deliverables", sa.Column("due_month", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("deliverables", "due_month")
    op.drop_column("milestones", "due_month")
    op.drop_column("tasks", "end_month")
    op.drop_column("tasks", "start_month")
    op.drop_column("work_packages", "end_month")
    op.drop_column("work_packages", "start_month")
    op.drop_column("projects", "reporting_dates")
    op.drop_column("projects", "duration_months")
    op.drop_column("projects", "start_date")

