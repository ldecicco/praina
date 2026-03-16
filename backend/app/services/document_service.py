import io
import re
import uuid
from pathlib import Path
from typing import BinaryIO

import httpx
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import DocumentScope, DocumentStatus, ProjectDocument
from app.models.organization import TeamMember
from app.models.project import Project
from app.models.proposal import ProjectProposalSection
from app.models.work import Deliverable, Milestone, Task, WorkPackage
from app.schemas.document import DocumentLinkPayload, DocumentUploadPayload, DocumentVersionUploadPayload
from app.services.onboarding_service import NotFoundError, ValidationError


class DocumentService:
    def __init__(self, db: Session):
        self.db = db

    def create_document(
        self,
        project_id: uuid.UUID,
        payload: DocumentUploadPayload,
        file_name: str,
        content_type: str,
        file_stream: BinaryIO,
    ) -> ProjectDocument:
        self._get_project(project_id)
        self._validate_scope(project_id, payload)
        self._validate_uploader(project_id, payload.uploaded_by_member_id)
        self._validate_proposal_section(project_id, payload.proposal_section_id)

        safe_name = Path(file_name).name or "document.bin"
        document_key = uuid.uuid4()
        version = 1
        storage_path = self._storage_path(project_id, document_key, version, safe_name)
        file_size_bytes = self._write_file(file_stream, storage_path)

        document = ProjectDocument(
            document_key=document_key,
            project_id=project_id,
            scope=payload.scope,
            title=payload.title,
            storage_uri=str(storage_path),
            original_filename=safe_name,
            file_size_bytes=file_size_bytes,
            mime_type=content_type or "application/octet-stream",
            status=DocumentStatus.uploaded.value,
            version=version,
            metadata_json=payload.metadata_json,
            wp_id=payload.wp_id,
            task_id=payload.task_id,
            deliverable_id=payload.deliverable_id,
            milestone_id=payload.milestone_id,
            uploaded_by_member_id=payload.uploaded_by_member_id,
            proposal_section_id=payload.proposal_section_id,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def create_new_version(
        self,
        project_id: uuid.UUID,
        document_key: uuid.UUID,
        payload: DocumentVersionUploadPayload,
        file_name: str,
        content_type: str,
        file_stream: BinaryIO,
    ) -> ProjectDocument:
        self._get_project(project_id)
        latest = self.db.scalar(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id, ProjectDocument.document_key == document_key)
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if not latest:
            raise NotFoundError("Document not found in project.")

        self._validate_uploader(project_id, payload.uploaded_by_member_id)
        self._validate_proposal_section(project_id, payload.proposal_section_id)

        safe_name = Path(file_name).name or "document.bin"
        version = latest.version + 1
        storage_path = self._storage_path(project_id, document_key, version, safe_name)
        file_size_bytes = self._write_file(file_stream, storage_path)

        document = ProjectDocument(
            document_key=document_key,
            project_id=project_id,
            scope=latest.scope,
            title=payload.title or latest.title,
            storage_uri=str(storage_path),
            original_filename=safe_name,
            file_size_bytes=file_size_bytes,
            mime_type=content_type or "application/octet-stream",
            status=DocumentStatus.uploaded.value,
            version=version,
            metadata_json=payload.metadata_json if payload.metadata_json is not None else latest.metadata_json,
            wp_id=latest.wp_id,
            task_id=latest.task_id,
            deliverable_id=latest.deliverable_id,
            milestone_id=latest.milestone_id,
            uploaded_by_member_id=payload.uploaded_by_member_id,
            source_url=latest.source_url,
            source_type=latest.source_type,
            proposal_section_id=payload.proposal_section_id if payload.proposal_section_id is not None else latest.proposal_section_id,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_document_version(self, project_id: uuid.UUID, document_id: uuid.UUID) -> ProjectDocument:
        self._get_project(project_id)
        document = self.db.scalar(
            select(ProjectDocument).where(ProjectDocument.project_id == project_id, ProjectDocument.id == document_id)
        )
        if not document:
            raise NotFoundError("Document version not found in project.")
        return document

    def get_document_versions(self, project_id: uuid.UUID, document_key: uuid.UUID) -> list[ProjectDocument]:
        self._get_project(project_id)
        rows = self.db.scalars(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id, ProjectDocument.document_key == document_key)
            .order_by(ProjectDocument.version.desc())
        ).all()
        if not rows:
            raise NotFoundError("Document not found in project.")
        return list(rows)

    def list_documents(
        self,
        project_id: uuid.UUID,
        scope: DocumentScope | None = None,
        status: str | None = None,
        wp_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        deliverable_id: uuid.UUID | None = None,
        milestone_id: uuid.UUID | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ProjectDocument], int]:
        self._get_project(project_id)
        latest_sub = (
            select(
                ProjectDocument.document_key.label("document_key"),
                func.max(ProjectDocument.version).label("max_version"),
            )
            .where(ProjectDocument.project_id == project_id)
            .group_by(ProjectDocument.document_key)
            .subquery()
        )
        stmt = (
            select(ProjectDocument)
            .join(
                latest_sub,
                and_(
                    ProjectDocument.document_key == latest_sub.c.document_key,
                    ProjectDocument.version == latest_sub.c.max_version,
                ),
            )
            .where(ProjectDocument.project_id == project_id)
        )
        stmt = self._apply_document_filters(
            stmt, scope, status, wp_id, task_id, deliverable_id, milestone_id, search
        )

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(self.db.scalar(total_stmt) or 0)
        rows = self.db.scalars(
            stmt.order_by(ProjectDocument.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = list(rows)
        if not items:
            return items, total

        keys = [item.document_key for item in items]
        counts = dict(
            self.db.execute(
                select(ProjectDocument.document_key, func.count(ProjectDocument.id))
                .where(ProjectDocument.project_id == project_id, ProjectDocument.document_key.in_(keys))
                .group_by(ProjectDocument.document_key)
            ).all()
        )
        for item in items:
            setattr(item, "versions_count", int(counts.get(item.document_key, 1)))
        return items, total

    def create_document_from_url(
        self,
        project_id: uuid.UUID,
        payload: DocumentLinkPayload,
    ) -> ProjectDocument:
        self._get_project(project_id)
        upload_payload = DocumentUploadPayload(
            scope=payload.scope,
            title=payload.title,
            metadata_json=payload.metadata_json,
            wp_id=payload.wp_id,
            task_id=payload.task_id,
            deliverable_id=payload.deliverable_id,
            milestone_id=payload.milestone_id,
            uploaded_by_member_id=payload.uploaded_by_member_id,
            proposal_section_id=payload.proposal_section_id,
        )
        self._validate_scope(project_id, upload_payload)
        self._validate_uploader(project_id, payload.uploaded_by_member_id)
        self._validate_proposal_section(project_id, payload.proposal_section_id)

        doc_id = self._extract_google_doc_id(payload.url)
        content = self._fetch_url(f"https://docs.google.com/document/d/{doc_id}/export?format=docx")

        document_key = uuid.uuid4()
        version = 1
        file_name = f"{doc_id}.docx"
        storage_path = self._storage_path(project_id, document_key, version, file_name)
        file_size_bytes = self._write_file(io.BytesIO(content), storage_path)

        document = ProjectDocument(
            document_key=document_key,
            project_id=project_id,
            scope=payload.scope,
            title=payload.title,
            storage_uri=str(storage_path),
            original_filename=file_name,
            file_size_bytes=file_size_bytes,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            status=DocumentStatus.uploaded.value,
            version=version,
            metadata_json=payload.metadata_json,
            wp_id=payload.wp_id,
            task_id=payload.task_id,
            deliverable_id=payload.deliverable_id,
            milestone_id=payload.milestone_id,
            uploaded_by_member_id=payload.uploaded_by_member_id,
            source_url=payload.url,
            source_type="google_docs",
            proposal_section_id=payload.proposal_section_id,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def refresh_from_url(
        self,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> ProjectDocument:
        self._get_project(project_id)
        document = self.db.scalar(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.id == document_id,
            )
        )
        if not document:
            raise NotFoundError("Document not found in project.")
        latest = self.db.scalar(
            select(ProjectDocument)
            .where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.document_key == document.document_key,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if not latest:
            raise NotFoundError("Document not found in project.")
        if not latest.source_url:
            raise ValidationError("Document has no source URL to refresh from.")

        doc_id = self._extract_google_doc_id(latest.source_url)
        content = self._fetch_url(f"https://docs.google.com/document/d/{doc_id}/export?format=docx")

        version = latest.version + 1
        file_name = f"{doc_id}.docx"
        storage_path = self._storage_path(project_id, latest.document_key, version, file_name)
        file_size_bytes = self._write_file(io.BytesIO(content), storage_path)

        document = ProjectDocument(
            document_key=latest.document_key,
            project_id=project_id,
            scope=latest.scope,
            title=latest.title,
            storage_uri=str(storage_path),
            original_filename=file_name,
            file_size_bytes=file_size_bytes,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            status=DocumentStatus.uploaded.value,
            version=version,
            metadata_json=latest.metadata_json,
            wp_id=latest.wp_id,
            task_id=latest.task_id,
            deliverable_id=latest.deliverable_id,
            milestone_id=latest.milestone_id,
            uploaded_by_member_id=latest.uploaded_by_member_id,
            source_url=latest.source_url,
            source_type=latest.source_type,
            proposal_section_id=latest.proposal_section_id,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    @staticmethod
    def _extract_google_doc_id(url: str) -> str:
        match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", url)
        if not match:
            raise ValidationError("Could not extract Google Doc ID from URL.")
        return match.group(1)

    @staticmethod
    def _fetch_url(url: str) -> bytes:
        try:
            response = httpx.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValidationError(f"Failed to fetch document from URL: {exc}") from exc
        return response.content

    def _apply_document_filters(
        self,
        stmt: Select[tuple[ProjectDocument]],
        scope: DocumentScope | None,
        status: str | None,
        wp_id: uuid.UUID | None,
        task_id: uuid.UUID | None,
        deliverable_id: uuid.UUID | None,
        milestone_id: uuid.UUID | None,
        search: str | None,
    ) -> Select[tuple[ProjectDocument]]:
        if scope:
            stmt = stmt.where(ProjectDocument.scope == scope)
        if status:
            stmt = stmt.where(ProjectDocument.status == status)
        if wp_id:
            stmt = stmt.where(ProjectDocument.wp_id == wp_id)
        if task_id:
            stmt = stmt.where(ProjectDocument.task_id == task_id)
        if deliverable_id:
            stmt = stmt.where(ProjectDocument.deliverable_id == deliverable_id)
        if milestone_id:
            stmt = stmt.where(ProjectDocument.milestone_id == milestone_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(ProjectDocument.title.ilike(like))
        return stmt

    def _validate_scope(self, project_id: uuid.UUID, payload: DocumentUploadPayload) -> None:
        if payload.scope == DocumentScope.project:
            self._validate_no_linked_ids(payload)
            return
        if payload.scope == DocumentScope.wp:
            if not payload.wp_id:
                raise ValidationError("wp_id is required when scope is 'wp'.")
            self._validate_only(payload, "wp_id")
            if not self.db.scalar(
                select(WorkPackage.id).where(WorkPackage.id == payload.wp_id, WorkPackage.project_id == project_id)
            ):
                raise NotFoundError("Work package not found in project.")
            return
        if payload.scope == DocumentScope.task:
            if not payload.task_id:
                raise ValidationError("task_id is required when scope is 'task'.")
            self._validate_only(payload, "task_id")
            if not self.db.scalar(select(Task.id).where(Task.id == payload.task_id, Task.project_id == project_id)):
                raise NotFoundError("Task not found in project.")
            return
        if payload.scope == DocumentScope.deliverable:
            if not payload.deliverable_id:
                raise ValidationError("deliverable_id is required when scope is 'deliverable'.")
            self._validate_only(payload, "deliverable_id")
            if not self.db.scalar(
                select(Deliverable.id).where(
                    Deliverable.id == payload.deliverable_id, Deliverable.project_id == project_id
                )
            ):
                raise NotFoundError("Deliverable not found in project.")
            return
        if payload.scope == DocumentScope.milestone:
            if not payload.milestone_id:
                raise ValidationError("milestone_id is required when scope is 'milestone'.")
            self._validate_only(payload, "milestone_id")
            if not self.db.scalar(
                select(Milestone.id).where(Milestone.id == payload.milestone_id, Milestone.project_id == project_id)
            ):
                raise NotFoundError("Milestone not found in project.")
            return

        raise ValidationError("Unsupported document scope.")

    def _validate_no_linked_ids(self, payload: DocumentUploadPayload) -> None:
        if payload.wp_id or payload.task_id or payload.deliverable_id or payload.milestone_id:
            raise ValidationError("project scope does not accept wp_id, task_id, deliverable_id, or milestone_id.")

    def _validate_only(self, payload: DocumentUploadPayload, allowed_field: str) -> None:
        linked = {
            "wp_id": payload.wp_id,
            "task_id": payload.task_id,
            "deliverable_id": payload.deliverable_id,
            "milestone_id": payload.milestone_id,
        }
        invalid = [name for name, value in linked.items() if value and name != allowed_field]
        if invalid:
            invalid_csv = ", ".join(invalid)
            raise ValidationError(f"{allowed_field} scope cannot include: {invalid_csv}.")

    def _validate_uploader(self, project_id: uuid.UUID, uploaded_by_member_id: uuid.UUID | None) -> None:
        if not uploaded_by_member_id:
            return
        member = self.db.scalar(
            select(TeamMember.id).where(
                TeamMember.id == uploaded_by_member_id,
                TeamMember.project_id == project_id,
                TeamMember.is_active.is_(True),
            )
        )
        if not member:
            raise ValidationError("uploaded_by_member_id must reference an active project member.")

    def _validate_proposal_section(self, project_id: uuid.UUID, proposal_section_id: uuid.UUID | None) -> None:
        if not proposal_section_id:
            return
        section = self.db.scalar(
            select(ProjectProposalSection.id).where(
                ProjectProposalSection.id == proposal_section_id,
                ProjectProposalSection.project_id == project_id,
            )
        )
        if not section:
            raise ValidationError("proposal_section_id must reference a proposal section in this project.")

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _storage_path(self, project_id: uuid.UUID, document_key: uuid.UUID, version: int, file_name: str) -> Path:
        root = Path(settings.documents_storage_path)
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        target_dir = root / str(project_id) / str(document_key) / f"v{version}"
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / file_name

    def _write_file(self, file_stream: BinaryIO, target_path: Path) -> int:
        total = 0
        with target_path.open("wb") as output:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                total += len(chunk)
        return total
