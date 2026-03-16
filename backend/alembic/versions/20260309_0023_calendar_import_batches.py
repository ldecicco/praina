"""calendar import batches

Revision ID: 20260309_0023
Revises: 20260309_0022
Create Date: 2026-03-09 20:20:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260309_0023"
down_revision = "20260309_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_import_batches",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "filename", name="uq_calendar_import_batch_project_filename"),
    )
    op.create_index("ix_calendar_import_batches_project_id", "calendar_import_batches", ["project_id"])
    op.add_column("meeting_records", sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_meeting_records_import_batch_id", "meeting_records", ["import_batch_id"])
    op.create_foreign_key(
        "fk_meeting_records_import_batch_id",
        "meeting_records",
        "calendar_import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_meeting_records_import_batch_id", "meeting_records", type_="foreignkey")
    op.drop_index("ix_meeting_records_import_batch_id", table_name="meeting_records")
    op.drop_column("meeting_records", "import_batch_id")
    op.drop_index("ix_calendar_import_batches_project_id", table_name="calendar_import_batches")
    op.drop_table("calendar_import_batches")
