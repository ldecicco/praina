import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.auth import ProjectMembership
from app.models.document import ProjectDocument
from app.models.organization import PartnerOrganization, TeamMember
from app.models.project import Project
from app.models.auth import UserAccount
from app.models.proposal import (
    ProjectProposalSection,
    ProposalCallBrief,
    ProposalCallIngestJob,
    ProposalCallLibraryDocument,
    ProposalCallLibraryEntry,
    ProposalSubmissionItem,
    ProposalSubmissionRequirement,
    ProposalTemplate,
    ProposalTemplateSection,
)
from app.schemas.proposal import (
    ProposalCallLibraryEntryCreate,
    ProposalCallLibraryEntryUpdate,
    ProposalCallBriefUpsert,
    ProposalSubmissionItemUpdate,
    ProposalSubmissionRequirementCreate,
    ProposalSubmissionRequirementUpdate,
    ProjectProposalSectionUpdate,
    ProposalTemplateCreate,
    ProposalTemplateSectionCreate,
    ProposalTemplateSectionUpdate,
    ProposalTemplateUpdate,
)
from app.services.proposal_call_ai_service import ProposalCallAIService
from app.services.proposal_call_document_ingestion_service import ProposalCallDocumentIngestionService
from app.services.text_extraction import extract_text
from app.services.proposal_collab_service import proposal_collab_service
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError

STORAGE_ROOT = Path(getattr(settings, "storage_root", "storage"))


