from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class CourseStaffUserRead(BaseModel):
    user_id: str
    display_name: str
    email: str


class CourseCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    is_active: bool = True
    has_project_deadlines: bool = True
    teacher_user_id: str | None = None


class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=64)
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    has_project_deadlines: bool | None = None
    teacher_user_id: str | None = None


class CourseTeachingAssistantCreate(BaseModel):
    user_id: str


class CourseMaterialCreate(BaseModel):
    material_type: str = "instructions"
    title: str = Field(min_length=2, max_length=255)
    content_markdown: str | None = None
    external_url: str | None = Field(default=None, max_length=512)
    sort_order: int = Field(default=0, ge=0, le=10000)


class CourseMaterialUpdate(BaseModel):
    material_type: str | None = None
    title: str | None = Field(default=None, min_length=2, max_length=255)
    content_markdown: str | None = None
    external_url: str | None = Field(default=None, max_length=512)
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class CourseMaterialRead(BaseModel):
    id: str
    course_id: str
    material_type: str
    title: str
    content_markdown: str | None
    external_url: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class CourseRead(BaseModel):
    id: str
    code: str
    title: str
    description: str | None
    is_active: bool
    has_project_deadlines: bool
    teacher: CourseStaffUserRead | None = None
    teaching_assistants: list[CourseStaffUserRead] = Field(default_factory=list)
    materials: list[CourseMaterialRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CourseListRead(PaginatedResponse):
    items: list[CourseRead]
