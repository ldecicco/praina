"""Notification schemas."""

from __future__ import annotations

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: str
    user_id: str
    project_id: str | None = None
    channel: str
    status: str
    title: str
    body: str
    link_type: str | None = None
    link_id: str | None = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class NotificationListRead(BaseModel):
    items: list[NotificationRead]
    page: int
    page_size: int
    total: int


class UnreadCountRead(BaseModel):
    count: int
