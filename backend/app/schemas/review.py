from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import PaginatedResponse


class ReviewFindingCreate(BaseModel):
    document_id: UUID | None = None
    finding_type: str
    status: str = "open"
    source: str = "manual"
    section_ref: str | None = None
    summary: str
    details: str | None = None
    created_by_member_id: UUID | None = None


class ReviewFindingUpdate(BaseModel):
    document_id: UUID | None = None
    finding_type: str
    status: str
    source: str = "manual"
    section_ref: str | None = None
    summary: str
    details: str | None = None


class ReviewFindingRead(BaseModel):
    id: str
    project_id: str
    deliverable_id: str
    document_id: str | None = None
    finding_type: str
    status: str
    source: str
    section_ref: str | None = None
    summary: str
    details: str | None = None
    created_by_member_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewFindingListRead(PaginatedResponse):
    items: list[ReviewFindingRead]
