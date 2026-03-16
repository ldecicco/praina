"""add soft-delete fields to work entities

Revision ID: 20260306_0012
Revises: 20260306_0011
Create Date: 2026-03-06 19:45:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260306_0012"
down_revision = "20260306_0011"
branch_labels = None
depends_on = None


def _add_soft_delete_columns(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column("is_trashed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        table_name,
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f(f"ix_{table_name}_is_trashed"), table_name, ["is_trashed"], unique=False)


def _drop_soft_delete_columns(table_name: str) -> None:
    op.drop_index(op.f(f"ix_{table_name}_is_trashed"), table_name=table_name)
    op.drop_column(table_name, "trashed_at")
    op.drop_column(table_name, "is_trashed")


def upgrade() -> None:
    _add_soft_delete_columns("work_packages")
    _add_soft_delete_columns("tasks")
    _add_soft_delete_columns("milestones")
    _add_soft_delete_columns("deliverables")


def downgrade() -> None:
    _drop_soft_delete_columns("deliverables")
    _drop_soft_delete_columns("milestones")
    _drop_soft_delete_columns("tasks")
    _drop_soft_delete_columns("work_packages")
