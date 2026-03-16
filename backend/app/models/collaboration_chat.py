import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ProjectChatRoom(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_chat_rooms"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), default="project")
    scope_ref_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_chat_room_name"),)


class ProjectChatRoomMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_chat_room_members"

    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_chat_rooms.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)

    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_project_chat_room_member"),)


class ProjectChatMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_chat_messages"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_chat_rooms.id", ondelete="CASCADE"), index=True)
    sender_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_chat_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectChatMessageReaction(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_chat_message_reactions"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_chat_messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    emoji: Mapped[str] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_project_chat_message_reaction"),)
