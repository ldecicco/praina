from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse
from app.schemas.course import CourseStaffUserRead


class TeachingProjectProfileUpdate(BaseModel):
    course_id: str | None = None
    academic_year: str | None = None
    term: str | None = None
    functional_objectives_markdown: str | None = None
    specifications_markdown: str | None = None
    responsible_user_id: str | None = None
    status: str | None = None
    health: str | None = None
    reporting_cadence_days: int | None = Field(default=None, ge=1, le=365)
    final_grade: float | None = Field(default=None, ge=0, le=10)


class TeachingProjectProfileRead(BaseModel):
    id: str
    project_id: str
    course_id: str | None
    course_code: str | None
    course_title: str | None
    academic_year: str | None
    term: str | None
    functional_objectives_markdown: str | None
    specifications_markdown: str | None
    responsible_user_id: str | None
    responsible_user: CourseStaffUserRead | None = None
    status: str
    health: str
    reporting_cadence_days: int
    final_grade: float | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeachingProjectStudentCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class TeachingProjectStudentUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class TeachingProjectStudentRead(BaseModel):
    id: str
    project_id: str
    full_name: str
    email: str | None
    created_at: datetime
    updated_at: datetime


class TeachingProjectArtifactCreate(BaseModel):
    artifact_type: str
    label: str = Field(min_length=2, max_length=255)
    required: bool = False
    status: str = "missing"
    document_key: str | None = None
    external_url: str | None = Field(default=None, max_length=512)
    notes: str | None = None
    submitted_at: datetime | None = None


class TeachingProjectArtifactUpdate(BaseModel):
    artifact_type: str | None = None
    label: str | None = Field(default=None, min_length=2, max_length=255)
    required: bool | None = None
    status: str | None = None
    document_key: str | None = None
    external_url: str | None = Field(default=None, max_length=512)
    notes: str | None = None
    submitted_at: datetime | None = None


class TeachingProjectArtifactRead(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    label: str
    required: bool
    status: str
    document_key: str | None
    external_url: str | None
    notes: str | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeachingProjectBackgroundMaterialCreate(BaseModel):
    material_type: str = "other"
    title: str = Field(min_length=2, max_length=255)
    bibliography_reference_id: str | None = None
    document_key: str | None = None
    external_url: str | None = Field(default=None, max_length=512)
    notes: str | None = None


class TeachingProjectBackgroundMaterialUpdate(BaseModel):
    material_type: str | None = None
    title: str | None = Field(default=None, min_length=2, max_length=255)
    bibliography_reference_id: str | None = None
    document_key: str | None = None
    external_url: str | None = Field(default=None, max_length=512)
    notes: str | None = None


class TeachingProjectBackgroundMaterialRead(BaseModel):
    id: str
    project_id: str
    material_type: str
    title: str
    bibliography_reference_id: str | None
    bibliography_title: str | None
    bibliography_url: str | None
    bibliography_attachment_filename: str | None
    document_key: str | None
    external_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TeachingProgressReportCreate(BaseModel):
    report_date: date | None = None
    meeting_date: date | None = None
    work_done_markdown: str = ""
    next_steps_markdown: str = ""
    supervisor_feedback_markdown: str | None = None
    attachment_document_keys: list[str] = Field(default_factory=list)
    transcript_document_keys: list[str] = Field(default_factory=list)
    blocker_updates: list["TeachingProgressReportBlockerUpsert"] = Field(default_factory=list)
    submitted_at: datetime | None = None


class TeachingProgressReportUpdate(BaseModel):
    report_date: date | None = None
    meeting_date: date | None = None
    work_done_markdown: str | None = None
    next_steps_markdown: str | None = None
    supervisor_feedback_markdown: str | None = None
    attachment_document_keys: list[str] | None = None
    transcript_document_keys: list[str] | None = None
    blocker_updates: list["TeachingProgressReportBlockerUpsert"] | None = None
    submitted_at: datetime | None = None


class TeachingProgressReportBlockerUpsert(BaseModel):
    id: str | None = None
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    severity: str = "medium"
    status: str = "open"


class TeachingProgressReportRead(BaseModel):
    id: str
    project_id: str
    report_date: date | None
    meeting_date: date | None
    work_done_markdown: str
    next_steps_markdown: str
    blockers: list["TeachingProjectBlockerRead"] = Field(default_factory=list)
    supervisor_feedback_markdown: str | None
    attachment_document_keys: list[str] = Field(default_factory=list)
    transcript_document_keys: list[str] = Field(default_factory=list)
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeachingProjectMilestoneCreate(BaseModel):
    kind: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=2, max_length=255)
    due_at: date | None = None
    completed_at: datetime | None = None
    status: str = "pending"


class TeachingProjectMilestoneUpdate(BaseModel):
    kind: str | None = Field(default=None, min_length=2, max_length=64)
    label: str | None = Field(default=None, min_length=2, max_length=255)
    due_at: date | None = None
    completed_at: datetime | None = None
    status: str | None = None


class TeachingProjectMilestoneRead(BaseModel):
    id: str
    project_id: str
    kind: str
    label: str
    due_at: date | None
    completed_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime


class TeachingProjectAssessmentUpsert(BaseModel):
    grade: float | None = Field(default=None, ge=0, le=10)
    strengths_markdown: str | None = None
    weaknesses_markdown: str | None = None
    grading_rationale_markdown: str | None = None
    grader_user_id: str | None = None
    graded_at: datetime | None = None


class TeachingProjectAssessmentRead(BaseModel):
    id: str
    project_id: str
    grade: float | None
    strengths_markdown: str | None
    weaknesses_markdown: str | None
    grading_rationale_markdown: str | None
    grader_user_id: str | None
    graded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeachingProjectBlockerCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    severity: str = "medium"
    status: str = "open"
    detected_from: str | None = Field(default=None, max_length=64)
    opened_at: datetime | None = None
    resolved_at: datetime | None = None


class TeachingProjectBlockerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    severity: str | None = None
    status: str | None = None
    detected_from: str | None = Field(default=None, max_length=64)
    opened_at: datetime | None = None
    resolved_at: datetime | None = None


class TeachingProjectBlockerRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: str | None
    severity: str
    status: str
    detected_from: str | None
    opened_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeachingWorkspaceRead(BaseModel):
    profile: TeachingProjectProfileRead
    students: list[TeachingProjectStudentRead]
    artifacts: list[TeachingProjectArtifactRead]
    background_materials: list[TeachingProjectBackgroundMaterialRead]
    progress_reports: list[TeachingProgressReportRead]
    milestones: list[TeachingProjectMilestoneRead]
    blockers: list[TeachingProjectBlockerRead]
    assessment: TeachingProjectAssessmentRead | None = None


class TeachingStudentListRead(PaginatedResponse):
    items: list[TeachingProjectStudentRead]


class TeachingArtifactListRead(PaginatedResponse):
    items: list[TeachingProjectArtifactRead]


class TeachingBackgroundMaterialListRead(PaginatedResponse):
    items: list[TeachingProjectBackgroundMaterialRead]


class TeachingProgressReportListRead(PaginatedResponse):
    items: list[TeachingProgressReportRead]


class TeachingMilestoneListRead(PaginatedResponse):
    items: list[TeachingProjectMilestoneRead]


class TeachingBlockerListRead(PaginatedResponse):
    items: list[TeachingProjectBlockerRead]
