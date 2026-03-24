"""track booking and downtime linkage to lab closures

Revision ID: 20260324_0065
Revises: 20260323_0064
Create Date: 2026-03-24 09:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260324_0065"
down_revision = "20260323_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("equipment_bookings", sa.Column("cancelled_by_lab_closure_id", UUID(as_uuid=True), nullable=True))
    op.add_column("equipment_bookings", sa.Column("lab_closure_previous_status", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_equipment_bookings_cancelled_by_lab_closure_id",
        "equipment_bookings",
        "lab_closures",
        ["cancelled_by_lab_closure_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_equipment_bookings_cancelled_by_lab_closure_id"), "equipment_bookings", ["cancelled_by_lab_closure_id"], unique=False)

    op.add_column("equipment_downtime", sa.Column("source_lab_closure_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_equipment_downtime_source_lab_closure_id",
        "equipment_downtime",
        "lab_closures",
        ["source_lab_closure_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_equipment_downtime_source_lab_closure_id"), "equipment_downtime", ["source_lab_closure_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_equipment_downtime_source_lab_closure_id"), table_name="equipment_downtime")
    op.drop_constraint("fk_equipment_downtime_source_lab_closure_id", "equipment_downtime", type_="foreignkey")
    op.drop_column("equipment_downtime", "source_lab_closure_id")

    op.drop_index(op.f("ix_equipment_bookings_cancelled_by_lab_closure_id"), table_name="equipment_bookings")
    op.drop_constraint("fk_equipment_bookings_cancelled_by_lab_closure_id", "equipment_bookings", type_="foreignkey")
    op.drop_column("equipment_bookings", "lab_closure_previous_status")
    op.drop_column("equipment_bookings", "cancelled_by_lab_closure_id")
