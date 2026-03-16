"""add auth and project chat tables

Revision ID: 20260306_0007
Revises: 20260306_0006
Create Date: 2026-03-06 01:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260306_0007"
down_revision = "20260306_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("platform_role", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_accounts_email"), "user_accounts", ["email"], unique=True)
    op.create_index(op.f("ix_user_accounts_platform_role"), "user_accounts", ["platform_role"], unique=False)

    op.create_table(
        "project_memberships",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_membership"),
    )
    op.create_index(op.f("ix_project_memberships_project_id"), "project_memberships", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_memberships_role"), "project_memberships", ["role"], unique=False)
    op.create_index(op.f("ix_project_memberships_user_id"), "project_memberships", ["user_id"], unique=False)

    op.create_table(
        "project_chat_rooms",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="project"),
        sa.Column("scope_ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_project_chat_room_name"),
    )
    op.create_index(op.f("ix_project_chat_rooms_project_id"), "project_chat_rooms", ["project_id"], unique=False)

    op.create_table(
        "project_chat_room_members",
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["room_id"], ["project_chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_project_chat_room_member"),
    )
    op.create_index(op.f("ix_project_chat_room_members_room_id"), "project_chat_room_members", ["room_id"], unique=False)
    op.create_index(op.f("ix_project_chat_room_members_user_id"), "project_chat_room_members", ["user_id"], unique=False)

    op.create_table(
        "project_chat_messages",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["project_chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_chat_messages_project_id"), "project_chat_messages", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_chat_messages_room_id"), "project_chat_messages", ["room_id"], unique=False)
    op.create_index(op.f("ix_project_chat_messages_sender_user_id"), "project_chat_messages", ["sender_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_chat_messages_sender_user_id"), table_name="project_chat_messages")
    op.drop_index(op.f("ix_project_chat_messages_room_id"), table_name="project_chat_messages")
    op.drop_index(op.f("ix_project_chat_messages_project_id"), table_name="project_chat_messages")
    op.drop_table("project_chat_messages")

    op.drop_index(op.f("ix_project_chat_room_members_user_id"), table_name="project_chat_room_members")
    op.drop_index(op.f("ix_project_chat_room_members_room_id"), table_name="project_chat_room_members")
    op.drop_table("project_chat_room_members")

    op.drop_index(op.f("ix_project_chat_rooms_project_id"), table_name="project_chat_rooms")
    op.drop_table("project_chat_rooms")

    op.drop_index(op.f("ix_project_memberships_user_id"), table_name="project_memberships")
    op.drop_index(op.f("ix_project_memberships_role"), table_name="project_memberships")
    op.drop_index(op.f("ix_project_memberships_project_id"), table_name="project_memberships")
    op.drop_table("project_memberships")

    op.drop_index(op.f("ix_user_accounts_platform_role"), table_name="user_accounts")
    op.drop_index(op.f("ix_user_accounts_email"), table_name="user_accounts")
    op.drop_table("user_accounts")
