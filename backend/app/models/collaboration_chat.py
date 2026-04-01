import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ChatThread(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_threads"

    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_ref_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("scope_type", "scope_ref_id", "name", name="uq_chat_thread_scope_name"),
    )


class ChatThreadMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_thread_members"

    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)

    __table_args__ = (UniqueConstraint("thread_id", "user_id", name="uq_chat_thread_member"),)


class ChatThreadMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_thread_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    sender_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    reply_to_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_thread_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatThreadMessageReaction(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_thread_message_reactions"

    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_thread_messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    emoji: Mapped[str] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_chat_thread_message_reaction"),)


# Compatibility aliases during the service/routing transition.
ProjectChatRoom = ChatThread
ProjectChatRoomMember = ChatThreadMember
ProjectChatMessage = ChatThreadMessage
ProjectChatMessageReaction = ChatThreadMessageReaction
ResearchStudyChatMessage = ChatThreadMessage
ResearchStudyChatMessageReaction = ChatThreadMessageReaction
