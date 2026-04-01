from datetime import datetime

from pydantic import BaseModel, Field


class ScopedChatMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    reply_to_message_id: str | None = None


class ScopedChatMessageReactionToggleRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)


class ScopedChatReactionRead(BaseModel):
    emoji: str
    count: int
    user_ids: list[str] = Field(default_factory=list)


class ScopedChatReplyPreviewRead(BaseModel):
    id: str
    sender_user_id: str
    sender_display_name: str
    content: str
    deleted_at: datetime | None = None
    created_at: datetime


class ScopedChatMessageBaseRead(BaseModel):
    sender_user_id: str
    sender_display_name: str
    content: str
    reply_to_message_id: str | None = None
    reply_to_message: ScopedChatReplyPreviewRead | None = None
    reactions: list[ScopedChatReactionRead] = Field(default_factory=list)
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
