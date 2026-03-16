from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse


class CalendarIntegrationRead(BaseModel):
    id: str
    project_id: str
    provider: str
    connected_account_email: str | None = None
    token_expires_at: datetime | None = None
    last_synced_at: datetime | None = None
    sync_status: str
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class CalendarIntegrationListRead(PaginatedResponse):
    items: list[CalendarIntegrationRead]


class CalendarConnectRead(BaseModel):
    auth_url: str


class CalendarSyncResultRead(BaseModel):
    integration: CalendarIntegrationRead
    imported: int
    updated: int


class CalendarImportResultRead(BaseModel):
    imported: int
    updated: int


class CalendarImportBatchRead(BaseModel):
    id: str
    project_id: str
    filename: str
    imported_count: int
    updated_count: int
    created_at: datetime
    updated_at: datetime


class CalendarImportBatchListRead(PaginatedResponse):
    items: list[CalendarImportBatchRead]
