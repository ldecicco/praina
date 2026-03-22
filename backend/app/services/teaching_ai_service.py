from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.course import CourseMaterial
from app.models.document import ProjectDocument
from app.models.teaching import (
    TeachingChunk,
    TeachingProgressReport,
    TeachingProjectArtifact,
    TeachingProjectBlocker,
    TeachingProjectProfile,
)
from app.services.text_extraction import chunk_text


class TeachingAIService:
    def __init__(self, db: Session):
        self.db = db

    def rebuild_project_chunks(self, project_id: uuid.UUID) -> int:
        self.db.execute(delete(TeachingChunk).where(TeachingChunk.project_id == project_id))

        chunks: list[TeachingChunk] = []
        chunks.extend(self._profile_chunks(project_id))
        chunks.extend(self._artifact_chunks(project_id))
        chunks.extend(self._blocker_chunks(project_id))
        chunks.extend(self._progress_report_chunks(project_id))
        chunks.extend(self._course_material_chunks(project_id))

        for item in chunks:
            self.db.add(item)
        self.db.flush()
        return len(chunks)

    def rebuild_for_course(self, course_id: uuid.UUID) -> int:
        project_ids = [
            item
            for item in self.db.scalars(
                select(TeachingProjectProfile.project_id).where(TeachingProjectProfile.course_id == course_id)
            ).all()
        ]
        total = 0
        for project_id in project_ids:
            total += self.rebuild_project_chunks(project_id)
        return total

    def _profile_chunks(self, project_id: uuid.UUID) -> list[TeachingChunk]:
        profile = self.db.scalar(select(TeachingProjectProfile).where(TeachingProjectProfile.project_id == project_id))
        if not profile:
            return []

        parts: list[str] = []
        if profile.functional_objectives_markdown:
            parts.append("Functional Objectives\n" + profile.functional_objectives_markdown.strip())
        if profile.specifications_markdown:
            parts.append("Specifications\n" + profile.specifications_markdown.strip())
        if not parts:
            return []
        return self._make_chunks(
            project_id=project_id,
            source_type="profile",
            source_id=profile.id,
            text="\n\n".join(parts),
        )

    def _artifact_chunks(self, project_id: uuid.UUID) -> list[TeachingChunk]:
        artifacts = self.db.scalars(
            select(TeachingProjectArtifact)
            .where(TeachingProjectArtifact.project_id == project_id)
            .order_by(TeachingProjectArtifact.required.desc(), TeachingProjectArtifact.label.asc())
        ).all()
        chunks: list[TeachingChunk] = []
        for artifact in artifacts:
            text_parts = [
                f"Artifact: {artifact.label}",
                f"Type: {artifact.artifact_type.value}",
                f"Required: {'yes' if artifact.required else 'no'}",
                f"Status: {artifact.status.value}",
            ]
            if artifact.external_url:
                text_parts.append(f"URL: {artifact.external_url}")
            if artifact.notes:
                text_parts.append(f"Notes:\n{artifact.notes.strip()}")
            chunks.extend(
                self._make_chunks(
                    project_id=project_id,
                    source_type="artifact",
                    source_id=artifact.id,
                    text="\n".join(text_parts),
                )
            )
        return chunks

    def _blocker_chunks(self, project_id: uuid.UUID) -> list[TeachingChunk]:
        blockers = self.db.scalars(
            select(TeachingProjectBlocker)
            .where(TeachingProjectBlocker.project_id == project_id)
            .order_by(TeachingProjectBlocker.created_at.desc())
        ).all()
        chunks: list[TeachingChunk] = []
        for blocker in blockers:
            text_parts = [
                f"Blocker: {blocker.title}",
                f"Severity: {blocker.severity.value}",
                f"Status: {blocker.status.value}",
            ]
            if blocker.detected_from:
                text_parts.append(f"Detected From: {blocker.detected_from}")
            if blocker.description:
                text_parts.append(f"Description:\n{blocker.description.strip()}")
            chunks.extend(
                self._make_chunks(
                    project_id=project_id,
                    source_type="blocker",
                    source_id=blocker.id,
                    text="\n".join(text_parts),
                )
            )
        return chunks

    def _progress_report_chunks(self, project_id: uuid.UUID) -> list[TeachingChunk]:
        reports = self.db.scalars(
            select(TeachingProgressReport)
            .where(TeachingProgressReport.project_id == project_id)
            .order_by(TeachingProgressReport.report_date.desc().nullslast(), TeachingProgressReport.created_at.desc())
        ).all()
        document_titles = {
            str(item.document_key): item.title
            for item in self.db.scalars(
                select(ProjectDocument)
                .where(ProjectDocument.project_id == project_id)
                .order_by(ProjectDocument.updated_at.desc(), ProjectDocument.version.desc())
            ).all()
        }
        chunks: list[TeachingChunk] = []
        for report in reports:
            text_parts = []
            if report.report_date:
                text_parts.append(f"Report Date: {report.report_date.isoformat()}")
            if report.meeting_date:
                text_parts.append(f"Meeting Date: {report.meeting_date.isoformat()}")
            if report.work_done_markdown:
                text_parts.append("Work Done\n" + report.work_done_markdown.strip())
            if report.next_steps_markdown:
                text_parts.append("Next Steps\n" + report.next_steps_markdown.strip())
            if report.supervisor_feedback_markdown:
                text_parts.append("Supervisor Feedback\n" + report.supervisor_feedback_markdown.strip())
            if report.attachment_document_keys:
                text_parts.append(
                    "Attachments: " + ", ".join(document_titles.get(str(key), str(key)) for key in report.attachment_document_keys)
                )
            if report.transcript_document_keys:
                text_parts.append(
                    "Transcript Documents: " + ", ".join(document_titles.get(str(key), str(key)) for key in report.transcript_document_keys)
                )
            chunks.extend(
                self._make_chunks(
                    project_id=project_id,
                    source_type="progress_report",
                    source_id=report.id,
                    text="\n\n".join(part for part in text_parts if part.strip()),
                )
            )
        return chunks

    def _course_material_chunks(self, project_id: uuid.UUID) -> list[TeachingChunk]:
        profile = self.db.scalar(select(TeachingProjectProfile).where(TeachingProjectProfile.project_id == project_id))
        if not profile or not profile.course_id:
            return []
        materials = self.db.scalars(
            select(CourseMaterial)
            .where(CourseMaterial.course_id == profile.course_id)
            .order_by(CourseMaterial.sort_order.asc(), CourseMaterial.title.asc())
        ).all()
        chunks: list[TeachingChunk] = []
        for material in materials:
            text_parts = [
                f"Course Material: {material.title}",
                f"Type: {material.material_type.value}",
            ]
            if material.content_markdown:
                text_parts.append(material.content_markdown.strip())
            if material.external_url:
                text_parts.append(f"URL: {material.external_url}")
            chunks.extend(
                self._make_chunks(
                    project_id=project_id,
                    source_type="course_material",
                    source_id=material.id,
                    text="\n\n".join(part for part in text_parts if part.strip()),
                )
            )
        return chunks

    def _make_chunks(self, *, project_id: uuid.UUID, source_type: str, source_id: uuid.UUID, text: str) -> list[TeachingChunk]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []
        return [
            TeachingChunk(
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=index,
                content=content,
                embedding=None,
            )
            for index, content in enumerate(chunk_text(cleaned))
        ]
