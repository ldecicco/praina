"""add labs and lab closures for resources

Revision ID: 20260323_0064
Revises: 20260323_0063
Create Date: 2026-03-23 18:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260323_0064"
down_revision = "20260323_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("building", sa.String(length=255), nullable=True),
        sa.Column("room", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("responsible_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_labs_name"), "labs", ["name"], unique=False)
    op.create_index(op.f("ix_labs_responsible_user_id"), "labs", ["responsible_user_id"], unique=False)
    op.create_index(op.f("ix_labs_is_active"), "labs", ["is_active"], unique=False)

    op.add_column("equipment", sa.Column("lab_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_equipment_lab_id_labs", "equipment", "labs", ["lab_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_equipment_lab_id"), "equipment", ["lab_id"], unique=False)

    op.create_table(
        "lab_closures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", UUID(as_uuid=True), sa.ForeignKey("labs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False, server_default="personnel_unavailable"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancelled_booking_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_lab_closures_lab_id"), "lab_closures", ["lab_id"], unique=False)
    op.create_index(op.f("ix_lab_closures_start_at"), "lab_closures", ["start_at"], unique=False)
    op.create_index(op.f("ix_lab_closures_end_at"), "lab_closures", ["end_at"], unique=False)
    op.create_index(op.f("ix_lab_closures_reason"), "lab_closures", ["reason"], unique=False)
    op.create_index(op.f("ix_lab_closures_created_by_user_id"), "lab_closures", ["created_by_user_id"], unique=False)

    op.execute(
        """
        INSERT INTO labs (id, name, created_at, updated_at)
        SELECT
            (
                substr(hash, 1, 8) || '-' ||
                substr(hash, 9, 4) || '-' ||
                substr(hash, 13, 4) || '-' ||
                substr(hash, 17, 4) || '-' ||
                substr(hash, 21, 12)
            )::uuid,
            location,
            now(),
            now()
        FROM (
            SELECT DISTINCT trim(location) AS location, md5(trim(location) || '-lab-seed') AS hash
            FROM equipment
            WHERE location IS NOT NULL AND trim(location) <> ''
        ) q
        """
    )
    op.execute(
        """
        UPDATE equipment AS e
        SET lab_id = l.id
        FROM labs AS l
        WHERE e.location IS NOT NULL
          AND trim(e.location) <> ''
          AND l.name = trim(e.location)
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lab_closures_created_by_user_id"), table_name="lab_closures")
    op.drop_index(op.f("ix_lab_closures_reason"), table_name="lab_closures")
    op.drop_index(op.f("ix_lab_closures_end_at"), table_name="lab_closures")
    op.drop_index(op.f("ix_lab_closures_start_at"), table_name="lab_closures")
    op.drop_index(op.f("ix_lab_closures_lab_id"), table_name="lab_closures")
    op.drop_table("lab_closures")

    op.drop_index(op.f("ix_equipment_lab_id"), table_name="equipment")
    op.drop_constraint("fk_equipment_lab_id_labs", "equipment", type_="foreignkey")
    op.drop_column("equipment", "lab_id")

    op.drop_index(op.f("ix_labs_is_active"), table_name="labs")
    op.drop_index(op.f("ix_labs_responsible_user_id"), table_name="labs")
    op.drop_index(op.f("ix_labs_name"), table_name="labs")
    op.drop_table("labs")
