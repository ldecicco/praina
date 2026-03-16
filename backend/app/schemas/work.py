from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class AssignmentPayload(BaseModel):
    leader_organization_id: UUID
    responsible_person_id: UUID
    collaborating_partner_ids: list[UUID] = Field(default_factory=list)


class WorkPackageCreate(BaseModel):
    code: str
    title: str
    description: str | None = None
    start_month: int = Field(ge=1, le=120)
    end_month: int = Field(ge=1, le=120)
    execution_status: str = "planned"
    completed_by_member_id: UUID | None = None
    completion_note: str | None = None
    assignment: AssignmentPayload


class WorkPackageUpdate(BaseModel):
    code: str
    title: str
    description: str | None = None
    start_month: int = Field(ge=1, le=120)
    end_month: int = Field(ge=1, le=120)
    execution_status: str = "planned"
    completed_by_member_id: UUID | None = None
    completion_note: str | None = None
    assignment: AssignmentPayload


class TaskCreate(BaseModel):
    wp_id: UUID
    code: str
    title: str
    description: str | None = None
    start_month: int = Field(ge=1, le=120)
    end_month: int = Field(ge=1, le=120)
    execution_status: str = "planned"
    completed_by_member_id: UUID | None = None
    completion_note: str | None = None
    assignment: AssignmentPayload


class TaskUpdate(BaseModel):
    code: str
    title: str
    description: str | None = None
    start_month: int = Field(ge=1, le=120)
    end_month: int = Field(ge=1, le=120)
    execution_status: str = "planned"
    completed_by_member_id: UUID | None = None
    completion_note: str | None = None
    assignment: AssignmentPayload


class MilestoneCreate(BaseModel):
    code: str
    title: str
    description: str | None = None
    due_month: int = Field(ge=1, le=120)
    wp_ids: list[UUID] = Field(default_factory=list)
    assignment: AssignmentPayload


class DeliverableCreate(BaseModel):
    wp_ids: list[UUID] = Field(min_length=1)
    code: str
    title: str
    description: str | None = None
    due_month: int = Field(ge=1, le=120)
    workflow_status: str = "draft"
    review_due_month: int | None = Field(default=None, ge=1, le=120)
    review_owner_member_id: UUID | None = None
    assignment: AssignmentPayload


class MilestoneUpdate(BaseModel):
    code: str
    title: str
    description: str | None = None
    due_month: int = Field(ge=1, le=120)
    wp_ids: list[UUID] = Field(default_factory=list)
    assignment: AssignmentPayload


class DeliverableUpdate(BaseModel):
    code: str
    title: str
    description: str | None = None
    due_month: int = Field(ge=1, le=120)
    wp_ids: list[UUID] = Field(min_length=1)
    workflow_status: str = "draft"
    review_due_month: int | None = Field(default=None, ge=1, le=120)
    review_owner_member_id: UUID | None = None
    assignment: AssignmentPayload


class WorkEntityRead(BaseModel):
    id: str
    project_id: str
    code: str
    title: str
    description: str | None = None
    wp_id: str | None = None
    wp_ids: list[str] = Field(default_factory=list)
    start_month: int | None = None
    end_month: int | None = None
    due_month: int | None = None
    execution_status: str | None = None
    completed_at: datetime | None = None
    completed_by_member_id: str | None = None
    completion_note: str | None = None
    workflow_status: str | None = None
    review_due_month: int | None = None
    review_owner_member_id: str | None = None
    is_trashed: bool = False
    trashed_at: datetime | None = None
    leader_organization_id: str
    responsible_person_id: str
    collaborating_partner_ids: list[str] = Field(default_factory=list)


class WorkEntityListRead(PaginatedResponse):
    items: list[WorkEntityRead]


class AssignmentUpdate(BaseModel):
    leader_organization_id: UUID
    responsible_person_id: UUID
    collaborating_partner_ids: list[UUID] = Field(default_factory=list)


class AssignmentMatrixRowRead(BaseModel):
    entity_type: str
    entity_id: str
    code: str
    title: str
    wp_id: str | None = None
    leader_organization_id: str
    responsible_person_id: str
    collaborating_partner_ids: list[str] = Field(default_factory=list)


class AssignmentMatrixRead(PaginatedResponse):
    items: list[AssignmentMatrixRowRead]


class TrashedWorkEntityRead(BaseModel):
    entity_type: str
    entity: WorkEntityRead


class TrashedWorkEntityListRead(PaginatedResponse):
    items: list[TrashedWorkEntityRead]
