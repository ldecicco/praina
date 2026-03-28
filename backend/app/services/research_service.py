"""Research workspace CRUD service."""

from __future__ import annotations

import re
import uuid
import io
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import logging
import httpx

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.meeting import MeetingRecord
from app.models.auth import UserAccount
from app.models.document import DocumentChunk, DocumentScope, DocumentStatus, ProjectDocument
from app.models.organization import PartnerOrganization, TeamMember
from app.models.project import Project, ProjectKind
from app.models.research import (
    BibliographyCollection,
    BibliographyConcept,
    BibliographyNote,
    BibliographyReference,
    BibliographyTag,
    BibliographyUserStatus,
    BibliographyVisibility,
    CollectionMemberRole,
    OutputStatus,
    CollectionStatus,
    NoteType,
    ReadingStatus,
    ResearchAnnotation,
    ResearchCollection,
    ResearchCollectionMember,
    ResearchNote,
    ResearchReference,
    bibliography_collection_references,
    bibliography_reference_concepts,
    bibliography_reference_tags,
    research_collection_deliverables,
    research_collection_meetings,
    research_collection_tasks,
    research_collection_wps,
    research_note_references,
)
from app.models.teaching import TeachingProjectBackgroundMaterial
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.text_extraction import extract_pdf_abstract
from app.schemas.document import DocumentUploadPayload

logger = logging.getLogger(__name__)
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class DuplicateBibliographyError(ValidationError):
    def __init__(self, matches: list[tuple[str, BibliographyReference]]):
        super().__init__("Duplicate bibliography reference exists.")
        self.matches = matches


def _bibliography_embedding_text(item: BibliographyReference) -> str:
    """Build a text representation of a bibliography reference for embedding."""
    parts = [item.title]
    if item.authors:
        parts.append(", ".join(item.authors))
    if item.venue:
        parts.append(item.venue)
    if item.abstract:
        parts.append(item.abstract)
    return "\n".join(parts)


def _tokenize_query_terms(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) > 1}


