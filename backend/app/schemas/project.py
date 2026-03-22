from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import PaginatedResponse


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    start_date: date | None = None
    duration_months: int | None = Field(default=None, ge=1, le=120)
    reporting_dates: list[date] = Field(default_factory=list)
    language: str = "en_GB"
    project_mode: str = "execution"
    project_kind: str = "funded"
    teaching_course_id: UUID | None = None
    teaching_academic_year: str | None = Field(default=None, max_length=32)
    teaching_term: str | None = Field(default=None, max_length=32)
    coordinator_partner_id: UUID | None = None
    principal_investigator_id: UUID | None = None
    proposal_template_id: UUID | None = None

    @model_validator(mode="after")
    def check_execution_fields(self):
        if self.project_kind == "teaching" and self.project_mode != "execution":
            raise ValueError("teaching projects currently support execution mode only")
        if self.project_mode == "execution":
            if self.start_date is None:
                raise ValueError("start_date is required for execution mode projects")
            if self.duration_months is None:
                raise ValueError("duration_months is required for execution mode projects")
        return self


class ProjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=64)
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    start_date: date | None = None
    duration_months: int | None = Field(default=None, ge=1, le=120)
    reporting_dates: list[date] | None = None
    language: str | None = None
    project_mode: str | None = None
    project_kind: str | None = None
    teaching_course_id: UUID | None = None
    teaching_academic_year: str | None = Field(default=None, max_length=32)
    teaching_term: str | None = Field(default=None, max_length=32)
    coordinator_partner_id: UUID | None = None
    principal_investigator_id: UUID | None = None
    proposal_template_id: UUID | None = None


class ProjectRead(BaseModel):
    id: str
    code: str
    title: str
    description: str | None = None
    start_date: date
    duration_months: int
    reporting_dates: list[date]
    baseline_version: int
    status: str
    language: str
    project_mode: str = "execution"
    project_kind: str = "funded"
    coordinator_partner_id: str | None = None
    principal_investigator_id: str | None = None
    proposal_template_id: str | None = None


class MarkAsFundedPayload(BaseModel):
    start_date: date
    duration_months: int = Field(ge=1, le=120)
    reporting_dates: list[date] = Field(default_factory=list)


class ValidationErrorRead(BaseModel):
    entity_type: str
    entity_id: str
    code: str
    message: str


class ValidationWarningRead(BaseModel):
    entity_type: str = ""
    entity_id: str = ""
    code: str = ""
    field: str = ""
    message: str = ""


class ValidationResultRead(BaseModel):
    valid: bool
    errors: list[ValidationErrorRead]
    warnings: list[ValidationWarningRead] = Field(default_factory=list)


class ActivationResultRead(BaseModel):
    project_id: str
    status: str
    baseline_version: int
    audit_event_id: str


class ProjectListRead(PaginatedResponse):
    items: list[ProjectRead]
