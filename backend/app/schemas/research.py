from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


# ── Collection ─────────────────────────────────────────────────────────

class CollectionCreate(BaseModel):
    title: str
    description: str | None = None
    hypothesis: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    status: str = "active"
    tags: list[str] = Field(default_factory=list)
    overleaf_url: str | None = None
    target_output_title: str | None = None
    output_status: str = "not_started"


class CollectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    hypothesis: str | None = None
    open_questions: list[str] | None = None
    status: str | None = None
    tags: list[str] | None = None
    overleaf_url: str | None = None
    target_output_title: str | None = None
    output_status: str | None = None


class CollectionRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: str | None = None
    hypothesis: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    status: str
    tags: list[str] = Field(default_factory=list)
    overleaf_url: str | None = None
    target_output_title: str | None = None
    output_status: str
    created_by_member_id: str | None = None
    ai_synthesis: str | None = None
    ai_synthesis_at: datetime | None = None
    reference_count: int = 0
    note_count: int = 0
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class CollectionDetailRead(CollectionRead):
    members: list[CollectionMemberRead] = Field(default_factory=list)
    wp_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    deliverable_ids: list[str] = Field(default_factory=list)
    meetings: list[CollectionMeetingRead] = Field(default_factory=list)


class CollectionListRead(PaginatedResponse):
    items: list[CollectionRead] = Field(default_factory=list)


# ── Collection member ─────────────────────────────────────────────────

class CollectionMemberCreate(BaseModel):
    member_id: str
    role: str = "contributor"


class CollectionMemberUpdate(BaseModel):
    role: str


class CollectionMemberRead(BaseModel):
    id: str
    member_id: str
    member_name: str = ""
    organization_short_name: str = ""
    role: str
    created_at: datetime
    updated_at: datetime


# ── WBS links ──────────────────────────────────────────────────────────

class WbsLinksPayload(BaseModel):
    wp_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    deliverable_ids: list[str] = Field(default_factory=list)


class WbsLinksRead(BaseModel):
    wp_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    deliverable_ids: list[str] = Field(default_factory=list)


class CollectionMeetingPayload(BaseModel):
    meeting_ids: list[str] = Field(default_factory=list)


class CollectionMeetingRead(BaseModel):
    id: str
    title: str
    starts_at: datetime
    source_type: str
    summary: str | None = None


# ── Reference ──────────────────────────────────────────────────────────

class ReferenceCreate(BaseModel):
    title: str
    collection_id: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    document_key: str | None = None
    tags: list[str] = Field(default_factory=list)
    reading_status: str = "unread"
    bibliography_visibility: str = "shared"


class ReferenceUpdate(BaseModel):
    title: str | None = None
    collection_id: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    document_key: str | None = None
    tags: list[str] | None = None
    reading_status: str | None = None
    bibliography_visibility: str | None = None


class ReferenceRead(BaseModel):
    id: str
    project_id: str
    bibliography_reference_id: str | None = None
    collection_id: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    document_key: str | None = None
    tags: list[str] = Field(default_factory=list)
    bibliography_visibility: str | None = None
    bibliography_attachment_filename: str | None = None
    bibliography_attachment_url: str | None = None
    reading_status: str
    added_by_member_id: str | None = None
    ai_summary: str | None = None
    ai_summary_at: datetime | None = None
    note_count: int = 0
    annotation_count: int = 0
    created_at: datetime
    updated_at: datetime


class ReferenceListRead(PaginatedResponse):
    items: list[ReferenceRead] = Field(default_factory=list)


