from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import PaginatedResponse


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    platform_role: str
    is_active: bool
    can_access_research: bool
    can_access_teaching: bool
    temporary_password: str | None = None
    job_title: str | None = None
    organization: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


class MembershipRead(BaseModel):
    id: str
    project_id: str
    user_id: str
    role: str
    created_at: datetime
    updated_at: datetime


class MembershipListRead(PaginatedResponse):
    items: list[MembershipRead]


class MembershipUpsertRequest(BaseModel):
    user_id: str
    role: str


class MembershipWithUserRead(BaseModel):
    membership: MembershipRead
    user: UserRead


class MembershipWithUserListRead(PaginatedResponse):
    items: list[MembershipWithUserRead]


class AuthTokenRead(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class MeRead(BaseModel):
    user: UserRead
    memberships: list[MembershipRead]


class UserListRead(PaginatedResponse):
    items: list[UserRead]


class UserProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)


class UserAdminUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    platform_role: str | None = None
    is_active: bool | None = None
    can_access_research: bool | None = None
    can_access_teaching: bool | None = None


class UserAdminCreateRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    platform_role: str = Field(default="user")
    is_active: bool = True
    can_access_research: bool = True
    can_access_teaching: bool = True
