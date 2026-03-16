"""add reply links and reactions to project chat messages

Revision ID: 20260306_0009
Revises: 20260306_0008
Create Date: 2026-03-06 16:55:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260306_0009"
down_revision = "20260306_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_chat_messages", sa.Column("reply_to_message_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        op.f("ix_project_chat_messages_reply_to_message_id"),
        "project_chat_messages",
        ["reply_to_message_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_project_chat_messages_reply_to_message_id",
        "project_chat_messages",
        "project_chat_messages",
        ["reply_to_message_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "project_chat_message_reactions",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("emoji", sa.String(length=32), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["message_id"], ["project_chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", "emoji", name="uq_project_chat_message_reaction"),
    )
    op.create_index(
        op.f("ix_project_chat_message_reactions_message_id"),
        "project_chat_message_reactions",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_chat_message_reactions_user_id"),
        "project_chat_message_reactions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_chat_message_reactions_user_id"), table_name="project_chat_message_reactions")
    op.drop_index(op.f("ix_project_chat_message_reactions_message_id"), table_name="project_chat_message_reactions")
    op.drop_table("project_chat_message_reactions")

    op.drop_constraint("fk_project_chat_messages_reply_to_message_id", "project_chat_messages", type_="foreignkey")
    op.drop_index(op.f("ix_project_chat_messages_reply_to_message_id"), table_name="project_chat_messages")
    op.drop_column("project_chat_messages", "reply_to_message_id")
