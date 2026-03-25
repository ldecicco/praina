"""lab staff assignments

Revision ID: 20260325_0070
Revises: 20260325_0069
Create Date: 2026-03-25 22:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260325_0070"
down_revision: str | Sequence[str] | None = "20260325_0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lab_staff_assignments",
        sa.Column("lab_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="staff"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lab_id", "user_id", name="uq_lab_staff_assignment_lab_user"),
    )
    op.create_index(op.f("ix_lab_staff_assignments_lab_id"), "lab_staff_assignments", ["lab_id"], unique=False)
    op.create_index(op.f("ix_lab_staff_assignments_role"), "lab_staff_assignments", ["role"], unique=False)
    op.create_index(op.f("ix_lab_staff_assignments_user_id"), "lab_staff_assignments", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lab_staff_assignments_user_id"), table_name="lab_staff_assignments")
    op.drop_index(op.f("ix_lab_staff_assignments_role"), table_name="lab_staff_assignments")
    op.drop_index(op.f("ix_lab_staff_assignments_lab_id"), table_name="lab_staff_assignments")
    op.drop_table("lab_staff_assignments")
