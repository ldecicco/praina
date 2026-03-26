from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth import UserAccount
from app.models.course import Course
from app.models.project import Project, ProjectKind
from app.models.research import BibliographyReference
from app.models.teaching import (
    TeachingArtifactStatus,
    TeachingArtifactType,
    TeachingBlockerSeverity,
    TeachingBlockerStatus,
    TeachingMilestoneStatus,
    TeachingProgressReport,
    TeachingProjectArtifact,
    TeachingProjectAssessment,
    TeachingProjectBackgroundMaterial,
    TeachingProjectBlocker,
    TeachingProjectHealth,
    TeachingProjectMilestone,
    TeachingProjectProfile,
    TeachingProjectStatus,
    TeachingProjectStudent,
)
from app.services.teaching_ai_service import TeachingAIService
from app.services.onboarding_service import NotFoundError, ValidationError


class TeachingService:
    def __init__(self, db: Session):
        self.db = db
        self.ai_service = TeachingAIService(db)

    def get_workspace(self, project_id: uuid.UUID) -> dict[str, object]:
        profile = self.ensure_profile(project_id)
        assessment = self.db.scalar(
            select(TeachingProjectAssessment).where(TeachingProjectAssessment.project_id == project_id)
        )
        return {
            "profile": profile,
            "students": self.list_students(project_id, page=1, page_size=200)[0],
            "artifacts": self.list_artifacts(project_id, page=1, page_size=200)[0],
            "background_materials": self.list_background_materials(project_id, page=1, page_size=200)[0],
            "progress_reports": self.list_progress_reports(project_id, page=1, page_size=200)[0],
            "milestones": self.list_milestones(project_id, page=1, page_size=200)[0],
            "blockers": self.list_blockers(project_id, page=1, page_size=200)[0],
            "assessment": assessment,
        }

    def ensure_profile(self, project_id: uuid.UUID) -> TeachingProjectProfile:
        project = self._get_project(project_id)
        profile = self.db.scalar(
            select(TeachingProjectProfile).where(TeachingProjectProfile.project_id == project_id)
        )
        if profile:
            return profile
        profile = TeachingProjectProfile(project_id=project_id)
        self.db.add(profile)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update_profile(self, project_id: uuid.UUID, **fields) -> TeachingProjectProfile:
        profile = self.ensure_profile(project_id)
        next_course_id = profile.course_id
        for key, value in fields.items():
            if value is None and key not in {"final_grade", "responsible_user_id"}:
                continue
            if key == "course_id":
                value = uuid.UUID(value) if value else None
                if value:
                    course = self.db.scalar(select(Course).where(Course.id == value))
                    if not course:
                        raise NotFoundError("Course not found.")
                next_course_id = value
            if key == "responsible_user_id":
                value = uuid.UUID(value) if value else None
                if value:
                    self._validate_responsible_user(next_course_id, value)
            if key == "status" and value is not None:
                value = TeachingProjectStatus(value)
            if key == "health" and value is not None:
                value = TeachingProjectHealth(value)
            setattr(profile, key, value)
        if profile.final_grade is not None:
            profile.finalized_at = datetime.now(timezone.utc)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def list_students(self, project_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[TeachingProjectStudent], int]:
        self._get_project(project_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(TeachingProjectStudent).where(TeachingProjectStudent.project_id == project_id))
            or 0
        )
        items = self.db.scalars(
            select(TeachingProjectStudent)
            .where(TeachingProjectStudent.project_id == project_id)
            .order_by(TeachingProjectStudent.full_name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_student(self, project_id: uuid.UUID, *, full_name: str, email: str | None) -> TeachingProjectStudent:
        self._get_project(project_id)
        item = TeachingProjectStudent(project_id=project_id, full_name=full_name.strip(), email=(email or "").strip() or None)
        self.db.add(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_student(self, project_id: uuid.UUID, student_id: uuid.UUID, **fields) -> TeachingProjectStudent:
        item = self._get_student(project_id, student_id)
        if "full_name" in fields and fields["full_name"] is not None:
            item.full_name = fields["full_name"].strip()
        if "email" in fields:
            item.email = (fields["email"] or "").strip() or None
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_student(self, project_id: uuid.UUID, student_id: uuid.UUID) -> None:
        item = self._get_student(project_id, student_id)
        self.db.delete(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()

    def list_artifacts(self, project_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[TeachingProjectArtifact], int]:
        self._get_project(project_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(TeachingProjectArtifact).where(TeachingProjectArtifact.project_id == project_id))
            or 0
        )
        items = self.db.scalars(
            select(TeachingProjectArtifact)
            .where(TeachingProjectArtifact.project_id == project_id)
            .order_by(TeachingProjectArtifact.required.desc(), TeachingProjectArtifact.label.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_artifact(self, project_id: uuid.UUID, **fields) -> TeachingProjectArtifact:
        self._get_project(project_id)
        artifact_type = TeachingArtifactType(fields["artifact_type"])
        external_url = (fields.get("external_url") or "").strip() or None
        document_key = uuid.UUID(fields["document_key"]) if fields.get("document_key") else None
        self._validate_artifact_payload(artifact_type, external_url, document_key)
        item = TeachingProjectArtifact(
            project_id=project_id,
            artifact_type=artifact_type,
            label=fields["label"].strip(),
            required=bool(fields.get("required", False)),
            status=TeachingArtifactStatus(fields.get("status") or TeachingArtifactStatus.missing.value),
            document_key=document_key,
            external_url=external_url,
            notes=fields.get("notes"),
            submitted_at=fields.get("submitted_at"),
        )
        self.db.add(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_artifact(self, project_id: uuid.UUID, artifact_id: uuid.UUID, **fields) -> TeachingProjectArtifact:
        item = self._get_artifact(project_id, artifact_id)
        artifact_type = TeachingArtifactType(fields.get("artifact_type") or item.artifact_type.value)
        external_url = (fields.get("external_url") if "external_url" in fields else item.external_url) or None
        document_key_raw = fields.get("document_key") if "document_key" in fields else (str(item.document_key) if item.document_key else None)
        document_key = uuid.UUID(document_key_raw) if document_key_raw else None
        self._validate_artifact_payload(artifact_type, external_url, document_key)
        if "label" in fields and fields["label"] is not None:
            item.label = fields["label"].strip()
        if "required" in fields and fields["required"] is not None:
            item.required = bool(fields["required"])
        if "status" in fields and fields["status"] is not None:
            item.status = TeachingArtifactStatus(fields["status"])
        item.artifact_type = artifact_type
        item.document_key = document_key
        item.external_url = external_url
        if "notes" in fields:
            item.notes = fields["notes"]
        if "submitted_at" in fields:
            item.submitted_at = fields["submitted_at"]
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_artifact(self, project_id: uuid.UUID, artifact_id: uuid.UUID) -> None:
        item = self._get_artifact(project_id, artifact_id)
        self.db.delete(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()

    def list_background_materials(
        self, project_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[TeachingProjectBackgroundMaterial], int]:
        self._get_project(project_id)
        total = int(
            self.db.scalar(
                select(func.count()).select_from(TeachingProjectBackgroundMaterial).where(
                    TeachingProjectBackgroundMaterial.project_id == project_id
                )
            )
            or 0
        )
        items = self.db.scalars(
            select(TeachingProjectBackgroundMaterial)
            .where(TeachingProjectBackgroundMaterial.project_id == project_id)
            .order_by(TeachingProjectBackgroundMaterial.created_at.asc(), TeachingProjectBackgroundMaterial.title.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_background_material(self, project_id: uuid.UUID, **fields) -> TeachingProjectBackgroundMaterial:
        self._get_project(project_id)
        bibliography_reference_id = uuid.UUID(fields["bibliography_reference_id"]) if fields.get("bibliography_reference_id") else None
        if bibliography_reference_id and not self.db.get(BibliographyReference, bibliography_reference_id):
            raise NotFoundError("Bibliography reference not found.")
        item = TeachingProjectBackgroundMaterial(
            project_id=project_id,
            material_type=(fields.get("material_type") or "other").strip(),
            title=fields["title"].strip(),
            bibliography_reference_id=bibliography_reference_id,
            document_key=uuid.UUID(fields["document_key"]) if fields.get("document_key") else None,
            external_url=(fields.get("external_url") or "").strip() or None,
            notes=fields.get("notes"),
        )
        self.db.add(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_background_material(
        self, project_id: uuid.UUID, material_id: uuid.UUID, **fields
    ) -> TeachingProjectBackgroundMaterial:
        item = self._get_background_material(project_id, material_id)
        if "material_type" in fields and fields["material_type"] is not None:
            item.material_type = fields["material_type"].strip()
        if "title" in fields and fields["title"] is not None:
            item.title = fields["title"].strip()
        if "bibliography_reference_id" in fields:
            bibliography_reference_id = uuid.UUID(fields["bibliography_reference_id"]) if fields["bibliography_reference_id"] else None
            if bibliography_reference_id and not self.db.get(BibliographyReference, bibliography_reference_id):
                raise NotFoundError("Bibliography reference not found.")
            item.bibliography_reference_id = bibliography_reference_id
        if "document_key" in fields:
            item.document_key = uuid.UUID(fields["document_key"]) if fields["document_key"] else None
        if "external_url" in fields:
            item.external_url = (fields["external_url"] or "").strip() or None
        if "notes" in fields:
            item.notes = fields["notes"]
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_background_material(self, project_id: uuid.UUID, material_id: uuid.UUID) -> None:
        item = self._get_background_material(project_id, material_id)
        self.db.delete(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()

    def list_progress_reports(self, project_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[TeachingProgressReport], int]:
        self._get_project(project_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(TeachingProgressReport).where(TeachingProgressReport.project_id == project_id))
            or 0
        )
        items = self.db.scalars(
            select(TeachingProgressReport)
            .where(TeachingProgressReport.project_id == project_id)
            .order_by(TeachingProgressReport.report_date.desc().nullslast(), TeachingProgressReport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_progress_report(self, project_id: uuid.UUID, **fields) -> TeachingProgressReport:
        self._get_project(project_id)
        blocker_updates = fields.pop("blocker_updates", [])
        item = TeachingProgressReport(project_id=project_id, **self._normalize_report_fields(fields))
        self.db.add(item)
        self.db.flush()
        self._apply_report_blocker_updates(project_id, item.id, blocker_updates)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_progress_report(self, project_id: uuid.UUID, report_id: uuid.UUID, **fields) -> TeachingProgressReport:
        item = self._get_progress_report(project_id, report_id)
        blocker_updates = fields.pop("blocker_updates", None)
        for key, value in self._normalize_report_fields(fields, partial=True).items():
            setattr(item, key, value)
        self.db.flush()
        if blocker_updates is not None:
            self._apply_report_blocker_updates(project_id, item.id, blocker_updates)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_progress_report(self, project_id: uuid.UUID, report_id: uuid.UUID) -> None:
        item = self._get_progress_report(project_id, report_id)
        self.db.delete(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()

    def list_milestones(self, project_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[TeachingProjectMilestone], int]:
        self._get_project(project_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(TeachingProjectMilestone).where(TeachingProjectMilestone.project_id == project_id))
            or 0
        )
        items = self.db.scalars(
            select(TeachingProjectMilestone)
            .where(TeachingProjectMilestone.project_id == project_id)
            .order_by(TeachingProjectMilestone.due_at.asc().nullslast(), TeachingProjectMilestone.label.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_milestone(self, project_id: uuid.UUID, **fields) -> TeachingProjectMilestone:
        self._get_project(project_id)
        item = TeachingProjectMilestone(
            project_id=project_id,
            kind=fields["kind"].strip(),
            label=fields["label"].strip(),
            due_at=fields.get("due_at"),
            completed_at=fields.get("completed_at"),
            status=TeachingMilestoneStatus(fields.get("status") or TeachingMilestoneStatus.pending.value),
        )
        self.db.add(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_milestone(self, project_id: uuid.UUID, milestone_id: uuid.UUID, **fields) -> TeachingProjectMilestone:
        item = self._get_milestone(project_id, milestone_id)
        if "kind" in fields and fields["kind"] is not None:
            item.kind = fields["kind"].strip()
        if "label" in fields and fields["label"] is not None:
            item.label = fields["label"].strip()
        if "due_at" in fields:
            item.due_at = fields["due_at"]
        if "completed_at" in fields:
            item.completed_at = fields["completed_at"]
        if "status" in fields and fields["status"] is not None:
            item.status = TeachingMilestoneStatus(fields["status"])
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_milestone(self, project_id: uuid.UUID, milestone_id: uuid.UUID) -> None:
        item = self._get_milestone(project_id, milestone_id)
        self.db.delete(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()

    def list_blockers(self, project_id: uuid.UUID, *, page: int, page_size: int) -> tuple[list[TeachingProjectBlocker], int]:
        self._get_project(project_id)
        total = int(
            self.db.scalar(select(func.count()).select_from(TeachingProjectBlocker).where(TeachingProjectBlocker.project_id == project_id))
            or 0
        )
        items = self.db.scalars(
            select(TeachingProjectBlocker)
            .where(TeachingProjectBlocker.project_id == project_id)
            .order_by(TeachingProjectBlocker.status.asc(), TeachingProjectBlocker.severity.desc(), TeachingProjectBlocker.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_blocker(self, project_id: uuid.UUID, **fields) -> TeachingProjectBlocker:
        self._get_project(project_id)
        item = TeachingProjectBlocker(
            project_id=project_id,
            title=fields["title"].strip(),
            description=fields.get("description"),
            severity=TeachingBlockerSeverity(fields.get("severity") or TeachingBlockerSeverity.medium.value),
            status=TeachingBlockerStatus(fields.get("status") or TeachingBlockerStatus.open.value),
            detected_from=fields.get("detected_from"),
            opened_at=fields.get("opened_at"),
            resolved_at=fields.get("resolved_at"),
        )
        self.db.add(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_blocker(self, project_id: uuid.UUID, blocker_id: uuid.UUID, **fields) -> TeachingProjectBlocker:
        item = self._get_blocker(project_id, blocker_id)
        if "title" in fields and fields["title"] is not None:
            item.title = fields["title"].strip()
        if "description" in fields:
            item.description = fields["description"]
        if "severity" in fields and fields["severity"] is not None:
            item.severity = TeachingBlockerSeverity(fields["severity"])
        if "status" in fields and fields["status"] is not None:
            item.status = TeachingBlockerStatus(fields["status"])
        if "detected_from" in fields:
            item.detected_from = fields["detected_from"]
        if "opened_at" in fields:
            item.opened_at = fields["opened_at"]
        if "resolved_at" in fields:
            item.resolved_at = fields["resolved_at"]
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_blocker(self, project_id: uuid.UUID, blocker_id: uuid.UUID) -> None:
        item = self._get_blocker(project_id, blocker_id)
        self.db.delete(item)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()

    def upsert_assessment(self, project_id: uuid.UUID, **fields) -> TeachingProjectAssessment:
        self._get_project(project_id)
        item = self.db.scalar(
            select(TeachingProjectAssessment).where(TeachingProjectAssessment.project_id == project_id)
        )
        if not item:
            item = TeachingProjectAssessment(project_id=project_id)
            self.db.add(item)
        for key, value in fields.items():
            if key == "grader_user_id" and value:
                value = uuid.UUID(value)
                self._get_user(value)
            setattr(item, key, value)
        self.ai_service.rebuild_project_chunks(project_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def can_manage_project(self, project_id: uuid.UUID, user_id: uuid.UUID, platform_role: str) -> bool:
        if platform_role == "super_admin":
            return True
        profile = self.ensure_profile(project_id)
        if not profile.course_id:
            return False
        course = self.db.scalar(select(Course).where(Course.id == profile.course_id))
        if not course:
            return False
        if course.teacher_user_id == user_id:
            return True
        return self._is_teaching_assistant(profile.course_id, user_id)

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise NotFoundError("Project not found.")
        if (getattr(project, "project_kind", ProjectKind.funded.value) or ProjectKind.funded.value) != ProjectKind.teaching.value:
            raise ValidationError("Project is not a teaching project.")
        return project

    def _get_user(self, user_id: uuid.UUID) -> UserAccount:
        user = self.db.scalar(select(UserAccount).where(UserAccount.id == user_id))
        if not user:
            raise NotFoundError("User not found.")
        return user

    def _is_teaching_assistant(self, course_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        from app.models.course import CourseTeachingAssistant

        row = self.db.scalar(
            select(CourseTeachingAssistant).where(
                CourseTeachingAssistant.course_id == course_id,
                CourseTeachingAssistant.user_id == user_id,
            )
        )
        return row is not None

    def _validate_responsible_user(self, course_id: uuid.UUID | None, user_id: uuid.UUID) -> None:
        self._get_user(user_id)
        if not course_id:
            raise ValidationError("Select a course before assigning the responsible user.")
        course = self.db.scalar(select(Course).where(Course.id == course_id))
        if not course:
            raise NotFoundError("Course not found.")
        if course.teacher_user_id == user_id:
            return
        if self._is_teaching_assistant(course_id, user_id):
            return
        raise ValidationError("Responsible user must be the course teacher or one of its teaching assistants.")

    def _get_student(self, project_id: uuid.UUID, student_id: uuid.UUID) -> TeachingProjectStudent:
        item = self.db.scalar(
            select(TeachingProjectStudent).where(
                TeachingProjectStudent.project_id == project_id,
                TeachingProjectStudent.id == student_id,
            )
        )
        if not item:
            raise NotFoundError("Teaching student not found.")
        return item

    def _get_artifact(self, project_id: uuid.UUID, artifact_id: uuid.UUID) -> TeachingProjectArtifact:
        item = self.db.scalar(
            select(TeachingProjectArtifact).where(
                TeachingProjectArtifact.project_id == project_id,
                TeachingProjectArtifact.id == artifact_id,
            )
        )
        if not item:
            raise NotFoundError("Teaching artifact not found.")
        return item

    def _get_progress_report(self, project_id: uuid.UUID, report_id: uuid.UUID) -> TeachingProgressReport:
        item = self.db.scalar(
            select(TeachingProgressReport).where(
                TeachingProgressReport.project_id == project_id,
                TeachingProgressReport.id == report_id,
            )
        )
        if not item:
            raise NotFoundError("Teaching progress report not found.")
        return item

    def _get_background_material(
        self, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> TeachingProjectBackgroundMaterial:
        item = self.db.scalar(
            select(TeachingProjectBackgroundMaterial).where(
                TeachingProjectBackgroundMaterial.project_id == project_id,
                TeachingProjectBackgroundMaterial.id == material_id,
            )
        )
        if not item:
            raise NotFoundError("Background material not found.")
        return item

    def _get_milestone(self, project_id: uuid.UUID, milestone_id: uuid.UUID) -> TeachingProjectMilestone:
        item = self.db.scalar(
            select(TeachingProjectMilestone).where(
                TeachingProjectMilestone.project_id == project_id,
                TeachingProjectMilestone.id == milestone_id,
            )
        )
        if not item:
            raise NotFoundError("Teaching milestone not found.")
        return item

    def _get_blocker(self, project_id: uuid.UUID, blocker_id: uuid.UUID) -> TeachingProjectBlocker:
        item = self.db.scalar(
            select(TeachingProjectBlocker).where(
                TeachingProjectBlocker.project_id == project_id,
                TeachingProjectBlocker.id == blocker_id,
            )
        )
        if not item:
            raise NotFoundError("Teaching blocker not found.")
        return item

    @staticmethod
    def _normalize_report_fields(fields: dict, partial: bool = False) -> dict:
        normalized: dict[str, object] = {}
        for key in (
            "report_date",
            "meeting_date",
            "work_done_markdown",
            "next_steps_markdown",
            "supervisor_feedback_markdown",
            "attachment_document_keys",
            "transcript_document_keys",
            "submitted_at",
        ):
            if key not in fields:
                continue
            if key in {"attachment_document_keys", "transcript_document_keys"}:
                normalized[key] = [str(item) for item in (fields[key] or []) if str(item).strip()]
                continue
            normalized[key] = fields[key]
        if not partial:
            normalized.setdefault("work_done_markdown", "")
            normalized.setdefault("next_steps_markdown", "")
            normalized.setdefault("attachment_document_keys", [])
            normalized.setdefault("transcript_document_keys", [])
        return normalized

    def list_blockers_for_report(self, project_id: uuid.UUID, report_id: uuid.UUID) -> list[TeachingProjectBlocker]:
        return list(
            self.db.scalars(
                select(TeachingProjectBlocker)
                .where(
                    TeachingProjectBlocker.project_id == project_id,
                    (TeachingProjectBlocker.source_report_id == report_id) | (TeachingProjectBlocker.last_report_id == report_id),
                )
                .order_by(TeachingProjectBlocker.created_at.asc())
            ).all()
        )

    def _apply_report_blocker_updates(
        self,
        project_id: uuid.UUID,
        report_id: uuid.UUID,
        blocker_updates: list[dict] | list[object],
    ) -> None:
        if not blocker_updates:
            return
        for raw in blocker_updates:
            data = raw if isinstance(raw, dict) else raw.model_dump()
            blocker_id = data.get("id")
            if blocker_id:
                blocker = self._get_blocker(project_id, uuid.UUID(blocker_id))
                blocker.title = data["title"].strip()
                blocker.description = data.get("description")
                blocker.severity = TeachingBlockerSeverity(data.get("severity") or blocker.severity.value)
                blocker.status = TeachingBlockerStatus(data.get("status") or blocker.status.value)
                blocker.last_report_id = report_id
                if blocker.status == TeachingBlockerStatus.resolved and blocker.resolved_at is None:
                    blocker.resolved_at = datetime.now(timezone.utc)
            else:
                blocker = TeachingProjectBlocker(
                    project_id=project_id,
                    title=data["title"].strip(),
                    description=data.get("description"),
                    severity=TeachingBlockerSeverity(data.get("severity") or TeachingBlockerSeverity.medium.value),
                    status=TeachingBlockerStatus(data.get("status") or TeachingBlockerStatus.open.value),
                    detected_from="progress_report",
                    source_report_id=report_id,
                    last_report_id=report_id,
                    opened_at=datetime.now(timezone.utc),
                )
                self.db.add(blocker)
        self.db.flush()

    @staticmethod
    def _validate_artifact_payload(
        artifact_type: TeachingArtifactType, external_url: str | None, document_key: uuid.UUID | None
    ) -> None:
        if artifact_type == TeachingArtifactType.repository and not external_url:
            raise ValidationError("Repository artifacts require an external_url.")
