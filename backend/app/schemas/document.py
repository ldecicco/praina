from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.document import DocumentScope
from app.schemas.common import PaginatedResponse


class DocumentUploadPayload(BaseModel):
    scope: DocumentScope
    title: str = Field(min_length=2, max_length=255)
    metadata_json: dict = Field(default_factory=dict)
    wp_id: UUID | None = None
    task_id: UUID | None = None
    deliverable_id: UUID | None = None
    milestone_id: UUID | None = None
    uploaded_by_member_id: UUID | None = None
    proposal_section_id: UUID | None = None


class DocumentLinkPayload(BaseModel):
    url: str = Field(min_length=10, max_length=512)
    scope: DocumentScope
    title: str = Field(min_length=2, max_length=255)
    metadata_json: dict = Field(default_factory=dict)
    wp_id: UUID | None = None
    task_id: UUID | None = None
    deliverable_id: UUID | None = None
    milestone_id: UUID | None = None
    uploaded_by_member_id: UUID | None = None
    proposal_section_id: UUID | None = None


class DocumentVersionUploadPayload(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    metadata_json: dict | None = None
    uploaded_by_member_id: UUID | None = None
    proposal_section_id: UUID | None = None


class DocumentVersionRead(BaseModel):
    id: str
    document_key: str
    project_id: str
    scope: str
    title: str
    storage_uri: str
    original_filename: str
    file_size_bytes: int
    mime_type: str
    status: str
    version: int
    metadata_json: dict
    wp_id: str | None = None
    task_id: str | None = None
    deliverable_id: str | None = None
    milestone_id: str | None = None
    uploaded_by_member_id: str | None = None
    indexed_at: datetime | None = None
    ingestion_error: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    proposal_section_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentRead(BaseModel):
    latest_document_id: str
    document_key: str
    project_id: str
    scope: str
    title: str
    status: str
    latest_version: int
    versions_count: int
    wp_id: str | None = None
    task_id: str | None = None
    deliverable_id: str | None = None
    milestone_id: str | None = None
    uploaded_by_member_id: str | None = None
    indexed_at: datetime | None = None
    ingestion_error: str | None = None
    source_url: str | None = None
    source_type: str | None = None
    proposal_section_id: str | None = None
    updated_at: datetime


class DocumentListRead(PaginatedResponse):
    items: list[DocumentRead]


class DocumentVersionListRead(BaseModel):
    document_key: str
    versions: list[DocumentVersionRead]


class DocumentReindexResultRead(BaseModel):
    document_id: str
    status: str
    chunks_indexed: int
    queued: bool = False
    error: str | None = None