class BibliographyReferenceCreate(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    bibtex_raw: str | None = None
    tags: list[str] = Field(default_factory=list)
    visibility: str = "shared"
    allow_duplicate: bool = False
    reuse_existing_id: str | None = None


class BibliographyReferenceUpdate(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    bibtex_raw: str | None = None
    tags: list[str] | None = None
    visibility: str | None = None


class BibliographySemanticEvidenceRead(BaseModel):
    text: str
    similarity: float | None = None


class BibliographyReferenceRead(BaseModel):
    id: str
    source_project_id: str | None = None
    document_key: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    bibtex_raw: str | None = None
    tags: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    visibility: str
    created_by_user_id: str | None = None
    attachment_filename: str | None = None
    attachment_url: str | None = None
    document_status: str | None = None
    warning: str | None = None
    linked_project_count: int = 0
    note_count: int = 0
    reading_status: str = "unread"
    ai_summary: str | None = None
    ai_summary_at: datetime | None = None
    semantic_evidence: list[BibliographySemanticEvidenceRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class BibliographyReferenceListRead(PaginatedResponse):
    items: list[BibliographyReferenceRead] = Field(default_factory=list)


class BibliographyDuplicateCheckPayload(BaseModel):
    title: str
    doi: str | None = None


class BibliographyDuplicateMatchRead(BaseModel):
    match_reason: str
    reference: BibliographyReferenceRead


class BibliographyDuplicateCheckRead(BaseModel):
    matches: list[BibliographyDuplicateMatchRead] = Field(default_factory=list)


class BibliographyGraphRequest(BaseModel):
    reference_ids: list[str] = Field(default_factory=list)
    include_authors: bool = True
    include_concepts: bool = True
    include_tags: bool = False
    include_semantic: bool = True
    include_bibliography_collections: bool = True
    include_research_links: bool = True
    include_teaching_links: bool = True
    semantic_threshold: float = 0.78
    semantic_top_k: int = 3


class BibliographyGraphNodeRead(BaseModel):
    id: str
    label: str
    node_type: str
    ref_id: str | None = None


class BibliographyGraphEdgeRead(BaseModel):
    id: str
    source: str
    target: str
    edge_type: str
    weight: float | None = None


class BibliographyGraphRead(BaseModel):
    nodes: list[BibliographyGraphNodeRead] = Field(default_factory=list)
    edges: list[BibliographyGraphEdgeRead] = Field(default_factory=list)


class BibliographyCollectionCreate(BaseModel):
    title: str
    description: str | None = None
    visibility: str = "private"


class BibliographyCollectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    visibility: str | None = None


class BibliographyCollectionRead(BaseModel):
    id: str
    title: str
    description: str | None = None
    visibility: str
    owner_user_id: str
    reference_count: int = 0
    created_at: datetime
    updated_at: datetime


class BibliographyCollectionListRead(PaginatedResponse):
    items: list[BibliographyCollectionRead] = Field(default_factory=list)


class BibliographyCollectionReferenceUpsert(BaseModel):
    bibliography_reference_id: str


class BibliographyCollectionBulkResearchLinkPayload(BaseModel):
    project_id: str
    collection_id: str
    reading_status: str = "unread"


class BibliographyCollectionBulkTeachingLinkPayload(BaseModel):
    project_id: str


class BibliographyTagRead(BaseModel):
    id: str
    label: str
    slug: str
    created_at: datetime
    updated_at: datetime


class BibliographyTagListRead(PaginatedResponse):
    items: list[BibliographyTagRead] = Field(default_factory=list)


class BibliographyNoteCreate(BaseModel):
    content: str
    note_type: str = "comment"
    visibility: str = "shared"


class BibliographyNoteUpdate(BaseModel):
    content: str | None = None
    note_type: str | None = None
    visibility: str | None = None


class BibliographyNoteRead(BaseModel):
    id: str
    bibliography_reference_id: str
    user_id: str
    user_display_name: str
    content: str
    note_type: str
    visibility: str
    created_at: datetime
    updated_at: datetime


class BibliographyNoteListRead(BaseModel):
    items: list[BibliographyNoteRead] = Field(default_factory=list)


class BibliographyReadingStatusRead(BaseModel):
    reading_status: str


class BibliographyReadingStatusUpdate(BaseModel):
    reading_status: str


class BibliographyLinkPayload(BaseModel):
    bibliography_reference_id: str
    collection_id: str | None = None
    reading_status: str = "unread"


class ReferenceMovePayload(BaseModel):
    collection_id: str | None = None


class ReferenceStatusPayload(BaseModel):
    reading_status: str


# ── Note ───────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: str
    collection_id: str | None = None
    note_type: str = "observation"
    tags: list[str] = Field(default_factory=list)
    linked_reference_ids: list[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    collection_id: str | None = None
    note_type: str | None = None
    tags: list[str] | None = None


class NoteRead(BaseModel):
    id: str
    project_id: str
    collection_id: str | None = None
    author_member_id: str | None = None
    author_name: str | None = None
    title: str
    content: str
    note_type: str
    tags: list[str] = Field(default_factory=list)
    linked_reference_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class NoteListRead(PaginatedResponse):
    items: list[NoteRead] = Field(default_factory=list)


class NoteReferencesPayload(BaseModel):
    reference_ids: list[str] = Field(default_factory=list)


# ── AI responses ───────────────────────────────────────────────────────

class AISummaryRead(BaseModel):
    ai_summary: str
    ai_summary_at: datetime


class AISynthesisRead(BaseModel):
    ai_synthesis: str
    ai_synthesis_at: datetime


class ReferenceMetadataRead(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None


# ── BibTeX import ─────────────────────────────────────────────────────

class BibtexImportPayload(BaseModel):
    bibtex: str
    collection_id: str | None = None
    visibility: str = "shared"


class BibtexImportRead(BaseModel):
    created: list[ReferenceRead] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BibliographyBibtexImportRead(BaseModel):
    created: list[BibliographyReferenceRead] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BibliographyIdentifierImportPayload(BaseModel):
    identifiers: str
    visibility: str = "shared"
    source_project_id: str | None = None


class BibliographyIdentifierImportRead(BaseModel):
    created: list[BibliographyReferenceRead] = Field(default_factory=list)
    reused: list[BibliographyReferenceRead] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
