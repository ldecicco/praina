from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class MeetingRecordCreate(BaseModel):
    title: str
    starts_at: datetime
    source_type: str
    source_url: str | None = None
    participants: list[str] = Field(default_factory=list)
    content_text: str
    linked_document_id: UUID | None = None
    created_by_member_id: UUID | None = None


class MeetingRecordUpdate(BaseModel):
    title: str
    starts_at: datetime
    source_type: str
    source_url: str | None = None
    participants: list[str] = Field(default_factory=list)
    content_text: str
    linked_document_id: UUID | None = None


class MeetingRecordRead(BaseModel):
    id: str
    project_id: str
    title: str
    starts_at: datetime
    source_type: str
    source_url: str | None = None
    participants: list[str] = Field(default_factory=list)
    content_text: str
    summary: str | None = None
    external_calendar_event_id: str | None = None
    import_batch_id: str | None = None
    indexing_status: str = "pending"
    original_filename: str | None = None
    linked_document_id: str | None = None
    created_by_member_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MeetingRecordListRead(PaginatedResponse):
    items: list[MeetingRecordRead]
