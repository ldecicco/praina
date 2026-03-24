"""add resources and equipment tables

Revision ID: 20260323_0063
Revises: 20260322_0062
Create Date: 2026-03-23 10:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260323_0063"
down_revision = "20260322_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("serial_number", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("usage_mode", sa.String(length=32), nullable=False, server_default="exclusive"),
        sa.Column("access_notes", sa.Text(), nullable=True),
        sa.Column("booking_notes", sa.Text(), nullable=True),
        sa.Column("maintenance_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_equipment_name"), "equipment", ["name"], unique=False)
    op.create_index(op.f("ix_equipment_category"), "equipment", ["category"], unique=False)
    op.create_index(op.f("ix_equipment_location"), "equipment", ["location"], unique=False)
    op.create_index(op.f("ix_equipment_owner_user_id"), "equipment", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_equipment_serial_number"), "equipment", ["serial_number"], unique=False)
    op.create_index(op.f("ix_equipment_status"), "equipment", ["status"], unique=False)
    op.create_index(op.f("ix_equipment_usage_mode"), "equipment", ["usage_mode"], unique=False)
    op.create_index(op.f("ix_equipment_is_active"), "equipment", ["is_active"], unique=False)

    op.create_table(
        "equipment_requirements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="important"),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "equipment_id", name="uq_equipment_requirement_project_equipment"),
    )
    op.create_index(op.f("ix_equipment_requirements_project_id"), "equipment_requirements", ["project_id"], unique=False)
    op.create_index(op.f("ix_equipment_requirements_equipment_id"), "equipment_requirements", ["equipment_id"], unique=False)
    op.create_index(op.f("ix_equipment_requirements_priority"), "equipment_requirements", ["priority"], unique=False)
    op.create_index(op.f("ix_equipment_requirements_created_by_user_id"), "equipment_requirements", ["created_by_user_id"], unique=False)

    op.create_table(
        "equipment_bookings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_equipment_bookings_equipment_id"), "equipment_bookings", ["equipment_id"], unique=False)
    op.create_index(op.f("ix_equipment_bookings_project_id"), "equipment_bookings", ["project_id"], unique=False)
    op.create_index(op.f("ix_equipment_bookings_requester_user_id"), "equipment_bookings", ["requester_user_id"], unique=False)
    op.create_index(op.f("ix_equipment_bookings_approved_by_user_id"), "equipment_bookings", ["approved_by_user_id"], unique=False)
    op.create_index(op.f("ix_equipment_bookings_start_at"), "equipment_bookings", ["start_at"], unique=False)
    op.create_index(op.f("ix_equipment_bookings_end_at"), "equipment_bookings", ["end_at"], unique=False)
    op.create_index(op.f("ix_equipment_bookings_status"), "equipment_bookings", ["status"], unique=False)

    op.create_table(
        "equipment_downtime",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False, server_default="maintenance"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_equipment_downtime_equipment_id"), "equipment_downtime", ["equipment_id"], unique=False)
    op.create_index(op.f("ix_equipment_downtime_start_at"), "equipment_downtime", ["start_at"], unique=False)
    op.create_index(op.f("ix_equipment_downtime_end_at"), "equipment_downtime", ["end_at"], unique=False)
    op.create_index(op.f("ix_equipment_downtime_reason"), "equipment_downtime", ["reason"], unique=False)
    op.create_index(op.f("ix_equipment_downtime_created_by_user_id"), "equipment_downtime", ["created_by_user_id"], unique=False)

    op.create_table(
        "equipment_blockers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("equipment_bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=64), nullable=False, server_default="approval_pending"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(op.f("ix_equipment_blockers_project_id"), "equipment_blockers", ["project_id"], unique=False)
    op.create_index(op.f("ix_equipment_blockers_equipment_id"), "equipment_blockers", ["equipment_id"], unique=False)
    op.create_index(op.f("ix_equipment_blockers_booking_id"), "equipment_blockers", ["booking_id"], unique=False)
    op.create_index(op.f("ix_equipment_blockers_started_at"), "equipment_blockers", ["started_at"], unique=False)
    op.create_index(op.f("ix_equipment_blockers_ended_at"), "equipment_blockers", ["ended_at"], unique=False)
    op.create_index(op.f("ix_equipment_blockers_reason"), "equipment_blockers", ["reason"], unique=False)
    op.create_index(op.f("ix_equipment_blockers_status"), "equipment_blockers", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_equipment_blockers_status"), table_name="equipment_blockers")
    op.drop_index(op.f("ix_equipment_blockers_reason"), table_name="equipment_blockers")
    op.drop_index(op.f("ix_equipment_blockers_ended_at"), table_name="equipment_blockers")
    op.drop_index(op.f("ix_equipment_blockers_started_at"), table_name="equipment_blockers")
    op.drop_index(op.f("ix_equipment_blockers_booking_id"), table_name="equipment_blockers")
    op.drop_index(op.f("ix_equipment_blockers_equipment_id"), table_name="equipment_blockers")
    op.drop_index(op.f("ix_equipment_blockers_project_id"), table_name="equipment_blockers")
    op.drop_table("equipment_blockers")

    op.drop_index(op.f("ix_equipment_downtime_created_by_user_id"), table_name="equipment_downtime")
    op.drop_index(op.f("ix_equipment_downtime_reason"), table_name="equipment_downtime")
    op.drop_index(op.f("ix_equipment_downtime_end_at"), table_name="equipment_downtime")
    op.drop_index(op.f("ix_equipment_downtime_start_at"), table_name="equipment_downtime")
    op.drop_index(op.f("ix_equipment_downtime_equipment_id"), table_name="equipment_downtime")
    op.drop_table("equipment_downtime")

    op.drop_index(op.f("ix_equipment_bookings_status"), table_name="equipment_bookings")
    op.drop_index(op.f("ix_equipment_bookings_end_at"), table_name="equipment_bookings")
    op.drop_index(op.f("ix_equipment_bookings_start_at"), table_name="equipment_bookings")
    op.drop_index(op.f("ix_equipment_bookings_approved_by_user_id"), table_name="equipment_bookings")
    op.drop_index(op.f("ix_equipment_bookings_requester_user_id"), table_name="equipment_bookings")
    op.drop_index(op.f("ix_equipment_bookings_project_id"), table_name="equipment_bookings")
    op.drop_index(op.f("ix_equipment_bookings_equipment_id"), table_name="equipment_bookings")
    op.drop_table("equipment_bookings")

    op.drop_index(op.f("ix_equipment_requirements_created_by_user_id"), table_name="equipment_requirements")
    op.drop_index(op.f("ix_equipment_requirements_priority"), table_name="equipment_requirements")
    op.drop_index(op.f("ix_equipment_requirements_equipment_id"), table_name="equipment_requirements")
    op.drop_index(op.f("ix_equipment_requirements_project_id"), table_name="equipment_requirements")
    op.drop_table("equipment_requirements")

    op.drop_index(op.f("ix_equipment_is_active"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_usage_mode"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_status"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_serial_number"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_owner_user_id"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_location"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_category"), table_name="equipment")
    op.drop_index(op.f("ix_equipment_name"), table_name="equipment")
    op.drop_table("equipment")
