"""Add research study chat tables.

Revision ID: 20260331_0091
Revises: 20260331_0090
Create Date: 2026-03-31 20:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0091"
down_revision = "20260331_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_study_chat_messages",
        sa.Column("collection_id", sa.UUID(), nullable=False),
        sa.Column("sender_user_id", sa.UUID(), nullable=False),
        sa.Column("reply_to_message_id", sa.UUID(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["research_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reply_to_message_id"], ["research_study_chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_research_study_chat_messages_collection_id"),
        "research_study_chat_messages",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_study_chat_messages_reply_to_message_id"),
        "research_study_chat_messages",
        ["reply_to_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_study_chat_messages_sender_user_id"),
        "research_study_chat_messages",
        ["sender_user_id"],
        unique=False,
    )

    op.create_table(
        "research_study_chat_message_reactions",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("emoji", sa.String(length=32), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["research_study_chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_research_study_chat_message_reaction"),
    )
    op.create_index(
        op.f("ix_research_study_chat_message_reactions_message_id"),
        "research_study_chat_message_reactions",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_study_chat_message_reactions_user_id"),
        "research_study_chat_message_reactions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_research_study_chat_message_reactions_user_id"), table_name="research_study_chat_message_reactions")
    op.drop_index(op.f("ix_research_study_chat_message_reactions_message_id"), table_name="research_study_chat_message_reactions")
    op.drop_table("research_study_chat_message_reactions")
    op.drop_index(op.f("ix_research_study_chat_messages_sender_user_id"), table_name="research_study_chat_messages")
    op.drop_index(op.f("ix_research_study_chat_messages_reply_to_message_id"), table_name="research_study_chat_messages")
    op.drop_index(op.f("ix_research_study_chat_messages_collection_id"), table_name="research_study_chat_messages")
    op.drop_table("research_study_chat_messages")
