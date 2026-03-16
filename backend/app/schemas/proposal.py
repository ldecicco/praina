from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ProposalTemplateSectionCreate(BaseModel):
    key: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)
    guidance: str | None = None
    position: int = Field(default=1, ge=1)
    required: bool = True
    scope_hint: str = Field(default="project", min_length=2, max_length=32)


class ProposalTemplateSectionUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=2, max_length=80)
    title: str | None = Field(default=None, min_length=2, max_length=160)
    guidance: str | None = None
    position: int | None = Field(default=None, ge=1)
    required: bool | None = None
    scope_hint: str | None = Field(default=None, min_length=2, max_length=32)


class ProposalTemplateCreate(BaseModel):
    call_library_entry_id: UUID | None = None
    name: str = Field(min_length=2, max_length=160)
    funding_program: str = Field(min_length=2, max_length=120)
    description: str | None = None
    is_active: bool = True
    sections: list[ProposalTemplateSectionCreate] = Field(default_factory=list)


class ProposalTemplateUpdate(BaseModel):
    call_library_entry_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    funding_program: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    is_active: bool | None = None


class ProposalTemplateSectionRead(BaseModel):
    id: str
    template_id: str
    key: str
    title: str
    guidance: str | None = None
    position: int
    required: bool
    scope_hint: str
    created_at: datetime
    updated_at: datetime


class ProposalTemplateRead(BaseModel):
    id: str
    call_library_entry_id: str | None = None
    name: str
    funding_program: str
    description: str | None = None
    is_active: bool
    sections: list[ProposalTemplateSectionRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProposalTemplateListRead(PaginatedResponse):
    items: list[ProposalTemplateRead]


class ProjectProposalSectionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    guidance: str | None = None
    position: int | None = Field(default=None, ge=1)
    required: bool | None = None
    scope_hint: str | None = Field(default=None, min_length=2, max_length=32)
    status: str | None = Field(default=None, min_length=2, max_length=32)
    owner_member_id: UUID | None = None
    reviewer_member_id: UUID | None = None
    due_date: date | None = None
    notes: str | None = None
    content: str | None = None
    preserve_yjs_state: bool = False


class ProjectProposalSectionRead(BaseModel):
    id: str
    project_id: str
    template_section_id: str | None = None
    key: str
    title: str
    guidance: str | None = None
    position: int
    required: bool
    scope_hint: str
    status: str
    owner_member_id: str | None = None
    reviewer_member_id: str | None = None
    due_date: date | None = None
    notes: str | None = None
    content: str | None = None
    has_collab_state: bool = False
    linked_documents_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProjectProposalSectionListRead(BaseModel):
    items: list[ProjectProposalSectionRead]


class ProposalCallLibraryEntryCreate(BaseModel):
    call_title: str = Field(min_length=2, max_length=255)
    funder_name: str | None = Field(default=None, max_length=160)
    programme_name: str | None = Field(default=None, max_length=160)
    reference_code: str | None = Field(default=None, max_length=120)
    submission_deadline: date | None = None
    source_url: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    eligibility_notes: str | None = None
    budget_notes: str | None = None
    scoring_notes: str | None = None
    requirements_text: str | None = None
    is_active: bool = True


class ProposalCallLibraryEntryUpdate(BaseModel):
    call_title: str | None = Field(default=None, min_length=2, max_length=255)
    funder_name: str | None = Field(default=None, max_length=160)
    programme_name: str | None = Field(default=None, max_length=160)
    reference_code: str | None = Field(default=None, max_length=120)
    submission_deadline: date | None = None
    source_url: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    eligibility_notes: str | None = None
    budget_notes: str | None = None
    scoring_notes: str | None = None
    requirements_text: str | None = None
    is_active: bool | None = None


class ProposalCallLibraryEntryRead(BaseModel):
    id: str
    call_title: str
    funder_name: str | None = None
    programme_name: str | None = None
    reference_code: str | None = None
    submission_deadline: date | None = None
    source_url: str | None = None
    summary: str | None = None
    eligibility_notes: str | None = None
    budget_notes: str | None = None
    scoring_notes: str | None = None
    requirements_text: str | None = None
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProposalCallLibraryEntryListRead(PaginatedResponse):
    items: list[ProposalCallLibraryEntryRead]


class ProposalCallLibraryDocumentRead(BaseModel):
    id: str
    library_entry_id: str
    original_filename: str
    category: str
    status: str
    indexing_status: str
    mime_type: str
    file_size_bytes: int
    storage_path: str
    extracted_text: str | None = None
    indexed_at: datetime | None = None
    ingestion_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ProposalCallLibraryDocumentUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=2, max_length=64)
    status: str | None = Field(default=None, min_length=2, max_length=32)


class ProposalCallLibraryDocumentListRead(BaseModel):
    items: list[ProposalCallLibraryDocumentRead]


class ProposalCallDocumentReindexResultRead(BaseModel):
    document_id: str
    status: str
    chunks_indexed: int
    queued: bool = False
    error: str | None = None


class ProposalCallLibraryIngestRead(BaseModel):
    entry: ProposalCallLibraryEntryRead
    document: ProposalCallLibraryDocumentRead


class ProposalCallIngestJobRead(BaseModel):
    id: str
    library_entry_id: str
    document_id: str
    created_by_user_id: str | None = None
    status: str
    stage: str
    progress_current: int
    progress_total: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    stream_text: str | None = None
    created_at: datetime
    updated_at: datetime