class ProposalService:
    def __init__(self, db: Session):
        self.db = db

    def list_templates(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        active_only: bool = False,
        call_library_entry_id: uuid.UUID | None = None,
    ) -> tuple[list[ProposalTemplate], int]:
        stmt = select(ProposalTemplate)
        if call_library_entry_id:
            stmt = stmt.where(ProposalTemplate.call_library_entry_id == call_library_entry_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(ProposalTemplate.name.ilike(like), ProposalTemplate.funding_program.ilike(like)))
        if active_only:
            stmt = stmt.where(ProposalTemplate.is_active.is_(True))
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = self.db.scalars(
            stmt.order_by(ProposalTemplate.funding_program.asc(), ProposalTemplate.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        for item in items:
            setattr(item, "sections", self._list_template_sections(item.id))
        return list(items), total

    def get_template(self, template_id: uuid.UUID) -> ProposalTemplate:
        template = self.db.get(ProposalTemplate, template_id)
        if not template:
            raise NotFoundError("Proposal template not found.")
        setattr(template, "sections", self._list_template_sections(template_id))
        return template

    def create_template(self, payload: ProposalTemplateCreate) -> ProposalTemplate:
        if payload.call_library_entry_id:
            self._get_call_library_entry(payload.call_library_entry_id)
        template = ProposalTemplate(
            call_library_entry_id=payload.call_library_entry_id,
            name=payload.name.strip(),
            funding_program=payload.funding_program.strip(),
            description=(payload.description or "").strip() or None,
            is_active=payload.is_active,
        )
        self.db.add(template)
        self._flush_or_conflict("Template name must be unique.")
        for section in payload.sections:
            self._create_template_section(template.id, section)
        self.db.commit()
        return self.get_template(template.id)

    def update_template(self, template_id: uuid.UUID, payload: ProposalTemplateUpdate) -> ProposalTemplate:
        template = self._get_template(template_id)
        data = payload.model_dump(exclude_unset=True)
        if "call_library_entry_id" in data:
            if payload.call_library_entry_id:
                self._get_call_library_entry(payload.call_library_entry_id)
            template.call_library_entry_id = payload.call_library_entry_id
        if "name" in data and payload.name:
            template.name = payload.name.strip()
        if "funding_program" in data and payload.funding_program:
            template.funding_program = payload.funding_program.strip()
        if "description" in data:
            template.description = (payload.description or "").strip() or None
        if "is_active" in data and payload.is_active is not None:
            template.is_active = payload.is_active
        self._flush_or_conflict("Template name must be unique.")
        self.db.commit()
        return self.get_template(template.id)

    def delete_template(self, template_id: uuid.UUID) -> None:
        template = self._get_template(template_id)
        project_ids = self.db.scalars(select(Project.id).where(Project.proposal_template_id == template.id)).all()
        for project_id in project_ids:
            project = self.db.get(Project, project_id)
            if project:
                project.proposal_template_id = None
                self._sync_project_sections(project)
        self.db.delete(template)
        self.db.commit()

    def create_template_section(self, template_id: uuid.UUID, payload: ProposalTemplateSectionCreate) -> ProposalTemplate:
        self._get_template(template_id)
        self._create_template_section(template_id, payload)
        self.db.commit()
        self._sync_projects_for_template(template_id)
        self.db.commit()
        return self.get_template(template_id)

    def update_template_section(
        self,
        template_id: uuid.UUID,
        section_id: uuid.UUID,
        payload: ProposalTemplateSectionUpdate,
    ) -> ProposalTemplate:
        section = self.db.scalar(
            select(ProposalTemplateSection).where(
                ProposalTemplateSection.id == section_id,
                ProposalTemplateSection.template_id == template_id,
            )
        )
        if not section:
            raise NotFoundError("Template section not found.")
        data = payload.model_dump(exclude_unset=True)
        if "key" in data and payload.key:
            section.key = payload.key.strip()
        if "title" in data and payload.title:
            section.title = payload.title.strip()
        if "guidance" in data:
            section.guidance = (payload.guidance or "").strip() or None
        if "position" in data and payload.position is not None:
            section.position = payload.position
        if "required" in data and payload.required is not None:
            section.required = payload.required
        if "scope_hint" in data and payload.scope_hint:
            section.scope_hint = payload.scope_hint.strip()
        self._flush_or_conflict("Template section key must be unique within the template.")
        self.db.commit()
        self._sync_projects_for_template(template_id)
        self.db.commit()
        return self.get_template(template_id)

    def delete_template_section(self, template_id: uuid.UUID, section_id: uuid.UUID) -> ProposalTemplate:
        section = self.db.scalar(
            select(ProposalTemplateSection).where(
                ProposalTemplateSection.id == section_id,
                ProposalTemplateSection.template_id == template_id,
            )
        )
        if not section:
            raise NotFoundError("Template section not found.")
        self.db.delete(section)
        self.db.commit()
        self._sync_projects_for_template(template_id)
        self.db.commit()
        return self.get_template(template_id)

    def apply_template_to_project(self, project_id: uuid.UUID, template_id: uuid.UUID | None) -> list[ProjectProposalSection]:
        project = self._get_project(project_id)
        if template_id:
            template = self._get_template(template_id)
            if not template.is_active:
                raise ValidationError("Inactive proposal templates cannot be assigned to projects.")
            project.proposal_template_id = template.id
        else:
            project.proposal_template_id = None
        self.db.flush()
        self._sync_project_sections(project)
        self.db.commit()
        return self.list_project_sections(project_id)

    def list_project_sections(self, project_id: uuid.UUID) -> list[ProjectProposalSection]:
        self._get_project(project_id)
        rows = self.db.scalars(
            select(ProjectProposalSection)
            .where(ProjectProposalSection.project_id == project_id)
            .order_by(ProjectProposalSection.position.asc(), ProjectProposalSection.title.asc())
        ).all()
        if not rows:
            return []
        counts = dict(
            self.db.execute(
                select(ProjectDocument.proposal_section_id, func.count(ProjectDocument.id))
                .where(
                    ProjectDocument.project_id == project_id,
                    ProjectDocument.proposal_section_id.in_([row.id for row in rows]),
                )
                .group_by(ProjectDocument.proposal_section_id)
            ).all()
        )
        for row in rows:
            setattr(row, "linked_documents_count", int(counts.get(row.id, 0)))
        return list(rows)

    def list_call_library_entries(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        active_only: bool = True,
    ) -> tuple[list[ProposalCallLibraryEntry], int]:
        stmt = select(ProposalCallLibraryEntry)
        if active_only:
            stmt = stmt.where(ProposalCallLibraryEntry.is_active.is_(True))
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    ProposalCallLibraryEntry.call_title.ilike(like),
                    ProposalCallLibraryEntry.funder_name.ilike(like),
                    ProposalCallLibraryEntry.programme_name.ilike(like),
                    ProposalCallLibraryEntry.reference_code.ilike(like),
                )
            )
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = self.db.scalars(
            stmt.order_by(
                ProposalCallLibraryEntry.submission_deadline.asc().nulls_last(),
                ProposalCallLibraryEntry.updated_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_call_library_entry(self, payload: ProposalCallLibraryEntryCreate) -> ProposalCallLibraryEntry:
        item = ProposalCallLibraryEntry(
            call_title=payload.call_title.strip(),
            funder_name=(payload.funder_name or "").strip() or None,
            programme_name=(payload.programme_name or "").strip() or None,
            reference_code=(payload.reference_code or "").strip() or None,
            submission_deadline=payload.submission_deadline,
            source_url=(payload.source_url or "").strip() or None,
            summary=(payload.summary or "").strip() or None,
            eligibility_notes=(payload.eligibility_notes or "").strip() or None,
            budget_notes=(payload.budget_notes or "").strip() or None,
            scoring_notes=(payload.scoring_notes or "").strip() or None,
            requirements_text=(payload.requirements_text or "").strip() or None,
            is_active=payload.is_active,
            version=1,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def ingest_call_library_pdf(
        self,
        *,
        file_name: str,
        content_type: str,
        file_bytes: bytes,
        library_entry_id: uuid.UUID | None = None,
        source_url: str | None = None,
        category: str | None = None,
    ) -> tuple[ProposalCallLibraryEntry, ProposalCallLibraryDocument]:
        if content_type != "application/pdf" and not file_name.lower().endswith(".pdf"):
            raise ValidationError("Only PDF files are supported.")
        if not file_bytes:
            raise ValidationError("Uploaded file is empty.")

        entry = self.db.get(ProposalCallLibraryEntry, library_entry_id) if library_entry_id else None
        if library_entry_id and not entry:
            raise NotFoundError("Call library entry not found.")
        if not entry:
            entry = ProposalCallLibraryEntry(
                call_title=Path(file_name).stem[:255] or "Imported call",
                source_url=(source_url or "").strip() or None,
                version=1,
                is_active=True,
            )
            self.db.add(entry)
            self.db.flush()

        document_id = uuid.uuid4()
        safe_filename = (file_name or "call.pdf").replace("/", "_").replace("\\", "_")
        relative_path = f"call-library/{entry.id}/{document_id}/{safe_filename}"
        full_path = STORAGE_ROOT / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(file_bytes)

        extracted = extract_text(full_path, content_type)
        if not extracted.strip():
            raise ValidationError("Could not extract text from PDF.")

        ai_fields = ProposalCallAIService().extract_call_fields(extracted, source_url=source_url)
        self._apply_call_fields(
            entry,
            {
                "call_title": ai_fields.get("call_title") or entry.call_title or Path(file_name).stem,
                "funder_name": ai_fields.get("funder_name"),
                "programme_name": ai_fields.get("programme_name"),
                "reference_code": ai_fields.get("reference_code"),
                "submission_deadline": ai_fields.get("submission_deadline"),
                "source_url": ai_fields.get("source_url") or source_url,
                "summary": ai_fields.get("summary"),
                "eligibility_notes": ai_fields.get("eligibility_notes"),
                "budget_notes": ai_fields.get("budget_notes"),
                "scoring_notes": ai_fields.get("scoring_notes"),
                "requirements_text": ai_fields.get("requirements_text"),
            },
            increment_version=library_entry_id is not None,
        )

        document = ProposalCallLibraryDocument(
            id=document_id,
            library_entry_id=entry.id,
            original_filename=safe_filename,
            category=(category or "other").strip() or "other",
            status="active",
            indexing_status="uploaded",
            mime_type=content_type,
            file_size_bytes=len(file_bytes),
            storage_path=relative_path,
            extracted_text=extracted,
            indexed_at=None,
            ingestion_error=None,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(entry)
        self.db.refresh(document)
        ProposalCallDocumentIngestionService(self.db).reindex_document(entry.id, document.id)
        self.db.refresh(document)
        return entry, document

    def start_call_library_ingest_job(
        self,
        *,
        file_name: str,
        content_type: str,
        file_bytes: bytes,
        created_by_user_id: uuid.UUID | None = None,
        library_entry_id: uuid.UUID | None = None,
        source_url: str | None = None,
        category: str | None = None,
    ) -> ProposalCallIngestJob:
        if content_type != "application/pdf" and not file_name.lower().endswith(".pdf"):
            raise ValidationError("Only PDF files are supported.")
        if not file_bytes:
            raise ValidationError("Uploaded file is empty.")

        entry = self.db.get(ProposalCallLibraryEntry, library_entry_id) if library_entry_id else None
        if library_entry_id and not entry:
            raise NotFoundError("Call library entry not found.")
        if not entry:
            entry = ProposalCallLibraryEntry(
                call_title=Path(file_name).stem[:255] or "Imported call",
                source_url=(source_url or "").strip() or None,
                version=1,
                is_active=True,
            )
            self.db.add(entry)
            self.db.flush()

        document_id = uuid.uuid4()
        safe_filename = (file_name or "call.pdf").replace("/", "_").replace("\\", "_")
        relative_path = f"call-library/{entry.id}/{document_id}/{safe_filename}"
        full_path = STORAGE_ROOT / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(file_bytes)

        document = ProposalCallLibraryDocument(
            id=document_id,
            library_entry_id=entry.id,
            original_filename=safe_filename,
            category=(category or "other").strip() or "other",
            status="active",
            indexing_status="uploaded",
            mime_type=content_type,
            file_size_bytes=len(file_bytes),
            storage_path=relative_path,
            extracted_text=None,
            indexed_at=None,
            ingestion_error=None,
        )
        self.db.add(document)
        self.db.flush()

        job = ProposalCallIngestJob(
            library_entry_id=entry.id,
            document_id=document.id,
            created_by_user_id=created_by_user_id,
            status="queued",
            stage="queued",
            progress_current=0,
            progress_total=None,
            stream_text=None,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_call_library_ingest_job(self, job_id: uuid.UUID) -> ProposalCallIngestJob:
        job = self.db.get(ProposalCallIngestJob, job_id)
        if not job:
            raise NotFoundError("Call ingest job not found.")
        return job

    def update_call_library_entry(
        self,
        library_entry_id: uuid.UUID,
        payload: ProposalCallLibraryEntryUpdate,
    ) -> ProposalCallLibraryEntry:
        item = self.db.get(ProposalCallLibraryEntry, library_entry_id)
        if not item:
            raise NotFoundError("Call library entry not found.")
        data = payload.model_dump(exclude_unset=True)
        content_changed = self._apply_call_fields(
            item,
            {field: getattr(payload, field) for field in data.keys()},
            increment_version=False,
        )
        if "is_active" in data and payload.is_active is not None:
            item.is_active = payload.is_active
        if content_changed:
            item.version = int(item.version or 1) + 1
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_call_library_entry(self, library_entry_id: uuid.UUID) -> None:
        item = self.db.get(ProposalCallLibraryEntry, library_entry_id)
        if not item:
            raise NotFoundError("Call library entry not found.")
        project_use_count = int(
            self.db.scalar(
                select(func.count()).select_from(ProposalCallBrief).where(ProposalCallBrief.source_call_id == library_entry_id)
            ) or 0
        )
        if project_use_count > 0:
            raise ValidationError("Call cannot be deleted because it is used by one or more projects.")
        template_use_count = int(
            self.db.scalar(
                select(func.count()).select_from(ProposalTemplate).where(ProposalTemplate.call_library_entry_id == library_entry_id)
            ) or 0
        )
        if template_use_count > 0:
            raise ValidationError("Call cannot be deleted because templates are still linked to it.")
        self.db.delete(item)
        self.db.commit()

    def list_call_library_documents(
        self,
        library_entry_id: uuid.UUID,
        *,
        include_superseded: bool = True,
    ) -> list[ProposalCallLibraryDocument]:
        entry = self.db.get(ProposalCallLibraryEntry, library_entry_id)
        if not entry:
            raise NotFoundError("Call library entry not found.")
        stmt = (
            select(ProposalCallLibraryDocument)
            .where(ProposalCallLibraryDocument.library_entry_id == library_entry_id)
            .order_by(ProposalCallLibraryDocument.created_at.desc())
        )
        if not include_superseded:
            stmt = stmt.where(ProposalCallLibraryDocument.status != "superseded")
        return list(self.db.scalars(stmt).all())

    def update_call_library_document(
        self,
        library_entry_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        category: str | None = None,
        status: str | None = None,
    ) -> ProposalCallLibraryDocument:
        document = self.db.get(ProposalCallLibraryDocument, document_id)
        if not document or document.library_entry_id != library_entry_id:
            raise NotFoundError("Call document not found.")
        if category is not None:
            document.category = category.strip() or "other"
        if status is not None:
            normalized_status = status.strip().lower()
            if normalized_status not in {"active", "superseded"}:
                raise ValidationError("Call document status must be active or superseded.")
            document.status = normalized_status
        self.db.commit()
        self.db.refresh(document)
        return document

    def delete_call_library_document(
        self,
        library_entry_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        document = self.db.get(ProposalCallLibraryDocument, document_id)
        if not document or document.library_entry_id != library_entry_id:
            raise NotFoundError("Call document not found.")
        full_path = STORAGE_ROOT / document.storage_path
        self.db.delete(document)
        self.db.commit()
        if full_path.exists():
            full_path.unlink()

    def get_call_brief(self, project_id: uuid.UUID) -> ProposalCallBrief | None:
        self._get_project(project_id)
        return self.db.scalar(select(ProposalCallBrief).where(ProposalCallBrief.project_id == project_id))

    def upsert_call_brief(self, project_id: uuid.UUID, payload: ProposalCallBriefUpsert) -> ProposalCallBrief:
        self._get_project(project_id)
        item = self.db.scalar(select(ProposalCallBrief).where(ProposalCallBrief.project_id == project_id))
        if not item:
            item = ProposalCallBrief(project_id=project_id)
            self.db.add(item)
        data = payload.model_dump(exclude_unset=True)
        for field in (
            "call_title",
            "funder_name",
            "programme_name",
            "reference_code",
            "submission_deadline",
            "source_url",
            "summary",
            "eligibility_notes",
            "budget_notes",
            "scoring_notes",
            "requirements_text",
        ):
            if field not in data:
                continue
            value = getattr(payload, field)
            if isinstance(value, str):
                setattr(item, field, value.strip() or None)
            else:
                setattr(item, field, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def import_call_brief_from_library(
        self,
        project_id: uuid.UUID,
        library_entry_id: uuid.UUID,
        copied_by_user_id: uuid.UUID | None,
    ) -> ProposalCallBrief:
        self._get_project(project_id)
        if copied_by_user_id:
            user = self.db.get(UserAccount, copied_by_user_id)
            if not user:
                raise ValidationError("Copying user is invalid.")
        library_entry = self.db.get(ProposalCallLibraryEntry, library_entry_id)
        if not library_entry:
            raise NotFoundError("Call library entry not found.")
        item = self.db.scalar(select(ProposalCallBrief).where(ProposalCallBrief.project_id == project_id))
        if not item:
            item = ProposalCallBrief(project_id=project_id)
            self.db.add(item)
        item.source_call_id = library_entry.id
        item.source_version = library_entry.version
        item.copied_by_user_id = copied_by_user_id
        item.copied_at = datetime.now(timezone.utc)
        item.call_title = library_entry.call_title
        item.funder_name = library_entry.funder_name
        item.programme_name = library_entry.programme_name
        item.reference_code = library_entry.reference_code
        item.submission_deadline = library_entry.submission_deadline
        item.source_url = library_entry.source_url
        item.summary = library_entry.summary
        item.eligibility_notes = library_entry.eligibility_notes
        item.budget_notes = library_entry.budget_notes
        item.scoring_notes = library_entry.scoring_notes
        item.requirements_text = library_entry.requirements_text
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_submission_requirements(self, project_id: uuid.UUID) -> list[ProposalSubmissionRequirement]:
        self._get_project(project_id)
        self._sync_submission_items_for_project(project_id)
        requirements = list(
            self.db.scalars(
                select(ProposalSubmissionRequirement)
                .where(ProposalSubmissionRequirement.project_id == project_id)
                .order_by(ProposalSubmissionRequirement.position.asc(), ProposalSubmissionRequirement.created_at.asc())
            ).all()
        )
        if not requirements:
            return []
        requirement_ids = [item.id for item in requirements]
        items = list(
            self.db.scalars(
                select(ProposalSubmissionItem)
                .where(ProposalSubmissionItem.requirement_id.in_(requirement_ids))
                .order_by(
                    ProposalSubmissionItem.created_at.asc(),
                    ProposalSubmissionItem.partner_id.asc().nulls_first(),
                )
            ).all()
        )
        partner_names = {
            str(item.id): item.short_name
            for item in self.db.scalars(
                select(PartnerOrganization).where(PartnerOrganization.project_id == project_id)
            ).all()
        }
        member_names = {
            str(item.id): item.full_name
            for item in self.db.scalars(
                select(TeamMember).where(TeamMember.project_id == project_id)
            ).all()
        }
        items_by_requirement: dict[uuid.UUID, list[ProposalSubmissionItem]] = {item.id: [] for item in requirements}
        for item in items:
            setattr(item, "partner_name", partner_names.get(str(item.partner_id)) if item.partner_id else None)
            setattr(item, "assignee_name", member_names.get(str(item.assignee_member_id)) if item.assignee_member_id else None)
            if item.latest_uploaded_document_id:
                document = self.db.get(ProjectDocument, item.latest_uploaded_document_id)
                setattr(item, "latest_uploaded_document_title", document.title if document and document.project_id == project_id else None)
            else:
                setattr(item, "latest_uploaded_document_title", None)
            items_by_requirement.setdefault(item.requirement_id, []).append(item)
        for requirement in requirements:
            setattr(requirement, "items", items_by_requirement.get(requirement.id, []))
        return requirements

    def list_submission_requirements_for_actor(
        self,
        project_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        actor_platform_role: str,
    ) -> list[ProposalSubmissionRequirement]:
        access = self._submission_access(project_id, actor_user_id, actor_platform_role)
        requirements = self.list_submission_requirements(project_id)
        if access["is_coordinator"]:
            return requirements
        visible_partner_ids: set[uuid.UUID] = access["partner_ids"]
        scoped: list[ProposalSubmissionRequirement] = []
        for requirement in requirements:
            if requirement.document_type != "per_partner":
                continue
            visible_items = [
                item for item in getattr(requirement, "items", [])
                if item.partner_id and item.partner_id in visible_partner_ids
            ]
            if not visible_items:
                continue
            setattr(requirement, "items", visible_items)
            scoped.append(requirement)
        return scoped

    def create_submission_requirement(
        self,
        project_id: uuid.UUID,
        payload: ProposalSubmissionRequirementCreate,
    ) -> ProposalSubmissionRequirement:
        project = self._get_project(project_id)
        document_type = self._validate_submission_document_type(payload.document_type)
        format_hint = self._validate_submission_format_hint(payload.format_hint)
        template_id = self._validate_submission_template(project, payload.template_id, document_type=document_type, format_hint=format_hint)
        requirement = ProposalSubmissionRequirement(
            project_id=project.id,
            template_id=template_id,
            title=payload.title.strip(),
            description=(payload.description or "").strip() or None,
            document_type=document_type,
            format_hint=format_hint,
            required=payload.required,
            position=payload.position,
        )
        self.db.add(requirement)
        self.db.flush()
        self._create_submission_items_for_requirement(requirement)
        self.db.commit()
        return self._get_submission_requirement(project_id, requirement.id)

    def create_submission_requirement_for_actor(
        self,
        project_id: uuid.UUID,
        payload: ProposalSubmissionRequirementCreate,
        *,
        actor_user_id: uuid.UUID,
        actor_platform_role: str,
    ) -> ProposalSubmissionRequirement:
        access = self._submission_access(project_id, actor_user_id, actor_platform_role)
        if not access["is_coordinator"]:
            raise ValidationError("Only coordinators can manage submission requirements.")
        return self.create_submission_requirement(project_id, payload)

    def update_submission_requirement(
        self,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        payload: ProposalSubmissionRequirementUpdate,
    ) -> ProposalSubmissionRequirement:
        requirement = self._get_submission_requirement(project_id, requirement_id)
        data = payload.model_dump(exclude_unset=True)
        if "title" in data and payload.title:
            requirement.title = payload.title.strip()
        if "description" in data:
            requirement.description = (payload.description or "").strip() or None
        if "required" in data and payload.required is not None:
            requirement.required = payload.required
        if "position" in data and payload.position is not None:
            requirement.position = payload.position
        if "document_type" in data:
            next_document_type = self._validate_submission_document_type(payload.document_type or requirement.document_type)
            if next_document_type != requirement.document_type:
                raise ValidationError("Submission document type cannot be changed after creation.")
        if "format_hint" in data:
            next_format_hint = self._validate_submission_format_hint(payload.format_hint or requirement.format_hint)
            if next_format_hint != requirement.format_hint:
                raise ValidationError("Submission format cannot be changed after creation.")
        if "template_id" in data:
            requirement.template_id = self._validate_submission_template(
                self._get_project(project_id),
                payload.template_id,
                document_type=requirement.document_type,
                format_hint=requirement.format_hint,
            )
        self.db.commit()
        return self._get_submission_requirement(project_id, requirement.id)

    def update_submission_requirement_for_actor(
        self,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
        payload: ProposalSubmissionRequirementUpdate,
        *,
        actor_user_id: uuid.UUID,
        actor_platform_role: str,
    ) -> ProposalSubmissionRequirement:
        access = self._submission_access(project_id, actor_user_id, actor_platform_role)
        if not access["is_coordinator"]:
            raise ValidationError("Only coordinators can manage submission requirements.")
        return self.update_submission_requirement(project_id, requirement_id, payload)

    def update_submission_item(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: ProposalSubmissionItemUpdate,
    ) -> ProposalSubmissionItem:
        item = self.db.get(ProposalSubmissionItem, item_id)
        if not item or item.project_id != project_id:
            raise NotFoundError("Submission item not found.")
        data = payload.model_dump(exclude_unset=True)
        if "assignee_member_id" in data:
            self._validate_member(project_id, payload.assignee_member_id)
            item.assignee_member_id = payload.assignee_member_id
        if "status" in data and payload.status:
            item.status = self._validate_submission_status(payload.status)
            item.submitted_at = datetime.now(timezone.utc) if item.status == "submitted" else None
        if "notes" in data:
            item.notes = (payload.notes or "").strip() or None
        if "latest_uploaded_document_id" in data:
            if payload.latest_uploaded_document_id:
                document = self.db.get(ProjectDocument, payload.latest_uploaded_document_id)
                if not document or document.project_id != project_id:
                    raise ValidationError("Selected uploaded document is invalid.")
            item.latest_uploaded_document_id = payload.latest_uploaded_document_id
        self.db.commit()
        self.db.refresh(item)
        setattr(item, "partner_name", self._partner_name(project_id, item.partner_id))
        setattr(item, "assignee_name", self._member_name(project_id, item.assignee_member_id))
        if item.latest_uploaded_document_id:
            document = self.db.get(ProjectDocument, item.latest_uploaded_document_id)
            setattr(item, "latest_uploaded_document_title", document.title if document and document.project_id == project_id else None)
        else:
            setattr(item, "latest_uploaded_document_title", None)
        return item

    def update_submission_item_for_actor(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: ProposalSubmissionItemUpdate,
        *,
        actor_user_id: uuid.UUID,
        actor_platform_role: str,
    ) -> ProposalSubmissionItem:
        access = self._submission_access(project_id, actor_user_id, actor_platform_role)
        item = self.db.get(ProposalSubmissionItem, item_id)
        if not item or item.project_id != project_id:
            raise NotFoundError("Submission item not found.")
        if not access["is_coordinator"]:
            if not item.partner_id or item.partner_id not in access["partner_ids"]:
                raise ValidationError("You can only update submission items for your partner.")
        return self.update_submission_item(project_id, item_id, payload)

    def process_call_library_ingest_job(self, job_id: uuid.UUID) -> ProposalCallIngestJob:
        job = self.get_call_library_ingest_job(job_id)
        if job.status == "completed":
            return job

        document = self.db.get(ProposalCallLibraryDocument, job.document_id)
        entry = self.db.get(ProposalCallLibraryEntry, job.library_entry_id)
        if not document or not entry:
            raise NotFoundError("Call ingest job targets are missing.")

        full_path = STORAGE_ROOT / document.storage_path
        try:
            job.status = "processing"
            job.stage = "extracting_text"
            job.started_at = job.started_at or datetime.now(timezone.utc)
            job.error = None
            job.stream_text = None
            self.db.commit()

            extracted = extract_text(full_path, document.mime_type)
            if not extracted.strip():
                raise ValidationError("Could not extract text from PDF.")

            document.extracted_text = extracted
            ai_service = ProposalCallAIService()
            chunks = ai_service.build_chunks(extracted)
            if not chunks:
                raise ValidationError("Could not prepare call text for extraction.")

            job.progress_total = len(chunks)
            job.progress_current = 0
            job.stage = "processing_chunks"
            self.db.commit()

            def on_progress(current: int, total: int) -> None:
                job.progress_current = current
                job.progress_total = total
                job.stage = "processing_chunks"
                self.db.commit()

            def on_stream(text: str) -> None:
                job.stream_text = text[-12000:]
                self.db.commit()

            ai_fields = ai_service.extract_call_fields(
                extracted,
                source_url=entry.source_url,
                progress_callback=on_progress,
                stream_callback=on_stream,
            )

            job.stage = "reducing"
            self.db.commit()

            self._apply_call_fields(
                entry,
                {
                    "call_title": ai_fields.get("call_title") or entry.call_title or Path(document.original_filename).stem,
                    "funder_name": ai_fields.get("funder_name"),
                    "programme_name": ai_fields.get("programme_name"),
                    "reference_code": ai_fields.get("reference_code"),
                    "submission_deadline": ai_fields.get("submission_deadline"),
                    "source_url": ai_fields.get("source_url") or entry.source_url,
                    "summary": ai_fields.get("summary"),
                    "eligibility_notes": ai_fields.get("eligibility_notes"),
                    "budget_notes": ai_fields.get("budget_notes"),
                    "scoring_notes": ai_fields.get("scoring_notes"),
                    "requirements_text": ai_fields.get("requirements_text"),
                },
                increment_version=False,
            )
            job.progress_current = job.progress_total or job.progress_current
            job.status = "completed"
            job.stage = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.stream_text = (job.stream_text or "")[-12000:] or None
            self.db.commit()
            ProposalCallDocumentIngestionService(self.db).reindex_document(entry.id, document.id)
            self.db.refresh(job)
            self.db.refresh(document)
            return job
        except Exception as exc:
            self.db.rollback()
            failed_job = self.db.get(ProposalCallIngestJob, job_id)
            if failed_job:
                failed_job.status = "failed"
                failed_job.stage = "failed"
                failed_job.error = str(exc)
                failed_job.completed_at = datetime.now(timezone.utc)
                self.db.commit()
                self.db.refresh(failed_job)
                return failed_job
            raise

    def _apply_call_fields(
        self,
        item: ProposalCallLibraryEntry,
        values: dict[str, object],
        *,
        increment_version: bool,
    ) -> bool:
        content_changed = False
        for field in (
            "call_title",
            "funder_name",
            "programme_name",
            "reference_code",
            "submission_deadline",
            "source_url",
            "summary",
            "eligibility_notes",
            "budget_notes",
            "scoring_notes",
            "requirements_text",
        ):
            if field not in values:
                continue
            value = values[field]
            next_value = value.strip() or None if isinstance(value, str) else value
            if field == "submission_deadline" and isinstance(next_value, str):
                try:
                    from datetime import date
                    next_value = date.fromisoformat(next_value)
                except ValueError:
                    next_value = None
            if getattr(item, field) != next_value:
                setattr(item, field, next_value)
                content_changed = True
        if increment_version and content_changed:
            item.version = int(item.version or 1) + 1
        return content_changed

    def update_project_section(
        self,
        project_id: uuid.UUID,
        section_id: uuid.UUID,
        payload: ProjectProposalSectionUpdate,
    ) -> ProjectProposalSection:
        section = self.db.scalar(
            select(ProjectProposalSection).where(
                ProjectProposalSection.id == section_id,
                ProjectProposalSection.project_id == project_id,
            )
        )
        if not section:
            raise NotFoundError("Proposal section not found in project.")
        data = payload.model_dump(exclude_unset=True)
        if "title" in data and payload.title:
            section.title = payload.title.strip()
        if "guidance" in data:
            section.guidance = (payload.guidance or "").strip() or None
        if "position" in data and payload.position is not None:
            section.position = payload.position
        if "required" in data and payload.required is not None:
            section.required = payload.required
        if "scope_hint" in data and payload.scope_hint:
            section.scope_hint = payload.scope_hint.strip()
        if "status" in data and payload.status:
            section.status = payload.status.strip()
        if "owner_member_id" in data:
            self._validate_member(project_id, payload.owner_member_id)
            section.owner_member_id = payload.owner_member_id
        if "reviewer_member_id" in data:
            self._validate_member(project_id, payload.reviewer_member_id)
            section.reviewer_member_id = payload.reviewer_member_id
        if "due_date" in data:
            section.due_date = payload.due_date
        if "notes" in data:
            section.notes = (payload.notes or "").strip() or None
        if "content" in data:
            section.content = (payload.content or "").strip() or None
            if not payload.preserve_yjs_state:
                section.yjs_state = None
                proposal_collab_service.invalidate(section.id)
        self.db.commit()
        self.db.refresh(section)
        setattr(section, "linked_documents_count", self._linked_documents_count(project_id, section.id))
        return section

    def _create_template_section(self, template_id: uuid.UUID, payload: ProposalTemplateSectionCreate) -> None:
        section = ProposalTemplateSection(
            template_id=template_id,
            key=payload.key.strip(),
            title=payload.title.strip(),
            guidance=(payload.guidance or "").strip() or None,
            position=payload.position,
            required=payload.required,
            scope_hint=payload.scope_hint.strip(),
        )
        self.db.add(section)
        self._flush_or_conflict("Template section key must be unique within the template.")

    def _sync_projects_for_template(self, template_id: uuid.UUID) -> None:
        project_ids = self.db.scalars(select(Project.id).where(Project.proposal_template_id == template_id)).all()
        for project_id in project_ids:
            project = self.db.get(Project, project_id)
            if project:
                self._sync_project_sections(project)

    def _sync_project_sections(self, project: Project) -> None:
        existing = self.db.scalars(
            select(ProjectProposalSection).where(ProjectProposalSection.project_id == project.id)
        ).all()
        if not project.proposal_template_id:
            for item in existing:
                self.db.delete(item)
            self.db.flush()
            return
        template_sections = self._list_template_sections(project.proposal_template_id)
        existing_by_template_id = {
            item.template_section_id: item for item in existing if item.template_section_id is not None
        }
        kept_ids: set[uuid.UUID] = set()
        for template_section in template_sections:
            kept_ids.add(template_section.id)
            row = existing_by_template_id.get(template_section.id)
            if not row:
                row = ProjectProposalSection(
                    project_id=project.id,
                    template_section_id=template_section.id,
                    key=template_section.key,
                    title=template_section.title,
                    guidance=template_section.guidance,
                    position=template_section.position,
                    required=template_section.required,
                    scope_hint=template_section.scope_hint,
                    status="not_started",
                )
                self.db.add(row)
                continue
            row.key = template_section.key
            row.title = template_section.title
            row.guidance = template_section.guidance
            row.position = template_section.position
            row.required = template_section.required
            row.scope_hint = template_section.scope_hint
        for item in existing:
            if item.template_section_id and item.template_section_id not in kept_ids:
                self.db.delete(item)
        self.db.flush()

    def _linked_documents_count(self, project_id: uuid.UUID, section_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count(ProjectDocument.id)).where(
                    ProjectDocument.project_id == project_id,
                    ProjectDocument.proposal_section_id == section_id,
                )
            )
            or 0
        )

    def _list_template_sections(self, template_id: uuid.UUID) -> list[ProposalTemplateSection]:
        return list(
            self.db.scalars(
                select(ProposalTemplateSection)
                .where(ProposalTemplateSection.template_id == template_id)
                .order_by(ProposalTemplateSection.position.asc(), ProposalTemplateSection.title.asc())
            ).all()
        )

    def _validate_member(self, project_id: uuid.UUID, member_id: uuid.UUID | None) -> None:
        if not member_id:
            return
        member = self.db.get(TeamMember, member_id)
        if not member or member.project_id != project_id:
            raise ValidationError("Selected proposal section member is invalid.")

    def _partner_name(self, project_id: uuid.UUID, partner_id: uuid.UUID | None) -> str | None:
        if not partner_id:
            return None
        partner = self.db.get(PartnerOrganization, partner_id)
        if not partner or partner.project_id != project_id:
            return None
        return partner.short_name

    def _member_name(self, project_id: uuid.UUID, member_id: uuid.UUID | None) -> str | None:
        if not member_id:
            return None
        member = self.db.get(TeamMember, member_id)
        if not member or member.project_id != project_id:
            return None
        return member.full_name

    def _validate_submission_document_type(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"project", "per_partner"}:
            raise ValidationError("Submission document type must be project or per_partner.")
        return normalized

    def _validate_submission_format_hint(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"online", "upload"}:
            raise ValidationError("Submission format must be online or upload.")
        return normalized

    def _validate_submission_status(self, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"not_started", "in_preparation", "completed", "submitted"}:
            raise ValidationError("Submission status must be not_started, in_preparation, completed, or submitted.")
        return normalized

    def _validate_submission_template(
        self,
        project: Project,
        template_id: uuid.UUID | None,
        *,
        document_type: str,
        format_hint: str,
    ) -> uuid.UUID | None:
        if not template_id:
            return None
        if document_type != "project" or format_hint != "online":
            raise ValidationError("Templates can only be assigned to project online submission documents.")
        template = self._get_template(template_id)
        call_brief = self.get_call_brief(project.id)
        if call_brief and call_brief.source_call_id and template.call_library_entry_id and template.call_library_entry_id != call_brief.source_call_id:
            raise ValidationError("Selected submission template must belong to the project's call.")
        return template.id

    def _create_submission_items_for_requirement(self, requirement: ProposalSubmissionRequirement) -> None:
        if requirement.document_type == "project":
            self.db.add(
                ProposalSubmissionItem(
                    project_id=requirement.project_id,
                    requirement_id=requirement.id,
                    partner_id=None,
                    status="not_started",
                )
            )
            self.db.flush()
            return
        partners = list(
            self.db.scalars(
                select(PartnerOrganization)
                .where(PartnerOrganization.project_id == requirement.project_id)
                .order_by(PartnerOrganization.short_name.asc())
            ).all()
        )
        for partner in partners:
            self.db.add(
                ProposalSubmissionItem(
                    project_id=requirement.project_id,
                    requirement_id=requirement.id,
                    partner_id=partner.id,
                    status="not_started",
                )
            )
        self.db.flush()

    def _sync_submission_items_for_project(self, project_id: uuid.UUID) -> None:
        requirements = list(
            self.db.scalars(
                select(ProposalSubmissionRequirement).where(ProposalSubmissionRequirement.project_id == project_id)
            ).all()
        )
        if not requirements:
            return
        partners = list(
            self.db.scalars(
                select(PartnerOrganization).where(PartnerOrganization.project_id == project_id)
            ).all()
        )
        partner_ids = {partner.id for partner in partners}
        changed = False
        for requirement in requirements:
            items = list(
                self.db.scalars(
                    select(ProposalSubmissionItem).where(ProposalSubmissionItem.requirement_id == requirement.id)
                ).all()
            )
            if requirement.document_type == "project":
                if not any(item.partner_id is None for item in items):
                    self.db.add(
                        ProposalSubmissionItem(
                            project_id=project_id,
                            requirement_id=requirement.id,
                            partner_id=None,
                            status="not_started",
                        )
                    )
                    changed = True
                continue
            existing_partner_ids = {item.partner_id for item in items if item.partner_id is not None}
            for partner_id in sorted(partner_ids - existing_partner_ids, key=lambda value: str(value)):
                self.db.add(
                    ProposalSubmissionItem(
                        project_id=project_id,
                        requirement_id=requirement.id,
                        partner_id=partner_id,
                        status="not_started",
                    )
                )
                changed = True
            for item in items:
                if item.partner_id is None:
                    self.db.delete(item)
                    changed = True
        if changed:
            self.db.commit()

    def _submission_access(self, project_id: uuid.UUID, actor_user_id: uuid.UUID, actor_platform_role: str) -> dict[str, object]:
        project = self._get_project(project_id)
        if actor_platform_role == "super_admin":
            member_rows = list(
                self.db.scalars(
                    select(TeamMember).where(TeamMember.project_id == project_id, TeamMember.user_account_id == actor_user_id)
                ).all()
            )
            partner_ids = {member.organization_id for member in member_rows}
            return {
                "is_coordinator": True,
                "partner_ids": partner_ids,
            }
        membership = self.db.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == actor_user_id,
            )
        )
        member_rows = list(
            self.db.scalars(
                select(TeamMember).where(TeamMember.project_id == project_id, TeamMember.user_account_id == actor_user_id)
            ).all()
        )
        if not membership and not member_rows:
            raise ValidationError("Insufficient access to this project's submission package.")
        partner_ids = {member.organization_id for member in member_rows}
        is_coordinator = bool(project.coordinator_partner_id and project.coordinator_partner_id in partner_ids)
        return {
            "is_coordinator": is_coordinator,
            "partner_ids": partner_ids,
        }

    def _get_submission_requirement(
        self,
        project_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> ProposalSubmissionRequirement:
        requirement = self.db.get(ProposalSubmissionRequirement, requirement_id)
        if not requirement or requirement.project_id != project_id:
            raise NotFoundError("Submission requirement not found.")
        requirements = self.list_submission_requirements(project_id)
        for item in requirements:
            if item.id == requirement_id:
                return item
        raise NotFoundError("Submission requirement not found.")

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _get_template(self, template_id: uuid.UUID) -> ProposalTemplate:
        template = self.db.get(ProposalTemplate, template_id)
        if not template:
            raise NotFoundError("Proposal template not found.")
        return template

    def _get_call_library_entry(self, library_entry_id: uuid.UUID) -> ProposalCallLibraryEntry:
        item = self.db.get(ProposalCallLibraryEntry, library_entry_id)
        if not item:
            raise NotFoundError("Call library entry not found.")
        return item

    def _flush_or_conflict(self, message: str) -> None:
        from sqlalchemy.exc import IntegrityError

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(message) from exc


def run_call_library_ingest_job(job_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        ProposalService(db).process_call_library_ingest_job(job_id)
    finally:
        db.close()
