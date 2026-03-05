from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class AssignmentPayload(BaseModel):
    leader_organization_id: UUID
    responsible_person_id: UUID
    collaborating_team_ids: list[UUID] = Field(default_factory=list)


class WorkPackageCreate(BaseModel):
    code: str
    title: str
    description: str | None = None
    assignment: AssignmentPayload


class TaskCreate(BaseModel):
    wp_id: UUID
    code: str
    title: str
    description: str | None = None
    assignment: AssignmentPayload


class MilestoneCreate(BaseModel):
    code: str
    title: str
    description: str | None = None
    assignment: AssignmentPayload


class DeliverableCreate(BaseModel):
    wp_id: UUID | None = None
    code: str
    title: str
    description: str | None = None
    assignment: AssignmentPayload


class WorkEntityRead(BaseModel):
    id: str
    project_id: str
    code: str
    title: str
    description: str | None = None
    wp_id: str | None = None
    leader_organization_id: str
    responsible_person_id: str
    collaborating_team_ids: list[str] = Field(default_factory=list)


class WorkEntityListRead(PaginatedResponse):
    items: list[WorkEntityRead]


class AssignmentUpdate(BaseModel):
    leader_organization_id: UUID
    responsible_person_id: UUID
    collaborating_team_ids: list[UUID] = Field(default_factory=list)


class AssignmentMatrixRowRead(BaseModel):
    entity_type: str
    entity_id: str
    code: str
    title: str
    wp_id: str | None = None
    leader_organization_id: str
    responsible_person_id: str
    collaborating_team_ids: list[str] = Field(default_factory=list)


class AssignmentMatrixRead(PaginatedResponse):
    items: list[AssignmentMatrixRowRead]
