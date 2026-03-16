from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ProjectInboxCreate(BaseModel):
    title: str
    details: str | None = None
    priority: str = "normal"
    source_type: str = "manual"
    source_key: str | None = None
    assignee_member_id: str | None = None
    due_date: date | None = None


class ProjectInboxUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    assignee_member_id: str | None = None
    due_date: date | None = None


class ProjectInboxRead(BaseModel):
    id: str
    project_id: str
    title: str
    details: str | None = None
    status: str
    priority: str
    source_type: str
    source_key: str | None = None
    assignee_member_id: str | None = None
    due_date: date | None = None
    created_at: datetime
    updated_at: datetime


class ProjectInboxListRead(PaginatedResponse):
    items: list[ProjectInboxRead] = Field(default_factory=list)
