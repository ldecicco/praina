from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ChatRoomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=500)
    scope_type: str = Field(default="project", max_length=32)
    scope_ref_id: str | None = None


class ChatRoomRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    scope_type: str
    scope_ref_id: str | None = None
    is_archived: bool
    member_user_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ChatRoomListRead(PaginatedResponse):
    items: list[ChatRoomRead]


class RoomMemberAddRequest(BaseModel):
    user_id: str


class ChatMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    reply_to_message_id: str | None = None


class ChatMessageReactionToggleRequest(BaseModel):
    emoji: str = Field(min_length=1, max_length=32)


class ChatMessageReactionRead(BaseModel):
    emoji: str
    count: int
    user_ids: list[str] = Field(default_factory=list)


class ChatMessageReplyPreview(BaseModel):
    id: str
    sender_user_id: str
    sender_display_name: str
    content: str
    deleted_at: datetime | None = None
    created_at: datetime


class ChatMessageRead(BaseModel):
    id: str
    project_id: str
    room_id: str
    sender_user_id: str
    sender_display_name: str
    content: str
    reply_to_message_id: str | None = None
    reply_to_message: ChatMessageReplyPreview | None = None
    reactions: list[ChatMessageReactionRead] = Field(default_factory=list)
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessageListRead(PaginatedResponse):
    items: list[ChatMessageRead]


class ProjectBroadcastCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=4000)
    severity: str = Field(default="important", max_length=16)
    deliver_telegram: bool = False


class ProjectBroadcastRead(BaseModel):
    id: str
    project_id: str | None
    lab_id: str | None = None
    author_user_id: str
    author_display_name: str
    title: str
    body: str
    severity: str
    deliver_telegram: bool
    recipient_count: int
    sent_at: datetime
    created_at: datetime
    updated_at: datetime


class ProjectBroadcastListRead(PaginatedResponse):
    items: list[ProjectBroadcastRead]
