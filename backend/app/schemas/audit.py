from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse


class AuditEventRead(BaseModel):
    id: str
    project_id: str
    actor_id: str | None = None
    actor_name: str | None = None
    event_type: str
    entity_type: str
    entity_id: str
    reason: str | None = None
    before_json: dict | None = None
    after_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class AuditEventListRead(PaginatedResponse):
    items: list[AuditEventRead]
