"""calendar integrations

Revision ID: 20260309_0022
Revises: 20260309_0021
Create Date: 2026-03-09 19:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260309_0022"
down_revision = "20260309_0021"
branch_labels = None
depends_on = None

calendar_provider = sa.Enum("microsoft365", "google", name="calendar_provider")
calendar_sync_status = sa.Enum("disconnected", "connected", "syncing", "sync_error", name="calendar_sync_status")
calendar_provider_ref = postgresql.ENUM("microsoft365", "google", name="calendar_provider", create_type=False)
calendar_sync_status_ref = postgresql.ENUM(
    "disconnected", "connected", "syncing", "sync_error", name="calendar_sync_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    calendar_provider.create(bind, checkfirst=True)
    calendar_sync_status.create(bind, checkfirst=True)

    op.add_column("meeting_records", sa.Column("external_calendar_event_id", sa.String(length=255), nullable=True))
    op.create_index("ix_meeting_records_external_calendar_event_id", "meeting_records", ["external_calendar_event_id"])

    op.create_table(
        "calendar_integrations",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", calendar_provider_ref, nullable=False),
        sa.Column("connected_account_email", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oauth_state", sa.String(length=128), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", calendar_sync_status_ref, nullable=False, server_default="disconnected"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "provider", name="uq_calendar_integration_project_provider"),
    )
    op.create_index("ix_calendar_integrations_project_id", "calendar_integrations", ["project_id"])
    op.create_index("ix_calendar_integrations_provider", "calendar_integrations", ["provider"])
    op.create_index("ix_calendar_integrations_oauth_state", "calendar_integrations", ["oauth_state"])
    op.create_index("ix_calendar_integrations_sync_status", "calendar_integrations", ["sync_status"])


def downgrade() -> None:
    op.drop_index("ix_calendar_integrations_sync_status", table_name="calendar_integrations")
    op.drop_index("ix_calendar_integrations_oauth_state", table_name="calendar_integrations")
    op.drop_index("ix_calendar_integrations_provider", table_name="calendar_integrations")
    op.drop_index("ix_calendar_integrations_project_id", table_name="calendar_integrations")
    op.drop_table("calendar_integrations")
    op.drop_index("ix_meeting_records_external_calendar_event_id", table_name="meeting_records")
    op.drop_column("meeting_records", "external_calendar_event_id")
    calendar_sync_status.drop(op.get_bind(), checkfirst=True)
    calendar_provider.drop(op.get_bind(), checkfirst=True)
