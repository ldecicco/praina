from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class CitationRead(BaseModel):
    source_type: str | None = None
    document_id: str
    document_key: str
    title: str
    version: int
    chunk_index: int
    snippet: str




class ChatCardRead(BaseModel):
    type: str
    title: str
    body: str
    action_label: str | None = None
    action_prompt: str | None = None

class ChatConversationCreate(BaseModel):
    title: str | None = None
    created_by_member_id: str | None = None


class ChatConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ChatConversationRead(BaseModel):
    id: str
    project_id: str
    title: str
    created_by_member_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatConversationListRead(PaginatedResponse):
    items: list[ChatConversationRead]


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    created_by_member_id: str | None = None


class ChatMessageRead(BaseModel):
    id: str
    conversation_id: str
    project_id: str
    role: str
    content: str
    citations: list[CitationRead] = Field(default_factory=list)
    cards: list[ChatCardRead] = Field(default_factory=list)
    created_by_member_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessageListRead(PaginatedResponse):
    items: list[ChatMessageRead]


class ChatMessageExchangeRead(BaseModel):
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead
