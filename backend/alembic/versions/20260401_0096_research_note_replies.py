"""research note replies

Revision ID: 20260401_0096
Revises: 20260401_0095
Create Date: 2026-04-01 18:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260401_0096"
down_revision = "20260401_0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_notes",
        sa.Column("user_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_research_notes_user_account_id", "research_notes", ["user_account_id"], unique=False)
    op.execute(
        """
        UPDATE research_notes AS rn
        SET user_account_id = tm.user_account_id
        FROM team_members AS tm
        WHERE rn.author_member_id = tm.id
          AND tm.user_account_id IS NOT NULL
        """
    )

    op.create_table(
        "research_note_replies",
        sa.Column("note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_note_replies_note_id", "research_note_replies", ["note_id"], unique=False)
    op.create_index("ix_research_note_replies_user_account_id", "research_note_replies", ["user_account_id"], unique=False)
    op.create_table(
        "research_note_reply_references",
        sa.Column("reply_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_note_replies.id", ondelete="CASCADE"), primary_key=True, nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_references.id", ondelete="CASCADE"), primary_key=True, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("research_note_reply_references")
    op.drop_index("ix_research_note_replies_user_account_id", table_name="research_note_replies")
    op.drop_index("ix_research_note_replies_note_id", table_name="research_note_replies")
    op.drop_table("research_note_replies")
    op.drop_index("ix_research_notes_user_account_id", table_name="research_notes")
    op.drop_column("research_notes", "user_account_id")