class ResearchService:
    def __init__(self, db: Session):
        self.db = db

    # ── helpers ────────────────────────────────────────────────────────

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _collection_status(self, value: str) -> CollectionStatus:
        try:
            return CollectionStatus(value)
        except ValueError as exc:
            raise ValidationError("Invalid collection status.") from exc

    def _output_status(self, value: str) -> OutputStatus:
        try:
            return OutputStatus(value)
        except ValueError as exc:
            raise ValidationError("Invalid output status.") from exc

    def _member_role(self, value: str) -> CollectionMemberRole:
        try:
            return CollectionMemberRole(value)
        except ValueError as exc:
            raise ValidationError("Invalid member role.") from exc

    def _reading_status(self, value: str) -> ReadingStatus:
        try:
            return ReadingStatus(value)
        except ValueError as exc:
            raise ValidationError("Invalid reading status.") from exc

    def _note_type(self, value: str) -> NoteType:
        try:
            return NoteType(value)
        except ValueError as exc:
            raise ValidationError("Invalid note type.") from exc

    def _bibliography_visibility(self, value: str) -> BibliographyVisibility:
        try:
            return BibliographyVisibility(value)
        except ValueError as exc:
            raise ValidationError("Invalid bibliography visibility.") from exc

    @staticmethod
    def _normalize_bibliography_title(value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    @staticmethod
    def _normalize_tag_labels(labels: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in labels or []:
            label = " ".join((raw or "").strip().split())
            if not label:
                continue
            canonical = label.lower()
            if canonical in seen:
                continue
            seen.add(canonical)
            normalized.append(label)
        return normalized

    @staticmethod
    def _tag_slug(label: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        return slug[:64] or "tag"

    @staticmethod
    def _normalize_concept_labels(labels: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in labels or []:
            label = " ".join((raw or "").strip().split())
            if not label:
                continue
            canonical = label.lower()
            if canonical in seen:
                continue
            seen.add(canonical)
            normalized.append(label)
        return normalized

    @staticmethod
    def _concept_slug(label: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        return slug[:96] or "concept"

    def _ensure_bibliography_tags(self, labels: list[str]) -> list[BibliographyTag]:
        if not labels:
            return []
        normalized = self._normalize_tag_labels(labels)
        lowered = [label.lower() for label in normalized]
        existing = list(
            self.db.scalars(select(BibliographyTag).where(func.lower(BibliographyTag.label).in_(lowered))).all()
        )
        by_lower = {item.label.lower(): item for item in existing}
        created: list[BibliographyTag] = []
        existing_slugs = set(self.db.scalars(select(BibliographyTag.slug)).all())
        for label in normalized:
            key = label.lower()
            if key in by_lower:
                continue
            base_slug = self._tag_slug(label)
            slug = base_slug
            suffix = 2
            while slug in existing_slugs:
                slug = f"{base_slug[: max(1, 64 - len(str(suffix)) - 1)]}-{suffix}"
                suffix += 1
            item = BibliographyTag(label=label, slug=slug)
            self.db.add(item)
            self.db.flush()
            by_lower[key] = item
            existing_slugs.add(slug)
            created.append(item)
        return [by_lower[label.lower()] for label in normalized]

    def _set_bibliography_reference_tags(self, reference_id: uuid.UUID, labels: list[str]) -> None:
        tags = self._ensure_bibliography_tags(labels)
        self.db.execute(
            delete(bibliography_reference_tags).where(bibliography_reference_tags.c.reference_id == reference_id)
        )
        for tag in tags:
            self.db.execute(
                insert(bibliography_reference_tags).values(reference_id=reference_id, tag_id=tag.id)
            )

    def bibliography_tags_for_reference(self, reference_id: uuid.UUID) -> list[str]:
        try:
            rows = self.db.execute(
                select(BibliographyTag.label)
                .join(
                    bibliography_reference_tags,
                    bibliography_reference_tags.c.tag_id == BibliographyTag.id,
                )
                .where(bibliography_reference_tags.c.reference_id == reference_id)
                .order_by(func.lower(BibliographyTag.label))
            ).all()
            return [row[0] for row in rows]
        except ProgrammingError as exc:
            if "bibliography_tags" in str(exc) or "bibliography_reference_tags" in str(exc):
                self.db.rollback()
                return []
            raise

    def _ensure_bibliography_concepts(self, labels: list[str]) -> list[BibliographyConcept]:
        if not labels:
            return []
        normalized = self._normalize_concept_labels(labels)
        lowered = [label.lower() for label in normalized]
        existing = list(
            self.db.scalars(select(BibliographyConcept).where(func.lower(BibliographyConcept.label).in_(lowered))).all()
        )
        by_lower = {item.label.lower(): item for item in existing}
        existing_slugs = set(self.db.scalars(select(BibliographyConcept.slug)).all())
        for label in normalized:
            key = label.lower()
            if key in by_lower:
                continue
            base_slug = self._concept_slug(label)
            slug = base_slug
            suffix = 2
            while slug in existing_slugs:
                slug = f"{base_slug[: max(1, 96 - len(str(suffix)) - 1)]}-{suffix}"
                suffix += 1
            item = BibliographyConcept(label=label, slug=slug)
            self.db.add(item)
            self.db.flush()
            by_lower[key] = item
            existing_slugs.add(slug)
        return [by_lower[label.lower()] for label in normalized]

    def _set_bibliography_reference_concepts(self, reference_id: uuid.UUID, labels: list[str]) -> None:
        concepts = self._ensure_bibliography_concepts(labels)
        self.db.execute(
            delete(bibliography_reference_concepts).where(bibliography_reference_concepts.c.reference_id == reference_id)
        )
        for concept in concepts:
            self.db.execute(
                insert(bibliography_reference_concepts).values(reference_id=reference_id, concept_id=concept.id)
            )

    def bibliography_concepts_for_reference(self, reference_id: uuid.UUID) -> list[str]:
        try:
            rows = self.db.execute(
                select(BibliographyConcept.label)
                .join(
                    bibliography_reference_concepts,
                    bibliography_reference_concepts.c.concept_id == BibliographyConcept.id,
                )
                .where(bibliography_reference_concepts.c.reference_id == reference_id)
                .order_by(func.lower(BibliographyConcept.label))
            ).all()
            return [row[0] for row in rows]
        except ProgrammingError as exc:
            if "bibliography_concepts" in str(exc) or "bibliography_reference_concepts" in str(exc):
                self.db.rollback()
                return []
            raise

    def list_bibliography_tags(
        self,
        *,
        search: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[BibliographyTag], int]:
        try:
            stmt = select(BibliographyTag)
            if search:
                pattern = f"%{search.strip()}%"
                stmt = stmt.where(BibliographyTag.label.ilike(pattern))
            total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
            items = list(
                self.db.scalars(
                    stmt.order_by(func.lower(BibliographyTag.label))
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
            )
            return items, total
        except ProgrammingError as exc:
            if "bibliography_tags" in str(exc):
                self.db.rollback()
                return [], 0
            raise

    # ── collection counts ──────────────────────────────────────────────

    def _reference_count(self, collection_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ResearchReference).where(ResearchReference.collection_id == collection_id)
            ) or 0
        )

    def _note_count(self, collection_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ResearchNote).where(ResearchNote.collection_id == collection_id)
            ) or 0
        )

    def _member_count(self, collection_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ResearchCollectionMember).where(
                    ResearchCollectionMember.collection_id == collection_id
                )
            ) or 0
        )

    def _ref_note_count(self, reference_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(research_note_references).where(
                    research_note_references.c.reference_id == reference_id
                )
            ) or 0
        )

    def _ref_annotation_count(self, reference_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ResearchAnnotation).where(
                    ResearchAnnotation.reference_id == reference_id
                )
            ) or 0
        )

    def bibliography_link_count(self, bibliography_reference_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(ResearchReference).where(
                    ResearchReference.bibliography_reference_id == bibliography_reference_id
                )
            ) or 0
        )

    def bibliography_collection_reference_count(self, bibliography_collection_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(bibliography_collection_references).where(
                    bibliography_collection_references.c.collection_id == bibliography_collection_id
                )
            )
            or 0
        )

    # ══════════════════════════════════════════════════════════════════
    # Collections
    # ══════════════════════════════════════════════════════════════════

    def list_collections(
        self,
        project_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ResearchCollection], int]:
        self._get_project(project_id)
        stmt = select(ResearchCollection).where(ResearchCollection.project_id == project_id)
        if status_filter:
            stmt = stmt.where(ResearchCollection.status == status_filter)
        if member_id:
            member_collection_ids = select(ResearchCollectionMember.collection_id).where(
                ResearchCollectionMember.member_id == member_id
            ).scalar_subquery()
            stmt = stmt.where(ResearchCollection.id.in_(member_collection_ids))
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ResearchCollection.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def get_collection(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> ResearchCollection:
        item = self.db.scalar(
            select(ResearchCollection).where(
                ResearchCollection.project_id == project_id,
                ResearchCollection.id == collection_id,
            )
        )
        if not item:
            raise NotFoundError("Collection not found.")
        return item

    def create_collection(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        description: str | None = None,
        hypothesis: str | None = None,
        open_questions: list[str] | None = None,
        status: str = "active",
        tags: list[str] | None = None,
        overleaf_url: str | None = None,
        target_output_title: str | None = None,
        output_status: str = "not_started",
        created_by_member_id: uuid.UUID | None = None,
    ) -> ResearchCollection:
        self._get_project(project_id)
        item = ResearchCollection(
            project_id=project_id,
            title=title[:255].strip(),
            description=(description or "").strip() or None,
            hypothesis=(hypothesis or "").strip() or None,
            open_questions=[item.strip() for item in (open_questions or []) if item and item.strip()],
            status=self._collection_status(status),
            tags=tags or [],
            overleaf_url=(overleaf_url or "").strip() or None,
            target_output_title=(target_output_title or "").strip() or None,
            output_status=self._output_status(output_status),
            created_by_member_id=created_by_member_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_collection(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        hypothesis: str | None = None,
        open_questions: list[str] | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        overleaf_url: str | None = None,
        target_output_title: str | None = None,
        output_status: str | None = None,
    ) -> ResearchCollection:
        item = self.get_collection(project_id, collection_id)
        if title is not None:
            item.title = title[:255].strip()
        if description is not None:
            item.description = description.strip() or None
        if hypothesis is not None:
            item.hypothesis = hypothesis.strip() or None
        if open_questions is not None:
            item.open_questions = [entry.strip() for entry in open_questions if entry and entry.strip()]
        if status is not None:
            item.status = self._collection_status(status)
        if tags is not None:
            item.tags = tags
        if overleaf_url is not None:
            item.overleaf_url = overleaf_url.strip() or None
        if target_output_title is not None:
            item.target_output_title = target_output_title.strip() or None
        if output_status is not None:
            item.output_status = self._output_status(output_status)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_collection(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> None:
        item = self.get_collection(project_id, collection_id)
        self.db.delete(item)
        self.db.commit()

    # ── collection members ─────────────────────────────────────────────

    def list_collection_members(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> list[dict]:
        self.get_collection(project_id, collection_id)
        rows = self.db.execute(
            select(ResearchCollectionMember, TeamMember.full_name, PartnerOrganization.short_name)
            .join(TeamMember, ResearchCollectionMember.member_id == TeamMember.id)
            .join(PartnerOrganization, TeamMember.organization_id == PartnerOrganization.id)
            .where(ResearchCollectionMember.collection_id == collection_id)
            .order_by(ResearchCollectionMember.created_at)
        ).all()
        return [
            {
                "item": cm,
                "member_name": name or "",
                "organization_short_name": org or "",
            }
            for cm, name, org in rows
        ]

    def add_collection_member(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        member_id: uuid.UUID,
        role: str = "contributor",
    ) -> dict:
        self.get_collection(project_id, collection_id)
        existing = self.db.scalar(
            select(ResearchCollectionMember).where(
                ResearchCollectionMember.collection_id == collection_id,
                ResearchCollectionMember.member_id == member_id,
            )
        )
        if existing:
            raise ValidationError("Member already in collection.")
        cm = ResearchCollectionMember(
            collection_id=collection_id,
            member_id=member_id,
            role=self._member_role(role),
        )
        self.db.add(cm)
        self.db.commit()
        self.db.refresh(cm)
        row = self.db.execute(
            select(TeamMember.full_name, PartnerOrganization.short_name)
            .join(PartnerOrganization, TeamMember.organization_id == PartnerOrganization.id)
            .where(TeamMember.id == member_id)
        ).one_or_none()
        return {
            "item": cm,
            "member_name": row[0] if row else "",
            "organization_short_name": row[1] if row else "",
        }

    def update_collection_member_role(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        member_record_id: uuid.UUID,
        *,
        role: str,
    ) -> dict:
        self.get_collection(project_id, collection_id)
        cm = self.db.scalar(
            select(ResearchCollectionMember).where(
                ResearchCollectionMember.collection_id == collection_id,
                ResearchCollectionMember.id == member_record_id,
            )
        )
        if not cm:
            raise NotFoundError("Collection member not found.")
        cm.role = self._member_role(role)
        self.db.commit()
        self.db.refresh(cm)
        row = self.db.execute(
            select(TeamMember.full_name, PartnerOrganization.short_name)
            .join(PartnerOrganization, TeamMember.organization_id == PartnerOrganization.id)
            .where(TeamMember.id == cm.member_id)
        ).one_or_none()
        return {
            "item": cm,
            "member_name": row[0] if row else "",
            "organization_short_name": row[1] if row else "",
        }

    def remove_collection_member(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        member_record_id: uuid.UUID,
    ) -> None:
        self.get_collection(project_id, collection_id)
        cm = self.db.scalar(
            select(ResearchCollectionMember).where(
                ResearchCollectionMember.collection_id == collection_id,
                ResearchCollectionMember.id == member_record_id,
            )
        )
        if not cm:
            raise NotFoundError("Collection member not found.")
        self.db.delete(cm)
        self.db.commit()

    # ── WBS links ──────────────────────────────────────────────────────

    def set_wbs_links(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        wp_ids: list[str],
        task_ids: list[str],
        deliverable_ids: list[str],
    ) -> dict:
        self.get_collection(project_id, collection_id)

        # Replace WP links
        self.db.execute(delete(research_collection_wps).where(research_collection_wps.c.collection_id == collection_id))
        for wid in wp_ids:
            self.db.execute(insert(research_collection_wps).values(collection_id=collection_id, wp_id=uuid.UUID(wid)))

        # Replace task links
        self.db.execute(delete(research_collection_tasks).where(research_collection_tasks.c.collection_id == collection_id))
        for tid in task_ids:
            self.db.execute(insert(research_collection_tasks).values(collection_id=collection_id, task_id=uuid.UUID(tid)))

        # Replace deliverable links
        self.db.execute(delete(research_collection_deliverables).where(research_collection_deliverables.c.collection_id == collection_id))
        for did in deliverable_ids:
            self.db.execute(insert(research_collection_deliverables).values(collection_id=collection_id, deliverable_id=uuid.UUID(did)))

        self.db.commit()
        return self.get_wbs_links(project_id, collection_id)

    def get_wbs_links(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> dict:
        self.get_collection(project_id, collection_id)
        wp_ids = [
            str(r[0]) for r in self.db.execute(
                select(research_collection_wps.c.wp_id).where(research_collection_wps.c.collection_id == collection_id)
            ).all()
        ]
        task_ids = [
            str(r[0]) for r in self.db.execute(
                select(research_collection_tasks.c.task_id).where(research_collection_tasks.c.collection_id == collection_id)
            ).all()
        ]
        deliverable_ids = [
            str(r[0]) for r in self.db.execute(
                select(research_collection_deliverables.c.deliverable_id).where(research_collection_deliverables.c.collection_id == collection_id)
            ).all()
        ]
        return {"wp_ids": wp_ids, "task_ids": task_ids, "deliverable_ids": deliverable_ids}

    def list_collection_meetings(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> list[MeetingRecord]:
        self.get_collection(project_id, collection_id)
        return list(
            self.db.scalars(
                select(MeetingRecord)
                .join(research_collection_meetings, research_collection_meetings.c.meeting_id == MeetingRecord.id)
                .where(
                    research_collection_meetings.c.collection_id == collection_id,
                    MeetingRecord.project_id == project_id,
                )
                .order_by(MeetingRecord.starts_at.desc())
            ).all()
        )

    def set_collection_meetings(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        meeting_ids: list[str],
    ) -> list[MeetingRecord]:
        self.get_collection(project_id, collection_id)
        self.db.execute(
            delete(research_collection_meetings).where(
                research_collection_meetings.c.collection_id == collection_id
            )
        )
        cleaned_ids: list[uuid.UUID] = []
        for raw_id in meeting_ids:
            meeting_id = uuid.UUID(raw_id)
            meeting = self.db.scalar(
                select(MeetingRecord.id).where(
                    MeetingRecord.project_id == project_id,
                    MeetingRecord.id == meeting_id,
                )
            )
            if not meeting:
                raise NotFoundError(f"Meeting {raw_id} not found.")
            self.db.execute(
                insert(research_collection_meetings).values(
                    collection_id=collection_id,
                    meeting_id=meeting_id,
                )
            )
            cleaned_ids.append(meeting_id)
        self.db.commit()
        if not cleaned_ids:
            return []
        return list(
            self.db.scalars(
                select(MeetingRecord)
                .where(MeetingRecord.id.in_(cleaned_ids))
                .order_by(MeetingRecord.starts_at.desc())
            ).all()
        )

    # ══════════════════════════════════════════════════════════════════
    # References
    # ══════════════════════════════════════════════════════════════════

    def list_references(
        self,
        project_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None = None,
        reading_status: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchReference], int]:
        self._get_project(project_id)
        stmt = select(ResearchReference).where(ResearchReference.project_id == project_id)
        if collection_id:
            stmt = stmt.where(ResearchReference.collection_id == collection_id)
        if reading_status:
            stmt = stmt.where(ResearchReference.reading_status == reading_status)
        if tag:
            stmt = stmt.where(ResearchReference.tags.contains([tag]))
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(ResearchReference.title.ilike(pattern))
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ResearchReference.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def get_reference(self, project_id: uuid.UUID, reference_id: uuid.UUID) -> ResearchReference:
        item = self.db.scalar(
            select(ResearchReference).where(
                ResearchReference.project_id == project_id,
                ResearchReference.id == reference_id,
            )
        )
        if not item:
            raise NotFoundError("Reference not found.")
        return item

    def create_reference(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        collection_id: uuid.UUID | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        url: str | None = None,
        abstract: str | None = None,
        document_key: uuid.UUID | None = None,
        tags: list[str] | None = None,
        reading_status: str = "unread",
        bibliography_visibility: str = "shared",
        added_by_member_id: uuid.UUID | None = None,
        created_by_user_id: uuid.UUID | None = None,
    ) -> ResearchReference:
        self._get_project(project_id)
        bibliography = self.create_bibliography_reference(
            title=title,
            authors=authors or [],
            year=year,
            venue=venue,
            doi=doi,
            url=url,
            abstract=abstract,
            bibtex_raw=None,
            visibility=bibliography_visibility,
            created_by_user_id=created_by_user_id,
        )
        item = ResearchReference(
            project_id=project_id,
            bibliography_reference_id=bibliography.id,
            title=title[:512].strip(),
            collection_id=collection_id,
            authors=authors or [],
            year=year,
            venue=(venue or "").strip() or None,
            doi=(doi or "").strip() or None,
            url=(url or "").strip() or None,
            abstract=(abstract or "").strip() or None,
            document_key=document_key,
            tags=tags or [],
            reading_status=self._reading_status(reading_status),
            added_by_member_id=added_by_member_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_reference(
        self,
        project_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        title: str | None = None,
        collection_id: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        url: str | None = None,
        abstract: str | None = None,
        document_key: str | None = None,
        tags: list[str] | None = None,
        reading_status: str | None = None,
        bibliography_visibility: str | None = None,
    ) -> ResearchReference:
        item = self.get_reference(project_id, reference_id)
        if title is not None:
            item.title = title[:512].strip()
        if collection_id is not None:
            item.collection_id = uuid.UUID(collection_id) if collection_id else None
        if authors is not None:
            item.authors = authors
        if year is not None:
            item.year = year
        if venue is not None:
            item.venue = venue.strip() or None
        if doi is not None:
            item.doi = doi.strip() or None
        if url is not None:
            item.url = url.strip() or None
        if abstract is not None:
            item.abstract = abstract.strip() or None
        if document_key is not None:
            item.document_key = uuid.UUID(document_key) if document_key else None
        if tags is not None:
            item.tags = tags
        if reading_status is not None:
            item.reading_status = self._reading_status(reading_status)
        if item.bibliography_reference_id:
            bibliography = self.get_bibliography_reference(item.bibliography_reference_id)
            bibliography.title = item.title
            bibliography.authors = item.authors or []
            bibliography.year = item.year
            bibliography.venue = item.venue
            bibliography.doi = item.doi
            bibliography.url = item.url
            bibliography.abstract = item.abstract
            if bibliography_visibility is not None:
                bibliography.visibility = self._bibliography_visibility(bibliography_visibility)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_reference(self, project_id: uuid.UUID, reference_id: uuid.UUID) -> None:
        item = self.get_reference(project_id, reference_id)
        self.db.delete(item)
        self.db.commit()

    def move_reference(
        self,
        project_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None,
    ) -> ResearchReference:
        item = self.get_reference(project_id, reference_id)
        item.collection_id = collection_id
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_reference_status(
        self,
        project_id: uuid.UUID,
        reference_id: uuid.UUID,
        *,
        reading_status: str,
    ) -> ResearchReference:
        item = self.get_reference(project_id, reference_id)
        item.reading_status = self._reading_status(reading_status)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _bibliography_collection_visibility(self, value: str) -> BibliographyVisibility:
        return self._bibliography_visibility(value)

    def list_bibliography_collections(
        self,
        user_id: uuid.UUID,
        *,
        visibility: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BibliographyCollection], int]:
        stmt = select(BibliographyCollection).where(
            (BibliographyCollection.owner_user_id == user_id)
            | (BibliographyCollection.visibility == BibliographyVisibility.shared)
        )
        if visibility:
            stmt = stmt.where(BibliographyCollection.visibility == self._bibliography_collection_visibility(visibility))
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(BibliographyCollection.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return items, total

    def get_bibliography_collection(self, collection_id: uuid.UUID, actor_user_id: uuid.UUID | None = None) -> BibliographyCollection:
        item = self.db.get(BibliographyCollection, collection_id)
        if not item:
            raise NotFoundError("Bibliography collection not found.")
        if actor_user_id is not None and item.visibility != BibliographyVisibility.shared and item.owner_user_id != actor_user_id:
            raise ValidationError("Cannot access this bibliography collection.")
        return item

    def create_bibliography_collection(
        self,
        user_id: uuid.UUID,
        *,
        title: str,
        description: str | None = None,
        visibility: str = "private",
    ) -> BibliographyCollection:
        item = BibliographyCollection(
            title=title[:255].strip(),
            description=(description or "").strip() or None,
            visibility=self._bibliography_collection_visibility(visibility),
            owner_user_id=user_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_bibliography_collection(
        self,
        collection_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        visibility: str | None = None,
    ) -> BibliographyCollection:
        item = self.get_bibliography_collection(collection_id, actor_user_id)
        if item.owner_user_id != actor_user_id:
            raise ValidationError("Only the owner can edit this bibliography collection.")
        if title is not None:
            item.title = title[:255].strip()
        if description is not None:
            item.description = description.strip() or None
        if visibility is not None:
            item.visibility = self._bibliography_collection_visibility(visibility)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_bibliography_collection(self, collection_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        item = self.get_bibliography_collection(collection_id, actor_user_id)
        if item.owner_user_id != actor_user_id:
            raise ValidationError("Only the owner can delete this bibliography collection.")
        self.db.delete(item)
        self.db.commit()

    def add_reference_to_bibliography_collection(
        self, collection_id: uuid.UUID, bibliography_reference_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> None:
        collection = self.get_bibliography_collection(collection_id, actor_user_id)
        if collection.owner_user_id != actor_user_id:
            raise ValidationError("Only the owner can edit this bibliography collection.")
        self.get_bibliography_reference(bibliography_reference_id)
        existing = self.db.execute(
            select(bibliography_collection_references.c.reference_id).where(
                bibliography_collection_references.c.collection_id == collection_id,
                bibliography_collection_references.c.reference_id == bibliography_reference_id,
            )
        ).first()
        if not existing:
            self.db.execute(
                insert(bibliography_collection_references).values(
                    collection_id=collection_id,
                    reference_id=bibliography_reference_id,
                )
            )
        self.db.commit()

    def remove_reference_from_bibliography_collection(
        self, collection_id: uuid.UUID, bibliography_reference_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> None:
        collection = self.get_bibliography_collection(collection_id, actor_user_id)
        if collection.owner_user_id != actor_user_id:
            raise ValidationError("Only the owner can edit this bibliography collection.")
        self.db.execute(
            delete(bibliography_collection_references).where(
                bibliography_collection_references.c.collection_id == collection_id,
                bibliography_collection_references.c.reference_id == bibliography_reference_id,
            )
        )
        self.db.commit()

    def bibliography_reference_ids_for_collection(
        self, collection_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
    ) -> list[uuid.UUID]:
        self.get_bibliography_collection(collection_id, actor_user_id)
        rows = self.db.execute(
            select(bibliography_collection_references.c.reference_id).where(
                bibliography_collection_references.c.collection_id == collection_id
            )
        ).all()
        return [row[0] for row in rows]

    def bulk_link_bibliography_collection_to_research(
        self,
        bibliography_collection_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        added_by_member_id: uuid.UUID | None = None,
        reading_status: str = "unread",
    ) -> int:
        project = self._get_project(project_id)
        if project.project_kind not in {ProjectKind.research, ProjectKind.funded}:
            raise ValidationError("Target project is not a research project.")
        self.get_collection(project_id, collection_id)
        reference_ids = self.bibliography_reference_ids_for_collection(bibliography_collection_id, actor_user_id)
        created = 0
        for reference_id in reference_ids:
            existing = self.db.scalar(
                select(ResearchReference.id).where(
                    ResearchReference.project_id == project_id,
                    ResearchReference.collection_id == collection_id,
                    ResearchReference.bibliography_reference_id == reference_id,
                )
            )
            if existing:
                continue
            self.link_bibliography_reference(
                project_id,
                bibliography_reference_id=reference_id,
                collection_id=collection_id,
                reading_status=reading_status,
                added_by_member_id=added_by_member_id,
            )
            created += 1
        return created

    def bulk_link_bibliography_collection_to_teaching(
        self,
        bibliography_collection_id: uuid.UUID,
        *,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
    ) -> int:
        from app.services.teaching_service import TeachingService

        project = self._get_project(project_id)
        if project.project_kind != ProjectKind.teaching:
            raise ValidationError("Target project is not a teaching project.")
        reference_ids = self.bibliography_reference_ids_for_collection(bibliography_collection_id, actor_user_id)
        teaching_service = TeachingService(self.db)
        created = 0
        for reference_id in reference_ids:
            bibliography = self.get_bibliography_reference(reference_id)
            existing_background = self.db.scalar(
                select(TeachingProjectBackgroundMaterial.id).where(
                    TeachingProjectBackgroundMaterial.project_id == project_id,
                    TeachingProjectBackgroundMaterial.bibliography_reference_id == reference_id,
                )
            )
            if existing_background:
                continue
            teaching_service.create_background_material(
                project_id,
                material_type="paper",
                title=bibliography.title,
                bibliography_reference_id=str(reference_id),
                document_key=None,
                external_url=bibliography.url,
                notes=None,
            )
            created += 1
        return created

    def list_bibliography(
        self,
        user_id: uuid.UUID,
        *,
        bibliography_collection_id: uuid.UUID | None = None,
        search: str | None = None,
        visibility: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[BibliographyReference], int]:
        stmt = select(BibliographyReference).where(
            (BibliographyReference.visibility == BibliographyVisibility.shared)
            | ((BibliographyReference.visibility == BibliographyVisibility.private) & (BibliographyReference.created_by_user_id == user_id))
        )
        if bibliography_collection_id:
            stmt = stmt.join(
                bibliography_collection_references,
                bibliography_collection_references.c.reference_id == BibliographyReference.id,
            ).where(bibliography_collection_references.c.collection_id == bibliography_collection_id)
        if visibility:
            stmt = stmt.where(BibliographyReference.visibility == self._bibliography_visibility(visibility))
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(BibliographyReference.title.ilike(pattern))
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(BibliographyReference.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return items, total

    def get_bibliography_reference(self, bibliography_reference_id: uuid.UUID) -> BibliographyReference:
        item = self.db.get(BibliographyReference, bibliography_reference_id)
        if not item:
            raise NotFoundError("Bibliography reference not found.")
        return item

    def get_bibliography_reference_visible_to_user(
        self,
        bibliography_reference_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
    ) -> BibliographyReference:
        item = self.get_bibliography_reference(bibliography_reference_id)
        visibility = item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility)
        if visibility == BibliographyVisibility.shared.value:
            return item
        if item.created_by_user_id == user_id:
            return item
        raise NotFoundError("Bibliography reference not found.")

    def bibliography_graph(
        self,
        *,
        user_id: uuid.UUID,
        reference_ids: list[uuid.UUID],
        include_authors: bool = True,
        include_concepts: bool = True,
        include_tags: bool = False,
        include_semantic: bool = True,
        include_bibliography_collections: bool = True,
        include_research_links: bool = True,
        include_teaching_links: bool = True,
        semantic_threshold: float = 0.78,
        semantic_top_k: int = 3,
    ) -> dict[str, list[dict[str, object]]]:
        if not reference_ids:
            return {"nodes": [], "edges": []}

        visible_stmt = select(BibliographyReference).where(
            BibliographyReference.id.in_(reference_ids),
            (
                (BibliographyReference.visibility == BibliographyVisibility.shared)
                | (
                    (BibliographyReference.visibility == BibliographyVisibility.private)
                    & (BibliographyReference.created_by_user_id == user_id)
                )
            ),
        )
        references = list(self.db.scalars(visible_stmt).all())
        if not references:
            return {"nodes": [], "edges": []}

        tag_lookup = {item.id: self.bibliography_tags_for_reference(item.id) for item in references}
        concept_lookup = {item.id: self.bibliography_concepts_for_reference(item.id) for item in references}
        nodes: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        node_ids: set[str] = set()
        edge_ids: set[str] = set()

        def add_node(node_id: str, label: str, node_type: str, *, ref_id: str | None = None) -> None:
            if node_id in node_ids:
                return
            node_ids.add(node_id)
            nodes.append({"id": node_id, "label": label, "node_type": node_type, "ref_id": ref_id})

        def add_edge(edge_id: str, source: str, target: str, edge_type: str, *, weight: float | None = None) -> None:
            if edge_id in edge_ids or source == target:
                return
            edge_ids.add(edge_id)
            edges.append({"id": edge_id, "source": source, "target": target, "edge_type": edge_type, "weight": weight})

        def can_access_project(project_id: uuid.UUID) -> bool:
            try:
                AuthService(self.db)._get_project_role(project_id, user_id)
                return True
            except NotFoundError:
                actor = self.db.get(UserAccount, user_id)
                return bool(actor and actor.platform_role == "super_admin")
            except Exception:
                return False

        for item in references:
            add_node(f"paper:{item.id}", item.title, "paper", ref_id=str(item.id))

        if include_authors:
            for item in references:
                for raw_author in item.authors or []:
                    author = " ".join((raw_author or "").strip().split())
                    if not author:
                        continue
                    author_id = f"author:{author.lower()}"
                    add_node(author_id, author, "author")
                    add_edge(
                        f"edge:paper-author:{item.id}:{author.lower()}",
                        f"paper:{item.id}",
                        author_id,
                        "written_by",
                    )

        if include_tags:
            for item in references:
                for raw_tag in tag_lookup.get(item.id, []):
                    tag = " ".join((raw_tag or "").strip().split())
                    if not tag:
                        continue
                    tag_id = f"tag:{tag.lower()}"
                    add_node(tag_id, tag, "tag")
                    add_edge(
                        f"edge:paper-tag:{item.id}:{tag.lower()}",
                        f"paper:{item.id}",
                        tag_id,
                        "tagged",
                    )

        if include_concepts:
            for item in references:
                for raw_concept in concept_lookup.get(item.id, []):
                    concept = " ".join((raw_concept or "").strip().split())
                    if not concept:
                        continue
                    concept_id = f"concept:{concept.lower()}"
                    add_node(concept_id, concept, "concept")
                    add_edge(
                        f"edge:paper-concept:{item.id}:{concept.lower()}",
                        f"paper:{item.id}",
                        concept_id,
                        "mentions_concept",
                    )

        if include_bibliography_collections:
            collection_rows = self.db.execute(
                select(
                    bibliography_collection_references.c.reference_id,
                    BibliographyCollection.id,
                    BibliographyCollection.title,
                    BibliographyCollection.visibility,
                    BibliographyCollection.owner_user_id,
                )
                .join(
                    BibliographyCollection,
                    BibliographyCollection.id == bibliography_collection_references.c.collection_id,
                )
                .where(bibliography_collection_references.c.reference_id.in_([item.id for item in references]))
            ).all()
            for reference_id, collection_id, title, visibility, owner_user_id in collection_rows:
                if visibility != BibliographyVisibility.shared and owner_user_id != user_id:
                    continue
                node_id = f"bib-collection:{collection_id}"
                add_node(node_id, title, "bibliography_collection")
                add_edge(
                    f"edge:paper-bib-collection:{reference_id}:{collection_id}",
                    f"paper:{reference_id}",
                    node_id,
                    "in_bibliography_collection",
                )

        if include_research_links:
            research_rows = self.db.execute(
                select(
                    ResearchReference.bibliography_reference_id,
                    ResearchCollection.id,
                    ResearchCollection.title,
                    ResearchCollection.project_id,
                    Project.title,
                )
                .join(ResearchCollection, ResearchCollection.id == ResearchReference.collection_id)
                .join(Project, Project.id == ResearchCollection.project_id)
                .where(
                    ResearchReference.bibliography_reference_id.in_([item.id for item in references]),
                    ResearchReference.collection_id.is_not(None),
                )
            ).all()
            for reference_id, collection_id, collection_title, project_id, project_title in research_rows:
                if not can_access_project(project_id):
                    continue
                project_node_id = f"research-project:{project_id}"
                collection_node_id = f"research-collection:{collection_id}"
                add_node(project_node_id, project_title, "research_project")
                add_node(collection_node_id, collection_title, "research_collection")
                add_edge(
                    f"edge:research-project-collection:{project_id}:{collection_id}",
                    project_node_id,
                    collection_node_id,
                    "contains_collection",
                )
                add_edge(
                    f"edge:paper-research-collection:{reference_id}:{collection_id}",
                    f"paper:{reference_id}",
                    collection_node_id,
                    "linked_to_research_collection",
                )

        if include_teaching_links:
            teaching_rows = self.db.execute(
                select(
                    TeachingProjectBackgroundMaterial.bibliography_reference_id,
                    TeachingProjectBackgroundMaterial.project_id,
                    Project.title,
                )
                .join(Project, Project.id == TeachingProjectBackgroundMaterial.project_id)
                .where(
                    TeachingProjectBackgroundMaterial.bibliography_reference_id.in_([item.id for item in references]),
                    TeachingProjectBackgroundMaterial.bibliography_reference_id.is_not(None),
                )
            ).all()
            for reference_id, project_id, project_title in teaching_rows:
                if not can_access_project(project_id):
                    continue
                node_id = f"teaching-project:{project_id}"
                add_node(node_id, project_title, "teaching_project")
                add_edge(
                    f"edge:paper-teaching-project:{reference_id}:{project_id}",
                    f"paper:{reference_id}",
                    node_id,
                    "used_in_teaching_project",
                )

        if include_semantic:
            top_k = max(1, min(int(semantic_top_k or 3), 10))
            threshold = max(0.0, min(float(semantic_threshold or 0.78), 0.999))
            papers_with_embeddings = [item for item in references if item.embedding is not None]
            for item in papers_with_embeddings:
                cosine_distance = BibliographyReference.embedding.cosine_distance(item.embedding)
                rows = self.db.execute(
                    select(BibliographyReference.id, cosine_distance.label("distance"))
                    .where(
                        BibliographyReference.id.in_([other.id for other in papers_with_embeddings]),
                        BibliographyReference.id != item.id,
                        BibliographyReference.embedding.is_not(None),
                    )
                    .order_by(cosine_distance.asc())
                    .limit(top_k)
                ).all()
                for other_id, distance in rows:
                    similarity = 1.0 - float(distance)
                    if similarity < threshold:
                        continue
                    left, right = sorted((str(item.id), str(other_id)))
                    add_edge(
                        f"edge:semantic:{left}:{right}",
                        f"paper:{left}",
                        f"paper:{right}",
                        "semantic",
                        weight=similarity,
                    )

        return {"nodes": nodes, "edges": edges}

    def create_bibliography_reference(
        self,
        *,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        url: str | None = None,
        abstract: str | None = None,
        bibtex_raw: str | None = None,
        tags: list[str] | None = None,
        visibility: str = "shared",
        created_by_user_id: uuid.UUID | None = None,
        allow_duplicate: bool = False,
        reuse_existing_id: uuid.UUID | None = None,
    ) -> BibliographyReference:
        duplicates = self.find_bibliography_duplicates(
            created_by_user_id=created_by_user_id,
            doi=doi,
            title=title,
        )
        if reuse_existing_id:
            existing = self.get_bibliography_reference(reuse_existing_id)
            visible_ids = {item.id for _, item in duplicates}
            if duplicates and existing.id not in visible_ids:
                raise ValidationError("Selected bibliography reference is not a valid duplicate candidate.")
            self._merge_existing_bibliography_reference(
                existing,
                authors=authors,
                year=year,
                venue=venue,
                doi=doi,
                url=url,
                abstract=abstract,
                bibtex_raw=bibtex_raw,
                tags=tags,
            )
            return existing
        if duplicates and not allow_duplicate:
            raise DuplicateBibliographyError(duplicates)
        item = BibliographyReference(
            title=title[:512].strip(),
            authors=authors or [],
            year=year,
            venue=(venue or "").strip() or None,
            doi=(doi or "").strip() or None,
            url=(url or "").strip() or None,
            abstract=(abstract or "").strip() or None,
            bibtex_raw=(bibtex_raw or "").strip() or None,
            visibility=self._bibliography_visibility(visibility),
            created_by_user_id=created_by_user_id,
        )
        self.db.add(item)
        self.db.flush()
        self._set_bibliography_reference_tags(item.id, tags or [])
        self.db.commit()
        self.db.refresh(item)
        return item

    def import_bibliography_identifiers(
        self,
        *,
        identifiers: str,
        visibility: str,
        created_by_user_id: uuid.UUID | None,
        source_project_id: uuid.UUID | None = None,
    ) -> tuple[list[BibliographyReference], list[BibliographyReference], list[str]]:
        tokens = self._parse_bibliography_identifier_tokens(identifiers)
        if not tokens:
            raise ValidationError("No valid DOI or arXiv identifiers found.")

        created: list[BibliographyReference] = []
        reused: list[BibliographyReference] = []
        errors: list[str] = []

        for token in tokens:
            try:
                if token["kind"] == "doi":
                    metadata = self._fetch_doi_metadata(token["value"])
                    item, created_new = self._create_or_reuse_bibliography_reference(
                        title=metadata["title"],
                        authors=metadata["authors"],
                        year=metadata["year"],
                        venue=metadata["venue"],
                        doi=metadata["doi"],
                        url=metadata["url"],
                        abstract=metadata["abstract"],
                        bibtex_raw=None,
                        tags=[],
                        visibility=visibility,
                        created_by_user_id=created_by_user_id,
                    )
                else:
                    metadata = self._fetch_arxiv_metadata(token["value"])
                    item, created_new = self._create_or_reuse_bibliography_reference(
                        title=metadata["title"],
                        authors=metadata["authors"],
                        year=metadata["year"],
                        venue=metadata["venue"],
                        doi=metadata["doi"],
                        url=metadata["url"],
                        abstract=metadata["abstract"],
                        bibtex_raw=None,
                        tags=[],
                        visibility=visibility,
                        created_by_user_id=created_by_user_id,
                    )
                    if source_project_id is None:
                        raise ValidationError("Select a project before importing arXiv papers.")
                    if not item.document_key:
                        self._attach_bibliography_pdf_from_url(
                            project_id=source_project_id,
                            bibliography_reference_id=item.id,
                            url=metadata["pdf_url"],
                            file_name=f"{token['value'].replace('/', '_')}.pdf",
                        )
                        item = self.get_bibliography_reference(item.id)

                (created if created_new else reused).append(item)
            except Exception as exc:
                errors.append(f"{token['raw']}: {exc}")

        return created, reused, errors

    def _create_or_reuse_bibliography_reference(
        self,
        *,
        title: str,
        authors: list[str] | None,
        year: int | None,
        venue: str | None,
        doi: str | None,
        url: str | None,
        abstract: str | None,
        bibtex_raw: str | None,
        tags: list[str] | None,
        visibility: str,
        created_by_user_id: uuid.UUID | None,
    ) -> tuple[BibliographyReference, bool]:
        duplicates = self.find_bibliography_duplicates(
            created_by_user_id=created_by_user_id,
            doi=doi,
            title=title,
        )
        if duplicates:
            existing = duplicates[0][1]
            return (
                self._merge_existing_bibliography_reference(
                    existing,
                    authors=authors,
                    year=year,
                    venue=venue,
                    doi=doi,
                    url=url,
                    abstract=abstract,
                    bibtex_raw=bibtex_raw,
                    tags=tags,
                ),
                False,
            )
        return (
            self.create_bibliography_reference(
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                doi=doi,
                url=url,
                abstract=abstract,
                bibtex_raw=bibtex_raw,
                tags=tags,
                visibility=visibility,
                created_by_user_id=created_by_user_id,
                allow_duplicate=True,
            ),
            True,
        )

    def _parse_bibliography_identifier_tokens(self, raw: str) -> list[dict[str, str]]:
        tokens: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for chunk in re.split(r"[\n,;]+", raw or ""):
            value = chunk.strip()
            if not value:
                continue
            parsed = self._classify_bibliography_identifier(value)
            if not parsed:
                continue
            key = (parsed["kind"], parsed["value"])
            if key in seen:
                continue
            seen.add(key)
            tokens.append(parsed)
        return tokens

    def _classify_bibliography_identifier(self, raw: str) -> dict[str, str] | None:
        value = raw.strip()
        doi_match = re.search(r"(10\.\d{4,9}/[^\s]+)", value, re.IGNORECASE)
        if doi_match:
            return {"kind": "doi", "value": doi_match.group(1).rstrip(".,);"), "raw": raw}

        arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?\s#/]+)", value, re.IGNORECASE)
        if arxiv_match:
            arxiv_id = arxiv_match.group(1).removesuffix(".pdf")
            return {"kind": "arxiv", "value": arxiv_id, "raw": raw}

        simple_arxiv = re.fullmatch(r"(?:arxiv:)?([a-z\-]+/\d{7}|\d{4}\.\d{4,5}(?:v\d+)?)", value, re.IGNORECASE)
        if simple_arxiv:
            return {"kind": "arxiv", "value": simple_arxiv.group(1), "raw": raw}
        return None

    def _fetch_doi_metadata(self, doi: str) -> dict[str, object]:
        url = f"https://api.crossref.org/works/{quote(doi.strip(), safe='')}"
        with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": f"{settings.app_name}/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
        message = response.json().get("message", {})
        title = ((message.get("title") or [""])[0] or "").strip()
        if not title:
            raise ValidationError("Crossref returned no title.")
        authors = []
        for author in message.get("author") or []:
            given = (author.get("given") or "").strip()
            family = (author.get("family") or "").strip()
            full = " ".join(part for part in [given, family] if part).strip()
            if full:
                authors.append(full)
        year = None
        for field in ("published-print", "published-online", "issued"):
            date_parts = (((message.get(field) or {}).get("date-parts") or [[]])[0] or [])
            if date_parts:
                year = int(date_parts[0])
                break
        abstract = (message.get("abstract") or "").strip() or None
        if abstract:
            abstract = re.sub(r"<[^>]+>", " ", abstract)
            abstract = " ".join(abstract.split())
        venue = ((message.get("container-title") or [""])[0] or "").strip() or None
        return {
            "title": title,
            "authors": authors,
            "year": year,
            "venue": venue,
            "doi": doi.strip(),
            "url": (message.get("URL") or f"https://doi.org/{doi.strip()}").strip(),
            "abstract": abstract,
        }

    def _fetch_arxiv_metadata(self, arxiv_id: str) -> dict[str, object]:
        with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": f"{settings.app_name}/1.0"}) as client:
            response = client.get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id})
            response.raise_for_status()
        root = ET.fromstring(response.text)
        entry = root.find("atom:entry", ARXIV_NS)
        if entry is None:
            raise ValidationError("arXiv entry not found.")
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ARXIV_NS) or "").split())
        if not title:
            raise ValidationError("arXiv returned no title.")
        authors = [
            " ".join((author.findtext("atom:name", default="", namespaces=ARXIV_NS) or "").split())
            for author in entry.findall("atom:author", ARXIV_NS)
        ]
        authors = [author for author in authors if author]
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ARXIV_NS) or "").split()) or None
        published = entry.findtext("atom:published", default="", namespaces=ARXIV_NS)
        year = int(published[:4]) if published[:4].isdigit() else None
        doi = entry.findtext("arxiv:doi", default="", namespaces=ARXIV_NS).strip() or None
        return {
            "title": title,
            "authors": authors,
            "year": year,
            "venue": "arXiv",
            "doi": doi,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "abstract": summary,
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        }

    def _attach_bibliography_pdf_from_url(
        self,
        *,
        project_id: uuid.UUID,
        bibliography_reference_id: uuid.UUID,
        url: str,
        file_name: str,
    ) -> BibliographyReference:
        with httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": f"{settings.app_name}/1.0"}) as client:
            response = client.get(url)
            response.raise_for_status()
        return self.attach_bibliography_file(
            project_id,
            bibliography_reference_id,
            file_name=file_name,
            content_type="application/pdf",
            file_stream=io.BytesIO(response.content),
        )

    def _merge_existing_bibliography_reference(
        self,
        existing: BibliographyReference,
        *,
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        url: str | None = None,
        abstract: str | None = None,
        bibtex_raw: str | None = None,
        tags: list[str] | None = None,
    ) -> BibliographyReference:
        if not existing.abstract and abstract:
            existing.abstract = abstract.strip()
        if not existing.url and url:
            existing.url = url.strip()
        if not existing.venue and venue:
            existing.venue = venue.strip()
        if not existing.year and year:
            existing.year = year
        if not existing.doi and doi:
            existing.doi = doi.strip() or None
        if (not existing.authors) and authors:
            existing.authors = authors
        if bibliography_raw := (bibtex_raw or "").strip():
            existing.bibtex_raw = bibliography_raw
        if tags:
            merged_tags = sorted(set(self.bibliography_tags_for_reference(existing.id)) | set(tags), key=str.lower)
            self._set_bibliography_reference_tags(existing.id, merged_tags)
        self.db.commit()
        self.db.refresh(existing)
        return existing

    def update_bibliography_reference(
        self,
        bibliography_reference_id: uuid.UUID,
        *,
        title: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str | None = None,
        doi: str | None = None,
        url: str | None = None,
        abstract: str | None = None,
        bibtex_raw: str | None = None,
        tags: list[str] | None = None,
        visibility: str | None = None,
    ) -> BibliographyReference:
        item = self.get_bibliography_reference(bibliography_reference_id)
        if title is not None:
            item.title = title[:512].strip()
        if authors is not None:
            item.authors = authors
        if year is not None:
            item.year = year
        if venue is not None:
            item.venue = venue.strip() or None
        if doi is not None:
            item.doi = doi.strip() or None
        if url is not None:
            item.url = url.strip() or None
        if abstract is not None:
            item.abstract = abstract.strip() or None
        if bibtex_raw is not None:
            item.bibtex_raw = bibtex_raw.strip() or None
        if tags is not None:
            self._set_bibliography_reference_tags(item.id, tags)
        if visibility is not None:
            item.visibility = self._bibliography_visibility(visibility)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_bibliography_reference(self, bibliography_reference_id: uuid.UUID) -> None:
        item = self.get_bibliography_reference(bibliography_reference_id)
        self._delete_bibliography_attachment(item)
        self.db.delete(item)
        self.db.commit()

    def link_bibliography_reference(
        self,
        project_id: uuid.UUID,
        *,
        bibliography_reference_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
        reading_status: str = "unread",
        added_by_member_id: uuid.UUID | None = None,
    ) -> ResearchReference:
        self._get_project(project_id)
        bibliography = self.get_bibliography_reference(bibliography_reference_id)
        existing = self.db.scalar(
            select(ResearchReference).where(
                ResearchReference.project_id == project_id,
                ResearchReference.collection_id == collection_id,
                ResearchReference.bibliography_reference_id == bibliography_reference_id,
            )
        )
        if existing:
            return existing
        linked_document_key = None
        if bibliography.document_key and bibliography.source_project_id:
            if bibliography.source_project_id == project_id:
                linked_document_key = bibliography.document_key
            else:
                cloned = DocumentService(self.db).clone_document_to_project(
                    source_project_id=bibliography.source_project_id,
                    source_document_key=bibliography.document_key,
                    target_project_id=project_id,
                    title=bibliography.title,
                    metadata_json={
                        "category": "bibliography_reference",
                        "bibliography_reference_id": str(bibliography.id),
                    },
                )
                DocumentIngestionService(self.db).reindex_document(project_id, cloned.id)
                linked_document_key = cloned.document_key
        item = ResearchReference(
            project_id=project_id,
            bibliography_reference_id=bibliography_reference_id,
            collection_id=collection_id,
            title=bibliography.title,
            authors=bibliography.authors or [],
            year=bibliography.year,
            venue=bibliography.venue,
            doi=bibliography.doi,
            url=bibliography.url,
            abstract=bibliography.abstract,
            document_key=linked_document_key,
            tags=[],
            reading_status=self._reading_status(reading_status),
            added_by_member_id=added_by_member_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def attach_bibliography_file(
        self,
        project_id: uuid.UUID,
        bibliography_reference_id: uuid.UUID,
        *,
        file_name: str,
        content_type: str,
        file_stream: BinaryIO,
    ) -> BibliographyReference:
        item = self.get_bibliography_reference(bibliography_reference_id)
        document = DocumentService(self.db).create_document(
            project_id=project_id,
            payload=DocumentUploadPayload(
                scope=DocumentScope.project,
                title=item.title[:255],
                metadata_json={
                    "category": "bibliography_reference",
                    "bibliography_reference_id": str(item.id),
                },
            ),
            file_name=file_name,
            content_type=content_type,
            file_stream=file_stream,
        )
        DocumentIngestionService(self.db).reindex_document(project_id, document.id)
        item.source_project_id = project_id
        item.document_key = document.document_key
        item.attachment_path = document.storage_uri
        item.attachment_filename = document.original_filename
        item.attachment_mime_type = document.mime_type
        if not item.abstract and (document.mime_type == "application/pdf" or Path(document.storage_uri).suffix.lower() == ".pdf"):
            try:
                abstract = extract_pdf_abstract(Path(document.storage_uri), max_pages=2)
                if abstract:
                    item.abstract = abstract
            except Exception:
                logger.warning("Failed to auto-extract abstract for bibliography reference %s", item.id, exc_info=True)
        self.db.commit()
        self.db.refresh(item)
        return item

    def ensure_bibliography_document_ingested(
        self,
        bibliography_reference_id: uuid.UUID,
        *,
        source_project_id: uuid.UUID | None = None,
    ) -> BibliographyReference:
        item = self.get_bibliography_reference(bibliography_reference_id)

        if item.document_key and item.source_project_id:
            document = self.db.scalar(
                select(ProjectDocument)
                .where(
                    ProjectDocument.project_id == item.source_project_id,
                    ProjectDocument.document_key == item.document_key,
                )
                .order_by(ProjectDocument.version.desc())
                .limit(1)
            )
            if document:
                DocumentIngestionService(self.db).reindex_document(item.source_project_id, document.id)
                self.db.refresh(item)
                return item

        if not item.attachment_path:
            raise ValidationError("No PDF attached to this paper.")
        if source_project_id is None:
            raise ValidationError("Select a project before ingesting this PDF.")

        path = Path(item.attachment_path)
        if not path.is_absolute():
            root = Path(settings.documents_storage_path)
            if not root.is_absolute():
                root = (Path.cwd() / root).resolve()
            path = (root / path).resolve()
        if not path.exists():
            raise NotFoundError("Bibliography attachment file not found.")

        with path.open("rb") as stream:
            updated = self.attach_bibliography_file(
                source_project_id,
                bibliography_reference_id,
                file_name=item.attachment_filename or path.name,
                content_type=item.attachment_mime_type or "application/pdf",
                file_stream=stream,
            )
        return updated

    def find_bibliography_duplicates(
        self,
        *,
        doi: str | None,
        title: str,
        created_by_user_id: uuid.UUID | None,
    ) -> list[tuple[str, BibliographyReference]]:
        matches: list[tuple[str, BibliographyReference]] = []
        seen: set[uuid.UUID] = set()

        visible_filter = (
            (BibliographyReference.visibility == BibliographyVisibility.shared)
            | (
                (BibliographyReference.visibility == BibliographyVisibility.private)
                & (BibliographyReference.created_by_user_id == created_by_user_id)
            )
        )

        if doi and doi.strip():
            doi_matches = self.db.scalars(
                select(BibliographyReference).where(
                    visible_filter,
                    BibliographyReference.doi == doi.strip(),
                )
            ).all()
            for item in doi_matches:
                if item.id in seen:
                    continue
                seen.add(item.id)
                matches.append(("doi", item))

        normalized_title = self._normalize_bibliography_title(title)
        if normalized_title:
            rows = self.db.scalars(
                select(BibliographyReference).where(
                    visible_filter,
                    BibliographyReference.title.ilike(title.strip()),
                )
            ).all()
            for item in rows:
                if self._normalize_bibliography_title(item.title) != normalized_title or item.id in seen:
                    continue
                seen.add(item.id)
                matches.append(("title", item))

        return matches

    @staticmethod
    def _write_file(file_stream: BinaryIO, target_path: Path) -> int:
        total = 0
        with target_path.open("wb") as output:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                total += len(chunk)
        return total

    def _bibliography_storage_path(self, bibliography_reference_id: uuid.UUID, file_name: str) -> Path:
        root = Path(settings.documents_storage_path)
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        target_dir = root / "_bibliography" / str(bibliography_reference_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / file_name

    @staticmethod
    def _delete_bibliography_attachment(item: BibliographyReference) -> None:
        if not item.attachment_path:
            return
        path = Path(item.attachment_path)
        if path.exists():
            path.unlink(missing_ok=True)

    # ── bibliography embeddings ──────────────────────────────────────

    def _embed_bibliography_reference(self, item: BibliographyReference) -> None:
        """Generate and store an embedding for a bibliography reference. Fails silently."""
        from app.services.embedding_service import EmbeddingService

        text = _bibliography_embedding_text(item)
        if not text.strip():
            return
        try:
            svc = EmbeddingService(self.db)
            vectors = svc.embed_texts([text])
            if vectors:
                item.embedding = vectors[0]
        except Exception:
            logger.warning("Failed to embed bibliography reference %s", item.id, exc_info=True)

    def embed_bibliography_backfill(self) -> int:
        """Backfill embeddings for all bibliography references missing one. Returns count."""
        from app.services.embedding_service import EmbeddingService

        items = list(self.db.scalars(
            select(BibliographyReference).where(BibliographyReference.embedding.is_(None))
        ).all())
        if not items:
            return 0
        svc = EmbeddingService(self.db)
        count = 0
        batch_size = max(1, settings.embedding_batch_size)
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            texts = [_bibliography_embedding_text(item) for item in batch]
            try:
                vectors = svc.embed_texts(texts)
                for item, vec in zip(batch, vectors):
                    item.embedding = vec
                    count += 1
            except Exception:
                logger.warning("Failed to embed bibliography batch at offset %d", i, exc_info=True)
        self.db.flush()
        return count

    def search_bibliography_semantic(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        visibility: str | None = None,
        top_k: int = 20,
    ) -> list[BibliographyReference]:
        """Semantic search over bibliography references using cosine similarity."""
        from app.services.embedding_service import EmbeddingService

        svc = EmbeddingService(self.db)
        try:
            vectors = svc.embed_texts([query])
        except Exception:
            logger.warning("Failed to embed search query", exc_info=True)
            return []
        if not vectors:
            return []
        query_embedding = vectors[0]

        cosine_dist = BibliographyReference.embedding.cosine_distance(query_embedding)
        stmt = (
            select(BibliographyReference)
            .where(
                BibliographyReference.embedding.isnot(None),
                (BibliographyReference.visibility == BibliographyVisibility.shared)
                | (
                    (BibliographyReference.visibility == BibliographyVisibility.private)
                    & (BibliographyReference.created_by_user_id == user_id)
                ),
            )
            .order_by(cosine_dist)
            .limit(top_k)
        )
        if visibility:
            stmt = stmt.where(BibliographyReference.visibility == self._bibliography_visibility(visibility))
        return list(self.db.scalars(stmt).all())

    def search_bibliography_semantic_with_evidence(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        visibility: str | None = None,
        top_k: int = 20,
        chunk_limit: int = 3,
    ) -> list[tuple[BibliographyReference, list[dict[str, Any]]]]:
        from app.services.embedding_service import EmbeddingService

        svc = EmbeddingService(self.db)
        try:
            vectors = svc.embed_texts([query])
        except Exception:
            logger.warning("Failed to embed search query", exc_info=True)
            return []
        if not vectors:
            return []
        query_embedding = vectors[0]

        cosine_dist = BibliographyReference.embedding.cosine_distance(query_embedding)
        stmt = (
            select(BibliographyReference)
            .where(
                BibliographyReference.embedding.isnot(None),
                (BibliographyReference.visibility == BibliographyVisibility.shared)
                | (
                    (BibliographyReference.visibility == BibliographyVisibility.private)
                    & (BibliographyReference.created_by_user_id == user_id)
                ),
            )
            .order_by(cosine_dist)
            .limit(top_k)
        )
        if visibility:
            stmt = stmt.where(BibliographyReference.visibility == self._bibliography_visibility(visibility))
        items = list(self.db.scalars(stmt).all())
        return [
            (item, self.bibliography_document_chunk_evidence(item, query_embedding, query=query, limit=chunk_limit))
            for item in items
        ]

    def bibliography_semantic_evidence(self, item: BibliographyReference, query: str, *, limit: int = 3) -> list[str]:
        terms = _tokenize_query_terms(query)
        if not terms:
            return []
        candidates: list[tuple[int, str]] = []

        def add_candidate(text: str | None) -> None:
            normalized = " ".join((text or "").split())
            if not normalized:
                return
            lowered = normalized.lower()
            score = sum(1 for term in terms if term in lowered)
            if score > 0:
                candidates.append((score, normalized[:420]))

        add_candidate(item.title)
        if item.authors:
            add_candidate(", ".join(item.authors))
        if item.venue or item.year:
            add_candidate(" · ".join(str(part) for part in [item.venue, item.year] if part))
        add_candidate(item.abstract)
        add_candidate(item.bibtex_raw)

        candidates.sort(key=lambda row: (-row[0], len(row[1])))
        evidence: list[str] = []
        seen: set[str] = set()
        for _, text in candidates:
            if text in seen:
                continue
            seen.add(text)
            evidence.append(text)
            if len(evidence) >= limit:
                break
        return evidence

    def bibliography_document_chunk_evidence(
        self,
        item: BibliographyReference,
        query_embedding: list[float],
        *,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        if item.document_key is None or item.source_project_id is None:
            return [
                {"text": text, "similarity": None}
                for text in self.bibliography_semantic_evidence(item, query, limit=limit)
            ]

        document = self.db.scalar(
            select(ProjectDocument)
            .where(
                ProjectDocument.project_id == item.source_project_id,
                ProjectDocument.document_key == item.document_key,
                ProjectDocument.status == DocumentStatus.indexed.value,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if not document:
            return [
                {"text": text, "similarity": None}
                for text in self.bibliography_semantic_evidence(item, query, limit=limit)
            ]

        cosine_distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        rows = self.db.execute(
            select(DocumentChunk.content, (1 - cosine_distance).label("similarity"))
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.embedding.isnot(None),
            )
            .order_by(cosine_distance)
            .limit(limit)
        ).all()

        evidence: list[dict[str, Any]] = []
        seen: set[str] = set()
        for content, similarity in rows:
            text = " ".join((content or "").split())
            if not text or text in seen:
                continue
            seen.add(text)
            evidence.append({
                "text": text[:420],
                "similarity": round(float(similarity), 4) if similarity is not None else None,
            })
        if evidence:
            evidence.sort(
                key=lambda entry: entry["similarity"] if entry["similarity"] is not None else -1,
                reverse=True,
            )
            return evidence
        return [
            {"text": text, "similarity": None}
            for text in self.bibliography_semantic_evidence(item, query, limit=limit)
        ]

    # ── bibliography notes ──────────────────────────────────────────

    def list_bibliography_notes(
        self,
        bibliography_reference_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[tuple[BibliographyNote, str]]:
        """Return notes visible to the user, with author display_name."""
        stmt = (
            select(BibliographyNote, UserAccount.display_name)
            .join(UserAccount, BibliographyNote.user_id == UserAccount.id)
            .where(
                BibliographyNote.bibliography_reference_id == bibliography_reference_id,
                (BibliographyNote.visibility == BibliographyVisibility.shared)
                | (BibliographyNote.user_id == user_id),
            )
            .order_by(BibliographyNote.created_at.desc())
        )
        return list(self.db.execute(stmt).all())

    def create_bibliography_note(
        self,
        bibliography_reference_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        content: str,
        note_type: str = "comment",
        visibility: str = "shared",
    ) -> BibliographyNote:
        item = BibliographyNote(
            bibliography_reference_id=bibliography_reference_id,
            user_id=user_id,
            content=content.strip(),
            note_type=note_type,
            visibility=self._bibliography_visibility(visibility),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def extract_bibliography_abstract(self, bibliography_reference_id: uuid.UUID) -> BibliographyReference:
        item = self.get_bibliography_reference(bibliography_reference_id)

        file_path: Path | None = None
        if item.document_key and item.source_project_id:
            document = self.db.scalar(
                select(ProjectDocument)
                .where(
                    ProjectDocument.project_id == item.source_project_id,
                    ProjectDocument.document_key == item.document_key,
                )
                .order_by(ProjectDocument.version.desc())
                .limit(1)
            )
            if document and document.storage_uri:
                file_path = Path(document.storage_uri)
        if file_path is None and item.attachment_path:
            file_path = Path(item.attachment_path)

        if file_path is None or not file_path.exists():
            raise ValidationError("No PDF available to extract abstract.")

        abstract = extract_pdf_abstract(file_path, max_pages=2)
        if not abstract:
            self.db.refresh(item)
            return item

        item.abstract = abstract
        self.db.commit()
        self.db.refresh(item)
        return item

    def set_bibliography_reference_concepts(
        self,
        bibliography_reference_id: uuid.UUID,
        labels: list[str],
    ) -> BibliographyReference:
        item = self.get_bibliography_reference(bibliography_reference_id)
        self._set_bibliography_reference_concepts(item.id, labels)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_bibliography_note(
        self,
        note_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        content: str | None = None,
        note_type: str | None = None,
        visibility: str | None = None,
    ) -> BibliographyNote:
        item = self.db.get(BibliographyNote, note_id)
        if not item:
            raise NotFoundError("Note not found.")
        if item.user_id != user_id:
            raise ValidationError("You can only edit your own notes.")
        if content is not None:
            item.content = content.strip()
        if note_type is not None:
            item.note_type = note_type
        if visibility is not None:
            item.visibility = self._bibliography_visibility(visibility)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_bibliography_note(self, note_id: uuid.UUID, user_id: uuid.UUID) -> None:
        item = self.db.get(BibliographyNote, note_id)
        if not item:
            raise NotFoundError("Note not found.")
        if item.user_id != user_id:
            raise ValidationError("You can only delete your own notes.")
        self.db.delete(item)
        self.db.commit()

    def bibliography_note_count(self, bibliography_reference_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.count()).where(BibliographyNote.bibliography_reference_id == bibliography_reference_id)
            ) or 0
        )

    def bibliography_note_counts(self, reference_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not reference_ids:
            return {}
        rows = self.db.execute(
            select(BibliographyNote.bibliography_reference_id, func.count())
            .where(BibliographyNote.bibliography_reference_id.in_(reference_ids))
            .group_by(BibliographyNote.bibliography_reference_id)
        ).all()
        return {row[0]: row[1] for row in rows}

    # ── bibliography reading status ───────────────────────────────────

    def get_bibliography_reading_status(
        self, bibliography_reference_id: uuid.UUID, user_id: uuid.UUID
    ) -> str:
        item = self.db.get(BibliographyUserStatus, (user_id, bibliography_reference_id))
        return item.reading_status if item else "unread"

    def set_bibliography_reading_status(
        self, bibliography_reference_id: uuid.UUID, user_id: uuid.UUID, status: str
    ) -> str:
        valid = ("unread", "reading", "read", "reviewed")
        if status not in valid:
            raise ValidationError(f"Invalid reading status. Must be one of: {', '.join(valid)}")
        item = self.db.get(BibliographyUserStatus, (user_id, bibliography_reference_id))
        if item:
            item.reading_status = status
        else:
            item = BibliographyUserStatus(
                user_id=user_id,
                bibliography_reference_id=bibliography_reference_id,
                reading_status=status,
            )
            self.db.add(item)
        self.db.commit()
        return status

    def get_bibliography_reading_statuses(
        self, user_id: uuid.UUID, reference_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """Get reading statuses for multiple references in one query."""
        if not reference_ids:
            return {}
        rows = self.db.execute(
            select(BibliographyUserStatus.bibliography_reference_id, BibliographyUserStatus.reading_status)
            .where(
                BibliographyUserStatus.user_id == user_id,
                BibliographyUserStatus.bibliography_reference_id.in_(reference_ids),
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    # ══════════════════════════════════════════════════════════════════
    # Notes
    # ══════════════════════════════════════════════════════════════════

    def list_notes(
        self,
        project_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None = None,
        note_type: str | None = None,
        author_member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchNote], int]:
        self._get_project(project_id)
        stmt = select(ResearchNote).where(ResearchNote.project_id == project_id)
        if collection_id:
            stmt = stmt.where(ResearchNote.collection_id == collection_id)
        if note_type:
            stmt = stmt.where(ResearchNote.note_type == note_type)
        if author_member_id:
            stmt = stmt.where(ResearchNote.author_member_id == author_member_id)
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ResearchNote.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def get_note(self, project_id: uuid.UUID, note_id: uuid.UUID) -> ResearchNote:
        item = self.db.scalar(
            select(ResearchNote).where(
                ResearchNote.project_id == project_id,
                ResearchNote.id == note_id,
            )
        )
        if not item:
            raise NotFoundError("Note not found.")
        return item

    def create_note(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        content: str,
        collection_id: uuid.UUID | None = None,
        note_type: str = "observation",
        tags: list[str] | None = None,
        author_member_id: uuid.UUID | None = None,
        linked_reference_ids: list[str] | None = None,
    ) -> ResearchNote:
        self._get_project(project_id)
        item = ResearchNote(
            project_id=project_id,
            title=title[:255].strip(),
            content=content.strip(),
            collection_id=collection_id,
            note_type=self._note_type(note_type),
            tags=tags or [],
            author_member_id=author_member_id,
        )
        self.db.add(item)
        self.db.flush()
        if linked_reference_ids:
            for rid in linked_reference_ids:
                self.db.execute(
                    insert(research_note_references).values(note_id=item.id, reference_id=uuid.UUID(rid))
                )
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_note(
        self,
        project_id: uuid.UUID,
        note_id: uuid.UUID,
        *,
        title: str | None = None,
        content: str | None = None,
        collection_id: str | None = None,
        note_type: str | None = None,
        tags: list[str] | None = None,
    ) -> ResearchNote:
        item = self.get_note(project_id, note_id)
        if title is not None:
            item.title = title[:255].strip()
        if content is not None:
            item.content = content.strip()
        if collection_id is not None:
            item.collection_id = uuid.UUID(collection_id) if collection_id else None
        if note_type is not None:
            item.note_type = self._note_type(note_type)
        if tags is not None:
            item.tags = tags
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_note(self, project_id: uuid.UUID, note_id: uuid.UUID) -> None:
        item = self.get_note(project_id, note_id)
        self.db.delete(item)
        self.db.commit()

    def set_note_references(
        self,
        project_id: uuid.UUID,
        note_id: uuid.UUID,
        *,
        reference_ids: list[str],
    ) -> ResearchNote:
        item = self.get_note(project_id, note_id)
        self.db.execute(delete(research_note_references).where(research_note_references.c.note_id == item.id))
        for rid in reference_ids:
            self.db.execute(
                insert(research_note_references).values(note_id=item.id, reference_id=uuid.UUID(rid))
            )
        self.db.commit()
        self.db.refresh(item)
        return item

    def get_note_reference_ids(self, note_id: uuid.UUID) -> list[str]:
        rows = self.db.execute(
            select(research_note_references.c.reference_id).where(research_note_references.c.note_id == note_id)
        ).all()
        return [str(r[0]) for r in rows]

    def get_author_name(self, member_id: uuid.UUID | None) -> str | None:
        if not member_id:
            return None
        row = self.db.scalar(select(TeamMember.full_name).where(TeamMember.id == member_id))
        return row
    def bibliography_document_status(self, bibliography_reference_id: uuid.UUID) -> str | None:
        item = self.get_bibliography_reference(bibliography_reference_id)
        if item.document_key is None or item.source_project_id is None:
            if item.attachment_path or item.attachment_filename:
                return "pending"
            return "no_pdf"
        document = self.db.scalar(
            select(ProjectDocument.status)
            .where(
                ProjectDocument.project_id == item.source_project_id,
                ProjectDocument.document_key == item.document_key,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        return str(document) if document else "pending"

    def bibliography_ingestion_warning(self, bibliography_reference_id: uuid.UUID) -> str | None:
        item = self.get_bibliography_reference(bibliography_reference_id)
        has_attachment = bool(item.document_key or item.attachment_path or item.attachment_filename)
        if has_attachment and not item.abstract:
            return "Failed to automatically extract the abstract. Please manually add the abstract."
        return None
