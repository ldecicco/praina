from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ActionItemCreate(BaseModel):
    description: str
    assignee_name: str | None = None
    assignee_member_id: str | None = None
    due_date: date | None = None
    priority: str = "normal"
    source: str = "manual"


class ActionItemUpdate(BaseModel):
    description: str | None = None
    assignee_name: str | None = None
    assignee_member_id: str | None = None
    due_date: date | None = None
    priority: str | None = None
    status: str | None = None


class ActionItemRead(BaseModel):
    id: str
    project_id: str
    meeting_id: str
    description: str
    assignee_name: str | None = None
    assignee_member_id: str | None = None
    due_date: date | None = None
    priority: str
    status: str
    source: str
    linked_task_id: str | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class ActionItemListRead(PaginatedResponse):
    items: list[ActionItemRead]


class ActionItemPromoteRequest(BaseModel):
    wp_id: UUID


class ActionItemExtractionRead(BaseModel):
    summary: str | None = None
    items: list[ActionItemRead] = Field(default_factory=list)
