from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class CourseMaterialType(str, enum.Enum):
    instructions = "instructions"
    rubric = "rubric"
    template = "template"
    schedule = "schedule"
    resource = "resource"
    other = "other"


class Course(Base, IdMixin, TimestampMixin):
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    has_project_deadlines: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    teacher_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )


class CourseTeachingAssistant(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_teaching_assistants"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_teaching_assistant"),)

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)


class CourseMaterial(Base, IdMixin, TimestampMixin):
    __tablename__ = "course_materials"

    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    material_type: Mapped[CourseMaterialType] = mapped_column(
        Enum(CourseMaterialType, name="course_material_type"),
        default=CourseMaterialType.instructions,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), index=True)
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
