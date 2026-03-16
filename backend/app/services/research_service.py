"""Research workspace CRUD service."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.meeting import MeetingRecord
from app.models.organization import PartnerOrganization, TeamMember
from app.models.project import Project
from app.models.research import (
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
    research_collection_deliverables,
    research_collection_meetings,
    research_collection_tasks,
    research_collection_wps,
    research_note_references,
)
from app.services.onboarding_service import NotFoundError, ValidationError


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
        added_by_member_id: uuid.UUID | None = None,
    ) -> ResearchReference:
        self._get_project(project_id)
        item = ResearchReference(
            project_id=project_id,
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