class ProposalCallQuestionPayload(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class ProposalCallAnswerCitationRead(BaseModel):
    library_entry_id: str
    document_id: str
    document_title: str
    chunk_index: int
    snippet: str
    score: float


class ProposalCallAnswerDebugRead(BaseModel):
    library_entry_id: str
    document_id: str
    document_title: str
    chunk_index: int
    snippet: str
    score: float
    lexical_score: float = 0.0
    vector_score: float = 0.0
    combined_score: float = 0.0


class ProposalCallAnswerRead(BaseModel):
    answer: str
    grounded: bool
    insufficient_reason: str | None = None
    citations: list[ProposalCallAnswerCitationRead] = Field(default_factory=list)
    retrieval_debug: list[ProposalCallAnswerDebugRead] = Field(default_factory=list)


class ProposalCallBriefUpsert(BaseModel):
    call_title: str | None = Field(default=None, max_length=255)
    funder_name: str | None = Field(default=None, max_length=160)
    programme_name: str | None = Field(default=None, max_length=160)
    reference_code: str | None = Field(default=None, max_length=120)
    submission_deadline: date | None = None
    source_url: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    eligibility_notes: str | None = None
    budget_notes: str | None = None
    scoring_notes: str | None = None
    requirements_text: str | None = None


class ProposalCallBriefRead(BaseModel):
    id: str | None = None
    project_id: str
    source_call_id: str | None = None
    source_version: int | None = None
    copied_by_user_id: str | None = None
    copied_at: datetime | None = None
    call_title: str | None = None
    funder_name: str | None = None
    programme_name: str | None = None
    reference_code: str | None = None
    submission_deadline: date | None = None
    source_url: str | None = None
    summary: str | None = None
    eligibility_notes: str | None = None
    budget_notes: str | None = None
    scoring_notes: str | None = None
    requirements_text: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProposalSubmissionRequirementCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    document_type: str = Field(min_length=2, max_length=32)
    format_hint: str = Field(min_length=2, max_length=32)
    required: bool = True
    position: int = Field(default=1, ge=1)
    template_id: UUID | None = None


class ProposalSubmissionRequirementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    document_type: str | None = Field(default=None, min_length=2, max_length=32)
    format_hint: str | None = Field(default=None, min_length=2, max_length=32)
    required: bool | None = None
    position: int | None = Field(default=None, ge=1)
    template_id: UUID | None = None


class ProposalSubmissionItemUpdate(BaseModel):
    assignee_member_id: UUID | None = None
    status: str | None = Field(default=None, min_length=2, max_length=32)
    notes: str | None = None
    latest_uploaded_document_id: UUID | None = None


class ProposalSubmissionItemRead(BaseModel):
    id: str
    project_id: str
    requirement_id: str
    partner_id: str | None = None
    assignee_member_id: str | None = None
    status: str
    latest_uploaded_document_id: str | None = None
    submitted_at: datetime | None = None
    notes: str | None = None
    partner_name: str | None = None
    assignee_name: str | None = None
    latest_uploaded_document_title: str | None = None
    created_at: datetime
    updated_at: datetime


class ProposalSubmissionRequirementRead(BaseModel):
    id: str
    project_id: str
    template_id: str | None = None
    title: str
    description: str | None = None
    document_type: str
    format_hint: str
    required: bool
    position: int
    items: list[ProposalSubmissionItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProposalSubmissionRequirementListRead(BaseModel):
    items: list[ProposalSubmissionRequirementRead]


class ProposalReviewFindingCreate(BaseModel):
    proposal_section_id: UUID | None = None
    review_kind: str = "general"
    finding_type: str
    status: str = "open"
    source: str = "manual"
    scope: str = "section"
    summary: str
    details: str | None = None
    anchor_text: str | None = None
    anchor_prefix: str | None = None
    anchor_suffix: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    created_by_member_id: UUID | None = None
    parent_finding_id: UUID | None = None


class ProposalReviewFindingUpdate(BaseModel):
    review_kind: str = "general"
    finding_type: str
    status: str
    source: str = "manual"
    scope: str
    summary: str
    details: str | None = None
    anchor_text: str | None = None
    anchor_prefix: str | None = None
    anchor_suffix: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    parent_finding_id: UUID | None = None


class ProposalReviewFindingRead(BaseModel):
    id: str
    project_id: str
    proposal_section_id: str | None = None
    review_kind: str
    finding_type: str
    status: str
    source: str
    scope: str
    summary: str
    details: str | None = None
    anchor_text: str | None = None
    anchor_prefix: str | None = None
    anchor_suffix: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    created_by_member_id: str | None = None
    parent_finding_id: str | None = None
    created_by_display_name: str | None = None
    replies: list["ProposalReviewFindingRead"] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProposalReviewFindingListRead(PaginatedResponse):
    items: list[ProposalReviewFindingRead]


class ProposalReviewRunPayload(BaseModel):
    proposal_section_id: UUID | None = None


class ProposalReviewRunRead(BaseModel):
    created: list[ProposalReviewFindingRead] = Field(default_factory=list)


class ProposalCallComplianceRunPayload(BaseModel):
    proposal_section_id: UUID | None = None


class ProposalCallBriefImportPayload(BaseModel):
    library_entry_id: UUID
