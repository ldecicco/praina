"""meeting records

Revision ID: 20260308_0015
Revises: 20260308_0014
Create Date: 2026-03-08 20:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260308_0015"
down_revision = "20260308_0014"
branch_labels = None
depends_on = None


meeting_source_type = sa.Enum("minutes", "transcript", name="meetingsourcetype")
meeting_source_type_ref = postgresql.ENUM("minutes", "transcript", name="meetingsourcetype", create_type=False)


def upgrade() -> None:
    meeting_source_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "meeting_records",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", meeting_source_type_ref, nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("participants_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("linked_document_id", sa.UUID(), nullable=True),
        sa.Column("created_by_member_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_document_id"], ["project_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_member_id"], ["team_members.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meeting_records_project_id"), "meeting_records", ["project_id"], unique=False)
    op.create_index(op.f("ix_meeting_records_starts_at"), "meeting_records", ["starts_at"], unique=False)
    op.create_index(op.f("ix_meeting_records_source_type"), "meeting_records", ["source_type"], unique=False)
    op.create_index(op.f("ix_meeting_records_linked_document_id"), "meeting_records", ["linked_document_id"], unique=False)
    op.create_index(op.f("ix_meeting_records_created_by_member_id"), "meeting_records", ["created_by_member_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_records_created_by_member_id"), table_name="meeting_records")
    op.drop_index(op.f("ix_meeting_records_linked_document_id"), table_name="meeting_records")
    op.drop_index(op.f("ix_meeting_records_source_type"), table_name="meeting_records")
    op.drop_index(op.f("ix_meeting_records_starts_at"), table_name="meeting_records")
    op.drop_index(op.f("ix_meeting_records_project_id"), table_name="meeting_records")
    op.drop_table("meeting_records")
    meeting_source_type.drop(op.get_bind(), checkfirst=True)
