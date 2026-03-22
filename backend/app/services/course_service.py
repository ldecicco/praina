from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import UserAccount
from app.models.course import Course, CourseMaterial, CourseMaterialType, CourseTeachingAssistant
from app.models.teaching import TeachingProjectProfile
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.teaching_ai_service import TeachingAIService


class CourseService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = TeachingAIService(db)

    def list_courses(
        self,
        *,
        search: str | None,
        active_only: bool,
        page: int,
        page_size: int,
        actor_user_id: uuid.UUID | None = None,
        actor_platform_role: str | None = None,
    ) -> tuple[list[Course], int]:
        filters = []
        if active_only:
            filters.append(Course.is_active.is_(True))
        if search:
            token = f"%{search.strip()}%"
            filters.append(or_(Course.code.ilike(token), Course.title.ilike(token)))

        stmt = select(Course)
        count_stmt = select(func.count()).select_from(Course)
        if actor_user_id and actor_platform_role != "super_admin":
            stmt = stmt.outerjoin(CourseTeachingAssistant, CourseTeachingAssistant.course_id == Course.id).where(
                (Course.teacher_user_id == actor_user_id) | (CourseTeachingAssistant.user_id == actor_user_id)
            ).distinct()
            count_stmt = (
                select(func.count(func.distinct(Course.id)))
                .select_from(Course)
                .outerjoin(CourseTeachingAssistant, CourseTeachingAssistant.course_id == Course.id)
                .where((Course.teacher_user_id == actor_user_id) | (CourseTeachingAssistant.user_id == actor_user_id))
            )
        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        total = int(self.db.scalar(count_stmt) or 0)
        items = self.db.scalars(
            stmt.order_by(Course.code.asc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(items), total

    def get_course(self, course_id: uuid.UUID) -> Course:
        item = self.db.scalar(select(Course).where(Course.id == course_id))
        if not item:
            raise NotFoundError("Course not found.")
        return item

    def get_teacher(self, course_id: uuid.UUID) -> UserAccount | None:
        course = self.get_course(course_id)
        if not course.teacher_user_id:
            return None
        return self.db.scalar(select(UserAccount).where(UserAccount.id == course.teacher_user_id))

    def list_teaching_assistants(self, course_id: uuid.UUID) -> list[UserAccount]:
        self.get_course(course_id)
        rows = self.db.scalars(
            select(UserAccount)
            .join(CourseTeachingAssistant, CourseTeachingAssistant.user_id == UserAccount.id)
            .where(CourseTeachingAssistant.course_id == course_id)
            .order_by(UserAccount.display_name.asc(), UserAccount.email.asc())
        ).all()
        return list(rows)

    def list_materials(self, course_id: uuid.UUID) -> list[CourseMaterial]:
        self.get_course(course_id)
        rows = self.db.scalars(
            select(CourseMaterial)
            .where(CourseMaterial.course_id == course_id)
            .order_by(CourseMaterial.sort_order.asc(), CourseMaterial.title.asc(), CourseMaterial.created_at.asc())
        ).all()
        return list(rows)

    def create_course(
        self,
        *,
        code: str,
        title: str,
        description: str | None,
        is_active: bool,
        has_project_deadlines: bool,
        teacher_user_id: str | None = None,
    ) -> Course:
        teacher_id = self._normalize_user_id(teacher_user_id) if teacher_user_id else None
        item = Course(
            code=code.strip(),
            title=title.strip(),
            description=description,
            is_active=is_active,
            has_project_deadlines=has_project_deadlines,
            teacher_user_id=teacher_id,
        )
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Course code must be unique.") from exc
        self.db.refresh(item)
        return item

    def update_course(self, course_id: uuid.UUID, **fields) -> Course:
        item = self.get_course(course_id)
        if "code" in fields and fields["code"] is not None:
            item.code = fields["code"].strip()
        if "title" in fields and fields["title"] is not None:
            item.title = fields["title"].strip()
        if "description" in fields:
            item.description = fields["description"]
        if "is_active" in fields and fields["is_active"] is not None:
            item.is_active = bool(fields["is_active"])
        if "has_project_deadlines" in fields and fields["has_project_deadlines"] is not None:
            item.has_project_deadlines = bool(fields["has_project_deadlines"])
        if "teacher_user_id" in fields:
            item.teacher_user_id = self._normalize_user_id(fields["teacher_user_id"]) if fields["teacher_user_id"] else None
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Course code must be unique.") from exc
        self.db.refresh(item)
        return item

    def add_teaching_assistant(self, course_id: uuid.UUID, *, user_id: str) -> UserAccount:
        course = self.get_course(course_id)
        assistant_id = self._normalize_user_id(user_id)
        if course.teacher_user_id and assistant_id == course.teacher_user_id:
            raise ValidationError("Teacher cannot be added as teaching assistant.")
        existing = self.db.scalar(
            select(CourseTeachingAssistant).where(
                CourseTeachingAssistant.course_id == course_id,
                CourseTeachingAssistant.user_id == assistant_id,
            )
        )
        if existing:
            raise ConflictError("Teaching assistant already assigned.")
        row = CourseTeachingAssistant(course_id=course_id, user_id=assistant_id)
        self.db.add(row)
        self.db.commit()
        return self._get_user(assistant_id)

    def remove_teaching_assistant(self, course_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.get_course(course_id)
        row = self.db.scalar(
            select(CourseTeachingAssistant).where(
                CourseTeachingAssistant.course_id == course_id,
                CourseTeachingAssistant.user_id == user_id,
            )
        )
        if not row:
            raise NotFoundError("Teaching assistant not found.")
        assigned_project = self.db.scalar(
            select(TeachingProjectProfile).where(
                TeachingProjectProfile.course_id == course_id,
                TeachingProjectProfile.responsible_user_id == user_id,
            )
        )
        if assigned_project:
            raise ValidationError("Reassign project responsibility before removing this teaching assistant.")
        self.db.delete(row)
        self.db.commit()

    def create_material(self, course_id: uuid.UUID, **fields) -> CourseMaterial:
        self.get_course(course_id)
        item = CourseMaterial(
            course_id=course_id,
            material_type=CourseMaterialType(fields.get("material_type") or CourseMaterialType.instructions.value),
            title=fields["title"].strip(),
            content_markdown=(fields.get("content_markdown") or "").strip() or None,
            external_url=(fields.get("external_url") or "").strip() or None,
            sort_order=int(fields.get("sort_order") or 0),
        )
        self.db.add(item)
        self.ai_service.rebuild_for_course(course_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_material(self, course_id: uuid.UUID, material_id: uuid.UUID, **fields) -> CourseMaterial:
        item = self._get_material(course_id, material_id)
        if "material_type" in fields and fields["material_type"] is not None:
            item.material_type = CourseMaterialType(fields["material_type"])
        if "title" in fields and fields["title"] is not None:
            item.title = fields["title"].strip()
        if "content_markdown" in fields:
            item.content_markdown = (fields["content_markdown"] or "").strip() or None
        if "external_url" in fields:
            item.external_url = (fields["external_url"] or "").strip() or None
        if "sort_order" in fields and fields["sort_order"] is not None:
            item.sort_order = int(fields["sort_order"])
        self.ai_service.rebuild_for_course(course_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_material(self, course_id: uuid.UUID, material_id: uuid.UUID) -> None:
        item = self._get_material(course_id, material_id)
        self.db.delete(item)
        self.ai_service.rebuild_for_course(course_id)
        self.db.commit()

    def can_manage_tas(self, course_id: uuid.UUID, user_id: uuid.UUID, platform_role: str) -> bool:
        if platform_role == "super_admin":
            return True
        course = self.get_course(course_id)
        return bool(course.teacher_user_id and course.teacher_user_id == user_id)

    def is_course_staff_user(self, course_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        course = self.get_course(course_id)
        if course.teacher_user_id == user_id:
            return True
        row = self.db.scalar(
            select(CourseTeachingAssistant).where(
                CourseTeachingAssistant.course_id == course_id,
                CourseTeachingAssistant.user_id == user_id,
            )
        )
        return row is not None

    def delete_course(self, course_id: uuid.UUID) -> None:
        item = self.get_course(course_id)
        self.db.delete(item)
        self.db.commit()

    def _normalize_user_id(self, user_id: str | uuid.UUID) -> uuid.UUID:
        identifier = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(user_id)
        self._get_user(identifier)
        return identifier

    def _get_material(self, course_id: uuid.UUID, material_id: uuid.UUID) -> CourseMaterial:
        item = self.db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.course_id == course_id,
                CourseMaterial.id == material_id,
            )
        )
        if not item:
            raise NotFoundError("Course material not found.")
        return item

    def _get_user(self, user_id: uuid.UUID) -> UserAccount:
        user = self.db.scalar(select(UserAccount).where(UserAccount.id == user_id))
        if not user:
            raise NotFoundError("User not found.")
        return user
