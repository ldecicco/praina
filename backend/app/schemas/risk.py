from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ProjectRiskCreate(BaseModel):
    code: str
    title: str
    description: str | None = None
    mitigation_plan: str | None = None
    status: str = "open"
    probability: str = "medium"
    impact: str = "medium"
    due_month: int | None = Field(default=None, ge=1, le=120)
    owner_partner_id: UUID
    owner_member_id: UUID


class ProjectRiskUpdate(BaseModel):
    code: str
    title: str
    description: str | None = None
    mitigation_plan: str | None = None
    status: str = "open"
    probability: str = "medium"
    impact: str = "medium"
    due_month: int | None = Field(default=None, ge=1, le=120)
    owner_partner_id: UUID
    owner_member_id: UUID


class ProjectRiskRead(BaseModel):
    id: str
    project_id: str
    code: str
    title: str
    description: str | None = None
    mitigation_plan: str | None = None
    status: str
    probability: str
    impact: str
    due_month: int | None = None
    owner_partner_id: str
    owner_member_id: str
    created_at: datetime
    updated_at: datetime


class ProjectRiskListRead(PaginatedResponse):
    items: list[ProjectRiskRead]
