from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import PaginatedResponse


class PartnerCreate(BaseModel):
    short_name: str = Field(min_length=2, max_length=32)
    legal_name: str = Field(min_length=2, max_length=255)


class PartnerRead(BaseModel):
    id: str
    project_id: str
    short_name: str
    legal_name: str


class TeamCreate(BaseModel):
    organization_id: UUID
    name: str = Field(min_length=2, max_length=120)


class TeamRead(BaseModel):
    id: str
    project_id: str
    organization_id: str
    name: str


class TeamMemberCreate(BaseModel):
    organization_id: UUID
    team_id: UUID
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    role: str = Field(min_length=2, max_length=80)


class TeamMemberRead(BaseModel):
    id: str
    project_id: str
    organization_id: str
    team_id: str
    full_name: str
    email: str
    role: str
    is_active: bool


class PartnerListRead(PaginatedResponse):
    items: list[PartnerRead]


class TeamListRead(PaginatedResponse):
    items: list[TeamRead]


class TeamMemberListRead(PaginatedResponse):
    items: list[TeamMemberRead]
