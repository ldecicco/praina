from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "normal"
    assignee_member_id: str | None = None
    wp_id: str | None = None
    task_id: str | None = None
    due_date: date | None = None
    sort_order: int = 0


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_member_id: str | None = None
    wp_id: str | None = None
    task_id: str | None = None
    due_date: date | None = None
    sort_order: int | None = None


class TodoRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: str | None = None
    status: str
    priority: str
    creator_member_id: str | None = None
    assignee_member_id: str | None = None
    wp_id: str | None = None
    task_id: str | None = None
    due_date: date | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TodoListRead(PaginatedResponse):
    items: list[TodoRead] = Field(default_factory=list)
