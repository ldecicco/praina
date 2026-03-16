from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import PaginatedResponse


class PartnerCreate(BaseModel):
    short_name: str = Field(min_length=2, max_length=32)
    legal_name: str = Field(min_length=2, max_length=255)
    partner_type: str = "beneficiary"
    country: str | None = None
    expertise: str | None = None


class PartnerUpdate(BaseModel):
    short_name: str = Field(min_length=2, max_length=32)
    legal_name: str = Field(min_length=2, max_length=255)
    partner_type: str | None = None
    country: str | None = None
    expertise: str | None = None


class PartnerRead(BaseModel):
    id: str
    project_id: str
    short_name: str
    legal_name: str
    partner_type: str
    country: str | None = None
    expertise: str | None = None


class TeamMemberCreate(BaseModel):
    partner_id: UUID
    user_id: UUID | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    role: str = Field(min_length=2, max_length=80)
    create_user_if_missing: bool = False
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)


class TeamMemberUpdate(BaseModel):
    partner_id: UUID
    user_id: UUID | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    role: str = Field(min_length=2, max_length=80)
    create_user_if_missing: bool = False
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class TeamMemberRead(BaseModel):
    id: str
    project_id: str
    partner_id: str
    user_account_id: str | None = None
    full_name: str
    email: str
    role: str
    is_active: bool
    temporary_password: str | None = None


class PartnerListRead(PaginatedResponse):
    items: list[PartnerRead]


class TeamMemberListRead(PaginatedResponse):
    items: list[TeamMemberRead]
