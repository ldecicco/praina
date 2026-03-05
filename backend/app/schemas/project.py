from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ProjectCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None


class ProjectRead(BaseModel):
    id: str
    code: str
    title: str
    description: str | None = None
    baseline_version: int
    status: str


class ValidationErrorRead(BaseModel):
    entity_type: str
    entity_id: str
    code: str
    message: str


class ValidationResultRead(BaseModel):
    valid: bool
    errors: list[ValidationErrorRead]
    warnings: list[str] = Field(default_factory=list)


class ActivationResultRead(BaseModel):
    project_id: str
    status: str
    baseline_version: int
    audit_event_id: str


class ProjectListRead(PaginatedResponse):
    items: list[ProjectRead]
