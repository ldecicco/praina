"""unified chat storage

Revision ID: 20260401_0092
Revises: 20260331_0091
Create Date: 2026-04-01 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260401_0092"
down_revision: str | None = "20260331_0091"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_ref_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_ref_id", "name", name="uq_chat_thread_scope_name"),
    )
    op.create_index(op.f("ix_chat_threads_project_id"), "chat_threads", ["project_id"], unique=False)
    op.create_index(op.f("ix_chat_threads_scope_ref_id"), "chat_threads", ["scope_ref_id"], unique=False)
    op.create_index(op.f("ix_chat_threads_scope_type"), "chat_threads", ["scope_type"], unique=False)

    op.create_table(
        "chat_thread_members",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "user_id", name="uq_chat_thread_member"),
    )
    op.create_index(op.f("ix_chat_thread_members_thread_id"), "chat_thread_members", ["thread_id"], unique=False)
    op.create_index(op.f("ix_chat_thread_members_user_id"), "chat_thread_members", ["user_id"], unique=False)

    op.create_table(
        "chat_thread_messages",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("reply_to_message_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reply_to_message_id"], ["chat_thread_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_thread_messages_thread_id"), "chat_thread_messages", ["thread_id"], unique=False)
    op.create_index(op.f("ix_chat_thread_messages_sender_user_id"), "chat_thread_messages", ["sender_user_id"], unique=False)
    op.create_index(op.f("ix_chat_thread_messages_reply_to_message_id"), "chat_thread_messages", ["reply_to_message_id"], unique=False)

    op.create_table(
        "chat_thread_message_reactions",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("emoji", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_thread_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_chat_thread_message_reaction"),
    )
    op.create_index(op.f("ix_chat_thread_message_reactions_message_id"), "chat_thread_message_reactions", ["message_id"], unique=False)
    op.create_index(op.f("ix_chat_thread_message_reactions_user_id"), "chat_thread_message_reactions", ["user_id"], unique=False)

    op.drop_table("research_study_chat_message_reactions")
    op.drop_table("research_study_chat_messages")
    op.drop_table("project_chat_message_reactions")
    op.drop_table("project_chat_messages")
    op.drop_table("project_chat_room_members")
    op.drop_table("project_chat_rooms")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for unified chat storage.")
