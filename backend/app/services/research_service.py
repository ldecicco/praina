"""Research workspace CRUD service."""

from __future__ import annotations

import re
import uuid
import io
from xml.etree import ElementTree as ET
from pathlib import Path
from datetime import date
from typing import BinaryIO
from urllib.parse import quote

import logging
import httpx

from sqlalchemy import Text, cast, delete, func, insert, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.meeting import MeetingRecord
from app.models.auth import UserAccount
from app.models.collaboration_chat import (
    ProjectChatRoom,
    ProjectChatRoomMember,
    ResearchStudyChatMessage,
    ResearchStudyChatMessageReaction,
)
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
    ResearchStudyFile,
    ResearchSpace,
    ResearchNote,
    ResearchReference,
    bibliography_collection_references,
    bibliography_reference_concepts,
    bibliography_reference_tags,
    research_collection_deliverables,
    research_collection_meetings,
    research_collection_spaces,
    research_collection_tasks,
    research_collection_wps,
    research_note_references,
    research_note_files,
)
from app.models.teaching import TeachingProjectBackgroundMaterial
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.auth_service import AuthService
from app.services.document_service import DocumentService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.scoped_chat_service import ScopedChatService
from app.services.text_extraction import extract_pdf_abstract
from app.schemas.document import DocumentUploadPayload

logger = logging.getLogger(__name__)
ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
GLOBAL_RESEARCH_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
UNSET = object()


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
        self.scoped = ScopedChatService(db)

    # ── helpers ────────────────────────────────────────────────────────

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _can_access_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        try:
            AuthService(self.db)._get_project_role(project_id, user_id)
        except Exception:
            return False
        return True

    def get_user_display_name(self, user_id: uuid.UUID) -> str:
        user = self.db.get(UserAccount, user_id)
        return user.display_name if user else "Unknown"

    def _space_linked_project_id(self, space_id: uuid.UUID) -> uuid.UUID | None:
        item = self.db.get(ResearchSpace, space_id)
        if not item:
            raise NotFoundError("Research space not found.")
        return item.linked_project_id

    def discover_research_users(
        self,
        actor_user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> tuple[list[UserAccount], int]:
        from app.services.auth_service import AuthService

        return AuthService(self.db).discover_users(actor_user_id, page, page_size, search=search)

    def get_research_space(self, space_id: uuid.UUID, actor_user_id: uuid.UUID) -> ResearchSpace:
        item = self.db.get(ResearchSpace, space_id)
        if not item:
            raise NotFoundError("Research space not found.")
        if item.owner_user_id != actor_user_id:
            if not item.linked_project_id or not self._can_access_project(item.linked_project_id, actor_user_id):
                raise ValidationError("Cannot access this research space.")
        return item

    def ensure_collection_chat_room_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
    ) -> ProjectChatRoom:
        collection = self.get_collection_for_space(space_id, collection_id)
        project_id = collection.project_id or self._space_linked_project_id(space_id)
        if project_id and not self._can_access_project(project_id, actor_user_id):
            raise ValidationError("Cannot access this study chat.")
        return self._ensure_collection_chat_room(project_id, collection, actor_user_id=actor_user_id)

    def ensure_collection_chat_room(
        self,
        project_id: uuid.UUID | None,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
    ) -> ProjectChatRoom:
        if not project_id:
            raise ValidationError("Project id is required for project-scoped study chat.")
        collection = self.get_collection(project_id, collection_id)
        if not self._can_access_project(project_id, actor_user_id):
            raise ValidationError("Cannot access this study chat.")
        return self._ensure_collection_chat_room(project_id, collection, actor_user_id=actor_user_id)

    def _ensure_collection_chat_room(
        self,
        project_id: uuid.UUID | None,
        collection: ResearchCollection,
        *,
        actor_user_id: uuid.UUID,
    ) -> ProjectChatRoom:
        allowed_user_ids = self._collection_chat_user_ids(collection.id)
        if not allowed_user_ids:
            raise ValidationError("Add study members with linked user accounts first.")
        if actor_user_id not in allowed_user_ids:
            raise ValidationError("Only study members can access this study chat.")

        room = self.db.scalar(
            select(ProjectChatRoom).where(
                ProjectChatRoom.project_id == project_id,
                ProjectChatRoom.scope_type == "research_collection",
                ProjectChatRoom.scope_ref_id == collection.id,
                ProjectChatRoom.is_archived.is_(False),
            )
        )
        if not room:
            base_name = f"Study · {collection.title.strip() or 'Untitled'}"
            safe_name = base_name[:110].rstrip()
            room = ProjectChatRoom(
                project_id=project_id,
                name=f"{safe_name} · {str(collection.id)[:8]}",
                description=collection.title.strip() or None,
                scope_type="research_collection",
                scope_ref_id=collection.id,
                is_archived=False,
            )
            self.db.add(room)
            self.db.commit()
            self.db.refresh(room)

        existing_user_ids = set(
            self.db.scalars(
                select(ProjectChatRoomMember.user_id).where(ProjectChatRoomMember.thread_id == room.id)
            ).all()
        )
        to_add = allowed_user_ids - existing_user_ids
        to_remove = existing_user_ids - allowed_user_ids
        if to_add:
            self.db.add_all([ProjectChatRoomMember(thread_id=room.id, user_id=user_id) for user_id in sorted(to_add, key=str)])
        if to_remove:
            self.db.execute(
                delete(ProjectChatRoomMember).where(
                    ProjectChatRoomMember.thread_id == room.id,
                    ProjectChatRoomMember.user_id.in_(list(to_remove)),
                )
            )
        if to_add or to_remove:
            self.db.commit()
            self.db.refresh(room)
        return room

    def _collection_chat_user_ids(self, collection_id: uuid.UUID) -> set[uuid.UUID]:
        direct_user_ids = set(
            self.db.scalars(
                select(ResearchCollectionMember.user_account_id).where(
                    ResearchCollectionMember.collection_id == collection_id,
                    ResearchCollectionMember.user_account_id.is_not(None),
                )
            ).all()
        )
        project_linked_user_ids = {
            user_id
            for (user_id,) in self.db.execute(
                select(TeamMember.user_account_id)
                .join(ResearchCollectionMember, ResearchCollectionMember.member_id == TeamMember.id)
                .where(
                    ResearchCollectionMember.collection_id == collection_id,
                    TeamMember.is_active.is_(True),
                    TeamMember.user_account_id.is_not(None),
                )
            ).all()
            if user_id
        }
        return direct_user_ids | project_linked_user_ids

    def can_access_collection_chat(self, collection_id: uuid.UUID, actor_user_id: uuid.UUID) -> bool:
        return actor_user_id in self._collection_chat_user_ids(collection_id)

    def list_study_chat_messages(
        self,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ResearchStudyChatMessage], int]:
        if not self.can_access_collection_chat(collection_id, actor_user_id):
            raise ValidationError("Only study members can access this chat.")
        collection = self.db.get(ResearchCollection, collection_id)
        if not collection:
            raise NotFoundError("Study not found.")
        room = self._ensure_collection_chat_room(collection.project_id, collection, actor_user_id=actor_user_id)
        return self.scoped.list_messages(
            ResearchStudyChatMessage,
            scope_field="thread_id",
            scope_id=room.id,
            page=page,
            page_size=page_size,
        )

    def create_study_chat_message(
        self,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        content: str,
        reply_to_message_id: uuid.UUID | None = None,
    ) -> ResearchStudyChatMessage:
        if not self.can_access_collection_chat(collection_id, actor_user_id):
            raise ValidationError("Only study members can write in this chat.")
        collection = self.db.get(ResearchCollection, collection_id)
        if not collection:
            raise NotFoundError("Study not found.")
        room = self._ensure_collection_chat_room(collection.project_id, collection, actor_user_id=actor_user_id)
        return self.scoped.create_message(
            ResearchStudyChatMessage,
            scope_field="thread_id",
            scope_id=room.id,
            sender_user_id=actor_user_id,
            content=content,
            reply_to_message_id=reply_to_message_id,
        )

    def toggle_study_chat_reaction(
        self,
        collection_id: uuid.UUID,
        message_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        emoji: str,
    ) -> ResearchStudyChatMessage:
        if not self.can_access_collection_chat(collection_id, actor_user_id):
            raise ValidationError("Only study members can react in this chat.")
        collection = self.db.get(ResearchCollection, collection_id)
        if not collection:
            raise NotFoundError("Study not found.")
        room = self._ensure_collection_chat_room(collection.project_id, collection, actor_user_id=actor_user_id)
        return self.scoped.toggle_reaction(
            ResearchStudyChatMessage,
            ResearchStudyChatMessageReaction,
            scope_field="thread_id",
            scope_id=room.id,
            message_id=message_id,
            actor_user_id=actor_user_id,
            emoji=emoji,
        )

    def study_chat_message_lookup(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, ResearchStudyChatMessage]:
        return self.scoped.message_lookup(ResearchStudyChatMessage, message_ids)

    def study_chat_reaction_summary_by_message(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
        return self.scoped.reaction_summary_by_message(ResearchStudyChatMessageReaction, message_ids)

    def list_research_spaces(
        self,
        actor_user_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[ResearchSpace], int]:
        rows = list(
            self.db.scalars(
                select(ResearchSpace)
                .order_by(ResearchSpace.updated_at.desc(), ResearchSpace.created_at.desc())
            ).all()
        )
        visible = [
            item for item in rows
            if item.owner_user_id == actor_user_id
            or (item.linked_project_id and self._can_access_project(item.linked_project_id, actor_user_id))
        ]
        total = len(visible)
        start = max(0, (page - 1) * page_size)
        return visible[start:start + page_size], total

    def create_research_space(
        self,
        *,
        actor_user_id: uuid.UUID,
        title: str,
        focus: str | None = None,
        linked_project_id: uuid.UUID | None = None,
    ) -> ResearchSpace:
        if linked_project_id is not None:
            self._get_project(linked_project_id)
            if not self._can_access_project(linked_project_id, actor_user_id):
                raise ValidationError("Cannot link this research space to the selected project.")
        item = ResearchSpace(
            title=title.strip(),
            focus=(focus or "").strip() or None,
            linked_project_id=linked_project_id,
            owner_user_id=actor_user_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _get_space_record(self, space_id: uuid.UUID) -> ResearchSpace:
        item = self.db.get(ResearchSpace, space_id)
        if not item:
            raise NotFoundError("Research space not found.")
        return item

    def _get_space_project_id(self, space_id: uuid.UUID) -> uuid.UUID | None:
        return self._get_space_record(space_id).linked_project_id

    def _require_space_project_id(self, space_id: uuid.UUID) -> uuid.UUID:
        project_id = self._get_space_project_id(space_id)
        if not project_id:
            raise ValidationError("Research space is not linked to a project.")
        return project_id

    def _space_member_id(self, space_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID | None:
        project_id = self._get_space_project_id(space_id)
        if not project_id:
            return None
        return self.db.scalar(
            select(TeamMember.id).where(
                TeamMember.user_account_id == user_id,
                TeamMember.project_id == project_id,
                TeamMember.is_active.is_(True),
            )
        )

    def collection_space_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            self.db.scalars(
                select(research_collection_spaces.c.space_id)
                .where(research_collection_spaces.c.collection_id == collection_id)
                .order_by(cast(research_collection_spaces.c.space_id, Text))
            ).all()
        )

    def _set_collection_spaces(self, collection_id: uuid.UUID, space_ids: list[uuid.UUID] | None) -> list[uuid.UUID]:
        normalized: list[uuid.UUID] = []
        seen: set[uuid.UUID] = set()
        for space_id in space_ids or []:
            if space_id in seen:
                continue
            self._get_space_record(space_id)
            normalized.append(space_id)
            seen.add(space_id)
        self.db.execute(
            delete(research_collection_spaces).where(research_collection_spaces.c.collection_id == collection_id)
        )
        for space_id in normalized:
            self.db.execute(
                insert(research_collection_spaces).values(collection_id=collection_id, space_id=space_id)
            )
        item = self.db.get(ResearchCollection, collection_id)
        if item:
            item.research_space_id = normalized[0] if normalized else None
        return normalized

    def get_collection_any(self, collection_id: uuid.UUID) -> ResearchCollection:
        item = self.db.get(ResearchCollection, collection_id)
        if not item:
            raise NotFoundError("Collection not found.")
        return item

    def _study_files_root(self) -> Path:
        return Path(settings.documents_storage_path) / "research-study-files"

    def _study_file_storage_path(self, collection_id: uuid.UUID, file_id: uuid.UUID, file_name: str) -> Path:
        safe_name = Path(file_name).name or "file.bin"
        target_dir = self._study_files_root() / str(collection_id) / str(file_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / safe_name

    def _write_study_file(self, file_stream: BinaryIO, storage_path: Path) -> int:
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with storage_path.open("wb") as output:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                total += len(chunk)
        return total

    def update_research_space(
        self,
        space_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        *,
        title: str | None = None,
        focus: str | None = None,
        linked_project_id: uuid.UUID | None | object = ...,
    ) -> ResearchSpace:
        item = self.get_research_space(space_id, actor_user_id)
        if item.owner_user_id != actor_user_id:
            raise ValidationError("Only the owner can edit this research space.")
        if title is not None:
            value = title.strip()
            if not value:
                raise ValidationError("Research space title cannot be empty.")
            item.title = value
        if focus is not None:
            item.focus = (focus or "").strip() or None
        if linked_project_id is not ...:
            if linked_project_id is not None:
                self._get_project(linked_project_id)
                if not self._can_access_project(linked_project_id, actor_user_id):
                    raise ValidationError("Cannot link this research space to the selected project.")
            item.linked_project_id = linked_project_id
        self.db.commit()
        self.db.refresh(item)
        return item

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

    @staticmethod
    def _note_lane(value: str | None) -> str | None:
        raw = " ".join(str(value or "").strip().lower().split())
        if not raw:
            return None
        slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
        return slug[:32] or None

    @staticmethod
    def _paper_question_items(items: list[dict] | None, note_ids: set[str]) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            note_refs = [str(item) for item in (raw.get("note_ids") or []) if str(item) in note_ids]
            normalized.append({
                "id": str(raw.get("id") or uuid.uuid4()),
                "text": text[:1000],
                "note_ids": note_refs,
            })
        return normalized

    # ── space-scoped collections ─────────────────────────────────────

    def list_collections_for_space(
        self,
        space_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ResearchCollection], int]:
        self._get_space_record(space_id)
        stmt = (
            select(ResearchCollection)
            .join(
                research_collection_spaces,
                research_collection_spaces.c.collection_id == ResearchCollection.id,
            )
            .where(research_collection_spaces.c.space_id == space_id)
        )
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

    def get_collection_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID) -> ResearchCollection:
        item = self.db.scalar(
            select(ResearchCollection)
            .join(
                research_collection_spaces,
                research_collection_spaces.c.collection_id == ResearchCollection.id,
            )
            .where(
                research_collection_spaces.c.space_id == space_id,
                ResearchCollection.id == collection_id,
            )
        )
        if not item:
            raise NotFoundError("Collection not found.")
        return item

    def create_collection_for_space(
        self,
        space_id: uuid.UUID,
        **kwargs,
    ) -> ResearchCollection:
        requested_space_ids = [space_id]
        for extra_space_id in kwargs.pop("space_ids", []) or []:
            extra_uuid = uuid.UUID(str(extra_space_id))
            if extra_uuid != space_id:
                requested_space_ids.append(extra_uuid)
        project_id = self._get_space_project_id(space_id)
        return self.create_collection(
            project_id,
            space_ids=requested_space_ids,
            **kwargs,
        ) if project_id else self._create_collection_without_project(
            space_ids=requested_space_ids,
            **kwargs,
        )

    def _create_collection_without_project(self, **kwargs) -> ResearchCollection:
        raw_space_ids = kwargs.get("space_ids") or []
        space_ids = [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in raw_space_ids]
        authors, questions, claims, sections, results = self._normalize_paper_workspace(
            study_results=kwargs.get("study_results"),
            paper_authors=kwargs.get("paper_authors"),
            paper_questions=kwargs.get("paper_questions"),
            paper_claims=kwargs.get("paper_claims"),
            paper_sections=kwargs.get("paper_sections"),
            member_ids=set(),
            reference_ids=set(),
            note_ids=set(),
            file_ids=set(),
        )
        iterations = self._study_iteration_items(kwargs.get("study_iterations"), set(), set(), set(), {str(item["id"]) for item in results})
        item = ResearchCollection(
            project_id=None,
            research_space_id=space_ids[0] if space_ids else None,
            title=kwargs["title"][:255].strip(),
            description=(kwargs.get("description") or "").strip() or None,
            hypothesis=(kwargs.get("hypothesis") or "").strip() or None,
            open_questions=[item.strip() for item in (kwargs.get("open_questions") or []) if item and item.strip()],
            status=self._collection_status(kwargs.get("status") or "active"),
            tags=kwargs.get("tags") or [],
            overleaf_url=(kwargs.get("overleaf_url") or "").strip() or None,
            paper_motivation=(kwargs.get("paper_motivation") or "").strip() or None,
            target_output_title=(kwargs.get("target_output_title") or "").strip() or None,
            target_venue=(kwargs.get("target_venue") or "").strip() or None,
            registration_deadline=kwargs.get("registration_deadline"),
            submission_deadline=kwargs.get("submission_deadline"),
            decision_date=kwargs.get("decision_date"),
            study_iterations=iterations,
            study_results=results,
            paper_authors=authors,
            paper_questions=questions,
            paper_claims=claims,
            paper_sections=sections,
            output_status=self._output_status(kwargs.get("output_status") or "not_started"),
            created_by_member_id=kwargs.get("created_by_member_id"),
        )
        self.db.add(item)
        self.db.flush()
        self._set_collection_spaces(item.id, space_ids)
        creator_user_id = kwargs.get("creator_user_id")
        if creator_user_id:
            self.db.add(
                ResearchCollectionMember(
                    collection_id=item.id,
                    user_account_id=creator_user_id,
                    role=CollectionMemberRole.lead,
                )
            )
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_collection_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID, **kwargs) -> ResearchCollection:
        self.get_collection_for_space(space_id, collection_id)
        requested_space_ids = [space_id]
        if kwargs.get("space_ids") is not None:
            requested_space_ids = [space_id]
            for extra_space_id in kwargs.get("space_ids") or []:
                extra_uuid = extra_space_id if isinstance(extra_space_id, uuid.UUID) else uuid.UUID(str(extra_space_id))
                if extra_uuid != space_id:
                    requested_space_ids.append(extra_uuid)
            kwargs["space_ids"] = requested_space_ids
        project_id = self._get_space_project_id(space_id)
        if project_id:
            return self.update_collection(project_id, collection_id, **kwargs)
        return self._update_collection_without_project(collection_id, **kwargs)

    def _update_collection_without_project(self, collection_id: uuid.UUID, **kwargs) -> ResearchCollection:
        item = self.db.get(ResearchCollection, collection_id)
        if not item:
            raise NotFoundError("Collection not found.")
        # Delegate to existing normalization logic by temporarily using the projectless item path.
        if "title" in kwargs and kwargs["title"] is not None:
            item.title = kwargs["title"][:255].strip()
        if "description" in kwargs and kwargs["description"] is not None:
            item.description = kwargs["description"].strip() or None
        if "hypothesis" in kwargs and kwargs["hypothesis"] is not None:
            item.hypothesis = kwargs["hypothesis"].strip() or None
        if "open_questions" in kwargs and kwargs["open_questions"] is not None:
            item.open_questions = [entry.strip() for entry in kwargs["open_questions"] if entry and entry.strip()]
        if "status" in kwargs and kwargs["status"] is not None:
            item.status = self._collection_status(kwargs["status"])
        if "tags" in kwargs and kwargs["tags"] is not None:
            item.tags = kwargs["tags"]
        if "overleaf_url" in kwargs and kwargs["overleaf_url"] is not None:
            item.overleaf_url = kwargs["overleaf_url"].strip() or None
        if "paper_motivation" in kwargs and kwargs["paper_motivation"] is not None:
            item.paper_motivation = kwargs["paper_motivation"].strip() or None
        if "target_output_title" in kwargs and kwargs["target_output_title"] is not None:
            item.target_output_title = kwargs["target_output_title"].strip() or None
        if "target_venue" in kwargs and kwargs["target_venue"] is not None:
            item.target_venue = kwargs["target_venue"].strip() or None
        if "registration_deadline" in kwargs and kwargs["registration_deadline"] is not None:
            item.registration_deadline = kwargs["registration_deadline"]
        if "submission_deadline" in kwargs and kwargs["submission_deadline"] is not None:
            item.submission_deadline = kwargs["submission_deadline"]
        if "decision_date" in kwargs and kwargs["decision_date"] is not None:
            item.decision_date = kwargs["decision_date"]
        collection_reference_ids = {
            str(ref_id)
            for ref_id in self.db.scalars(select(ResearchReference.id).where(ResearchReference.collection_id == collection_id)).all()
        }
        collection_note_ids = {
            str(note_id)
            for note_id in self.db.scalars(select(ResearchNote.id).where(ResearchNote.collection_id == collection_id)).all()
        }
        collection_file_ids = {
            str(file_id)
            for file_id in self.db.scalars(select(ResearchStudyFile.id).where(ResearchStudyFile.collection_id == collection_id)).all()
        }
        normalized_results = None
        if "study_results" in kwargs and kwargs["study_results"] is not None:
            normalized_results = self._study_result_items(kwargs["study_results"], collection_note_ids, collection_reference_ids, collection_file_ids)
            item.study_results = normalized_results
        if "study_iterations" in kwargs and kwargs["study_iterations"] is not None:
            result_ids = {str(entry.get("id") or "") for entry in (normalized_results if normalized_results is not None else (item.study_results or [])) if isinstance(entry, dict)}
            item.study_iterations = self._study_iteration_items(kwargs["study_iterations"], collection_note_ids, collection_reference_ids, collection_file_ids, result_ids)
        if any(kwargs.get(key) is not None for key in ("study_results", "paper_authors", "paper_questions", "paper_claims", "paper_sections")):
            collection_member_ids = {
                str(member_id)
                for member_id in self.db.scalars(
                    select(ResearchCollectionMember.member_id).where(ResearchCollectionMember.collection_id == collection_id)
                ).all()
            }
            authors, questions, claims, sections, results = self._normalize_paper_workspace(
                study_results=kwargs.get("study_results") if kwargs.get("study_results") is not None else (item.study_results or []),
                paper_authors=kwargs.get("paper_authors") if kwargs.get("paper_authors") is not None else (item.paper_authors or []),
                paper_questions=kwargs.get("paper_questions") if kwargs.get("paper_questions") is not None else (item.paper_questions or []),
                paper_claims=kwargs.get("paper_claims") if kwargs.get("paper_claims") is not None else (item.paper_claims or []),
                paper_sections=kwargs.get("paper_sections") if kwargs.get("paper_sections") is not None else (item.paper_sections or []),
                member_ids=collection_member_ids,
                reference_ids=collection_reference_ids,
                note_ids=collection_note_ids,
                file_ids=collection_file_ids,
            )
            if kwargs.get("study_results") is not None:
                item.study_results = results
            item.paper_authors = authors
            item.paper_questions = questions
            item.paper_claims = claims
            item.paper_sections = sections
        if "output_status" in kwargs and kwargs["output_status"] is not None:
            item.output_status = self._output_status(kwargs["output_status"])
        if "space_ids" in kwargs and kwargs["space_ids"] is not UNSET:
            normalized_space_ids = [
                entry if isinstance(entry, uuid.UUID) else uuid.UUID(str(entry))
                for entry in (kwargs["space_ids"] or [])
            ]
            self._set_collection_spaces(item.id, normalized_space_ids)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_collection_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID) -> None:
        item = self.get_collection_for_space(space_id, collection_id)
        self.db.delete(item)
        self.db.commit()

    @staticmethod
    def _paper_claim_items(
        items: list[dict] | None,
        question_ids: set[str],
        reference_ids: set[str],
        note_ids: set[str],
        result_ids: set[str],
        file_ids: set[str] | None = None,
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            question_refs = [str(item) for item in (raw.get("question_ids") or []) if str(item) in question_ids]
            reference_refs = [str(item) for item in (raw.get("reference_ids") or []) if str(item) in reference_ids]
            note_refs = [str(item) for item in (raw.get("note_ids") or []) if str(item) in note_ids]
            result_refs = [str(item) for item in (raw.get("result_ids") or []) if str(item) in result_ids]
            file_refs = [str(item) for item in (raw.get("file_ids") or []) if str(item) in (file_ids or set())]
            supporting_reference_refs = [str(item) for item in (raw.get("supporting_reference_ids") or []) if str(item) in reference_ids]
            supporting_note_refs = [str(item) for item in (raw.get("supporting_note_ids") or []) if str(item) in note_ids]
            status = str(raw.get("status") or "draft").strip() or "draft"
            audit_status = str(raw.get("audit_status") or "").strip() or None
            audit_summary = str(raw.get("audit_summary") or "").strip() or None
            missing_evidence = [
                str(item).strip()[:255]
                for item in (raw.get("missing_evidence") or [])
                if str(item).strip()
            ]
            audit_confidence = raw.get("audit_confidence")
            try:
                audit_confidence_value = float(audit_confidence) if audit_confidence is not None else None
            except (TypeError, ValueError):
                audit_confidence_value = None
            audited_at_raw = str(raw.get("audited_at") or "").strip()
            normalized.append({
                "id": str(raw.get("id") or uuid.uuid4()),
                "text": text[:1600],
                "question_ids": question_refs,
                "reference_ids": reference_refs,
                "note_ids": note_refs,
                "result_ids": result_refs,
                "file_ids": file_refs,
                "status": status[:64],
                "audit_status": audit_status[:64] if audit_status else None,
                "audit_summary": audit_summary[:4000] if audit_summary else None,
                "supporting_reference_ids": supporting_reference_refs,
                "supporting_note_ids": supporting_note_refs,
                "missing_evidence": missing_evidence,
                "audit_confidence": audit_confidence_value,
                "audited_at": audited_at_raw or None,
            })
        return normalized

    @staticmethod
    def _paper_section_items(
        items: list[dict] | None,
        question_ids: set[str],
        claim_ids: set[str],
        reference_ids: set[str],
        note_ids: set[str],
        result_ids: set[str],
        file_ids: set[str] | None = None,
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            q_refs = [str(item) for item in (raw.get("question_ids") or []) if str(item) in question_ids]
            c_refs = [str(item) for item in (raw.get("claim_ids") or []) if str(item) in claim_ids]
            reference_refs = [str(item) for item in (raw.get("reference_ids") or []) if str(item) in reference_ids]
            note_refs = [str(item) for item in (raw.get("note_ids") or []) if str(item) in note_ids]
            result_refs = [str(item) for item in (raw.get("result_ids") or []) if str(item) in result_ids]
            file_refs = [str(item) for item in (raw.get("file_ids") or []) if str(item) in (file_ids or set())]
            status = str(raw.get("status") or "not_started").strip() or "not_started"
            normalized.append({
                "id": str(raw.get("id") or uuid.uuid4()),
                "title": title[:255],
                "question_ids": q_refs,
                "claim_ids": c_refs,
                "reference_ids": reference_refs,
                "note_ids": note_refs,
                "result_ids": result_refs,
                "file_ids": file_refs,
                "status": status[:64],
            })
        return normalized

    @staticmethod
    def _paper_author_items(
        items: list[dict] | None,
        member_ids: set[str],
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        seen_member_ids: set[str] = set()
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            member_id = str(raw.get("member_id") or "").strip()
            display_name = str(raw.get("display_name") or "").strip()
            if not member_id or member_id not in member_ids or member_id in seen_member_ids:
                continue
            seen_member_ids.add(member_id)
            normalized.append({
                "id": str(raw.get("id") or uuid.uuid4()),
                "member_id": member_id,
                "display_name": display_name[:255] or "Author",
                "is_corresponding": bool(raw.get("is_corresponding")),
            })
        return normalized

    @staticmethod
    def _study_result_items(
        items: list[dict] | None,
        note_ids: set[str],
        reference_ids: set[str],
        file_ids: set[str] | None = None,
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            normalized.append({
                "id": str(raw.get("id") or uuid.uuid4()),
                "iteration_id": str(raw.get("iteration_id") or "").strip() or None,
                "title": title[:255],
                "note_ids": [str(item) for item in (raw.get("note_ids") or []) if str(item) in note_ids],
                "reference_ids": [str(item) for item in (raw.get("reference_ids") or []) if str(item) in reference_ids],
                "file_ids": [str(item) for item in (raw.get("file_ids") or []) if str(item) in (file_ids or set())],
                "summary": str(raw.get("summary") or "").strip()[:4000] or None,
                "what_changed": [str(item).strip()[:400] for item in (raw.get("what_changed") or []) if str(item).strip()],
                "improvements": [str(item).strip()[:400] for item in (raw.get("improvements") or []) if str(item).strip()],
                "regressions": [str(item).strip()[:400] for item in (raw.get("regressions") or []) if str(item).strip()],
                "unclear_points": [str(item).strip()[:400] for item in (raw.get("unclear_points") or []) if str(item).strip()],
                "next_actions": [str(item).strip()[:400] for item in (raw.get("next_actions") or []) if str(item).strip()],
                "user_comments": str(raw.get("user_comments") or "").strip()[:4000] or None,
                "created_at": str(raw.get("created_at") or "").strip() or None,
                "updated_at": str(raw.get("updated_at") or "").strip() or None,
            })
        return normalized

    @staticmethod
    def _study_iteration_items(
        items: list[dict] | None,
        note_ids: set[str],
        reference_ids: set[str],
        file_ids: set[str] | None,
        result_ids: set[str],
    ) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            start_date = raw.get("start_date")
            end_date = raw.get("end_date")
            normalized.append({
                "id": str(raw.get("id") or uuid.uuid4()),
                "title": title[:255],
                "start_date": start_date,
                "end_date": end_date,
                "note_ids": [str(item) for item in (raw.get("note_ids") or []) if str(item) in note_ids],
                "reference_ids": [str(item) for item in (raw.get("reference_ids") or []) if str(item) in reference_ids],
                "file_ids": [str(item) for item in (raw.get("file_ids") or []) if str(item) in (file_ids or set())],
                "result_ids": [str(item) for item in (raw.get("result_ids") or []) if str(item) in result_ids],
                "summary": str(raw.get("summary") or "").strip()[:4000] or None,
                "what_changed": [str(item).strip()[:400] for item in (raw.get("what_changed") or []) if str(item).strip()],
                "improvements": [str(item).strip()[:400] for item in (raw.get("improvements") or []) if str(item).strip()],
                "regressions": [str(item).strip()[:400] for item in (raw.get("regressions") or []) if str(item).strip()],
                "unclear_points": [str(item).strip()[:400] for item in (raw.get("unclear_points") or []) if str(item).strip()],
                "next_actions": [str(item).strip()[:400] for item in (raw.get("next_actions") or []) if str(item).strip()],
                "user_comments": str(raw.get("user_comments") or "").strip()[:4000] or None,
                "reviewed_at": str(raw.get("reviewed_at") or "").strip() or None,
            })
        return normalized

    def _normalize_paper_workspace(
        self,
        *,
        study_results: list[dict] | None = None,
        paper_authors: list[dict] | None = None,
        paper_questions: list[dict] | None = None,
        paper_claims: list[dict] | None = None,
        paper_sections: list[dict] | None = None,
        member_ids: set[str] | None = None,
        reference_ids: set[str] | None = None,
        note_ids: set[str] | None = None,
        file_ids: set[str] | None = None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
        authors = self._paper_author_items(paper_authors, member_ids or set())
        questions = self._paper_question_items(paper_questions, note_ids or set())
        results = self._study_result_items(study_results, note_ids or set(), reference_ids or set(), file_ids or set())
        result_ids = {str(item["id"]) for item in results}
        question_ids = {str(item["id"]) for item in questions}
        claims = self._paper_claim_items(paper_claims, question_ids, reference_ids or set(), note_ids or set(), result_ids, file_ids or set())
        claim_ids = {str(item["id"]) for item in claims}
        sections = self._paper_section_items(paper_sections, question_ids, claim_ids, reference_ids or set(), note_ids or set(), result_ids, file_ids or set())
        return authors, questions, claims, sections, results

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
        project_id: uuid.UUID | None,
        *,
        status_filter: str | None = None,
        member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ResearchCollection], int]:
        stmt = select(ResearchCollection)
        if project_id and project_id != GLOBAL_RESEARCH_PROJECT_ID:
            self._get_project(project_id)
            stmt = stmt.where(ResearchCollection.project_id == project_id)
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
        if project_id == GLOBAL_RESEARCH_PROJECT_ID:
            return self.get_collection_any(collection_id)
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
        project_id: uuid.UUID | None,
        *,
        title: str,
        space_ids: list[uuid.UUID] | None = None,
        description: str | None = None,
        hypothesis: str | None = None,
        open_questions: list[str] | None = None,
        status: str = "active",
        tags: list[str] | None = None,
        overleaf_url: str | None = None,
        paper_motivation: str | None = None,
        target_output_title: str | None = None,
        target_venue: str | None = None,
        registration_deadline: date | None = None,
        submission_deadline: date | None = None,
        decision_date: date | None = None,
        study_iterations: list[dict] | None = None,
        study_results: list[dict] | None = None,
        paper_authors: list[dict] | None = None,
        paper_questions: list[dict] | None = None,
        paper_claims: list[dict] | None = None,
        paper_sections: list[dict] | None = None,
        output_status: str = "not_started",
        created_by_member_id: uuid.UUID | None = None,
        creator_user_id: uuid.UUID | None = None,
    ) -> ResearchCollection:
        if (not project_id or project_id == GLOBAL_RESEARCH_PROJECT_ID) and space_ids:
            linked_project_ids = {
                linked_project_id
                for linked_project_id in (self._get_space_project_id(space_id) for space_id in space_ids)
                if linked_project_id
            }
            if len(linked_project_ids) > 1:
                raise ValidationError("A study cannot span spaces linked to different projects.")
            if linked_project_ids:
                project_id = next(iter(linked_project_ids))
        if not project_id or project_id == GLOBAL_RESEARCH_PROJECT_ID:
            return self._create_collection_without_project(
                title=title,
                space_ids=space_ids,
                description=description,
                hypothesis=hypothesis,
                open_questions=open_questions,
                status=status,
                tags=tags,
                overleaf_url=overleaf_url,
                paper_motivation=paper_motivation,
                target_output_title=target_output_title,
                target_venue=target_venue,
                registration_deadline=registration_deadline,
                submission_deadline=submission_deadline,
                decision_date=decision_date,
                study_iterations=study_iterations,
                study_results=study_results,
                paper_authors=paper_authors,
                paper_questions=paper_questions,
                paper_claims=paper_claims,
                paper_sections=paper_sections,
                output_status=output_status,
                created_by_member_id=created_by_member_id,
                creator_user_id=creator_user_id,
            )
        self._get_project(project_id)
        normalized_space_ids = [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in (space_ids or [])]
        authors, questions, claims, sections, results = self._normalize_paper_workspace(
            study_results=study_results,
            paper_authors=paper_authors,
            paper_questions=paper_questions,
            paper_claims=paper_claims,
            paper_sections=paper_sections,
            member_ids=set(),
            reference_ids=set(),
            note_ids=set(),
            file_ids=set(),
        )
        iterations = self._study_iteration_items(study_iterations, set(), set(), set(), {str(item["id"]) for item in results})
        item = ResearchCollection(
            project_id=project_id,
            research_space_id=normalized_space_ids[0] if normalized_space_ids else None,
            title=title[:255].strip(),
            description=(description or "").strip() or None,
            hypothesis=(hypothesis or "").strip() or None,
            open_questions=[item.strip() for item in (open_questions or []) if item and item.strip()],
            status=self._collection_status(status),
            tags=tags or [],
            overleaf_url=(overleaf_url or "").strip() or None,
            paper_motivation=(paper_motivation or "").strip() or None,
            target_output_title=(target_output_title or "").strip() or None,
            target_venue=(target_venue or "").strip() or None,
            registration_deadline=registration_deadline,
            submission_deadline=submission_deadline,
            decision_date=decision_date,
            study_iterations=iterations,
            study_results=results,
            paper_authors=authors,
            paper_questions=questions,
            paper_claims=claims,
            paper_sections=sections,
            output_status=self._output_status(output_status),
            created_by_member_id=created_by_member_id,
        )
        self.db.add(item)
        self.db.flush()
        self._set_collection_spaces(item.id, normalized_space_ids)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_collection(
        self,
        project_id: uuid.UUID | None,
        collection_id: uuid.UUID,
        *,
        title: str | None = None,
        space_ids: list[uuid.UUID] | object = UNSET,
        description: str | None = None,
        hypothesis: str | None = None,
        open_questions: list[str] | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        overleaf_url: str | None = None,
        paper_motivation: str | None = None,
        target_output_title: str | None = None,
        target_venue: str | None = None,
        registration_deadline: date | None = None,
        submission_deadline: date | None = None,
        decision_date: date | None = None,
        study_iterations: list[dict] | None = None,
        study_results: list[dict] | None = None,
        paper_authors: list[dict] | None = None,
        paper_questions: list[dict] | None = None,
        paper_claims: list[dict] | None = None,
        paper_sections: list[dict] | None = None,
        output_status: str | None = None,
    ) -> ResearchCollection:
        if not project_id or project_id == GLOBAL_RESEARCH_PROJECT_ID:
            return self._update_collection_without_project(
                collection_id,
                title=title,
                space_ids=space_ids,
                description=description,
                hypothesis=hypothesis,
                open_questions=open_questions,
                status=status,
                tags=tags,
                overleaf_url=overleaf_url,
                paper_motivation=paper_motivation,
                target_output_title=target_output_title,
                target_venue=target_venue,
                registration_deadline=registration_deadline,
                submission_deadline=submission_deadline,
                decision_date=decision_date,
                study_iterations=study_iterations,
                study_results=study_results,
                paper_authors=paper_authors,
                paper_questions=paper_questions,
                paper_claims=paper_claims,
                paper_sections=paper_sections,
                output_status=output_status,
            )
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
        if paper_motivation is not None:
            item.paper_motivation = paper_motivation.strip() or None
        if target_output_title is not None:
            item.target_output_title = target_output_title.strip() or None
        if target_venue is not None:
            item.target_venue = target_venue.strip() or None
        if registration_deadline is not None:
            item.registration_deadline = registration_deadline
        if submission_deadline is not None:
            item.submission_deadline = submission_deadline
        if decision_date is not None:
            item.decision_date = decision_date
        collection_reference_ids = {
            str(ref_id)
            for ref_id in self.db.scalars(select(ResearchReference.id).where(ResearchReference.collection_id == collection_id)).all()
        }
        collection_note_ids = {
            str(note_id)
            for note_id in self.db.scalars(select(ResearchNote.id).where(ResearchNote.collection_id == collection_id)).all()
        }
        collection_file_ids = {
            str(file_id)
            for file_id in self.db.scalars(select(ResearchStudyFile.id).where(ResearchStudyFile.collection_id == collection_id)).all()
        }
        normalized_results = None
        if study_results is not None:
            normalized_results = self._study_result_items(study_results, collection_note_ids, collection_reference_ids, collection_file_ids)
            item.study_results = normalized_results
        if study_iterations is not None:
            result_ids = {str(entry.get("id") or "") for entry in (normalized_results if normalized_results is not None else (item.study_results or [])) if isinstance(entry, dict)}
            item.study_iterations = self._study_iteration_items(study_iterations, collection_note_ids, collection_reference_ids, collection_file_ids, result_ids)
        if (
            study_results is not None
            or
            paper_authors is not None
            or
            paper_questions is not None
            or paper_claims is not None
            or paper_sections is not None
        ):
            collection_member_ids = {
                str(item)
                for item in self.db.scalars(
                    select(ResearchCollectionMember.member_id).where(ResearchCollectionMember.collection_id == collection_id)
                ).all()
            }
            authors, questions, claims, sections, results = self._normalize_paper_workspace(
                study_results=study_results if study_results is not None else (item.study_results or []),
                paper_authors=paper_authors if paper_authors is not None else (item.paper_authors or []),
                paper_questions=paper_questions if paper_questions is not None else (item.paper_questions or []),
                paper_claims=paper_claims if paper_claims is not None else (item.paper_claims or []),
                paper_sections=paper_sections if paper_sections is not None else (item.paper_sections or []),
                member_ids=collection_member_ids,
                reference_ids=collection_reference_ids,
                note_ids=collection_note_ids,
                file_ids=collection_file_ids,
            )
            if study_results is not None:
                item.study_results = results
            item.paper_authors = authors
            item.paper_questions = questions
            item.paper_claims = claims
            item.paper_sections = sections
        if output_status is not None:
            item.output_status = self._output_status(output_status)
        if space_ids is not UNSET:
            normalized_space_ids = [
                entry if isinstance(entry, uuid.UUID) else uuid.UUID(str(entry))
                for entry in (space_ids or [])
            ]
            self._set_collection_spaces(item.id, normalized_space_ids)
        self.db.commit()
        self.db.refresh(item)
        return item

    def apply_paper_claim_audits(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        audits: list[dict[str, object]],
    ) -> ResearchCollection:
        item = self.get_collection(project_id, collection_id)
        current_claims = [claim for claim in (item.paper_claims or []) if isinstance(claim, dict)]
        audit_map = {str(audit.get("claim_id") or ""): audit for audit in audits if str(audit.get("claim_id") or "").strip()}
        next_claims: list[dict[str, object]] = []
        for claim in current_claims:
            claim_id = str(claim.get("id") or "")
            audit = audit_map.get(claim_id)
            if not audit:
                next_claims.append(claim)
                continue
            merged = dict(claim)
            merged["audit_status"] = str(audit.get("audit_status") or "").strip() or None
            merged["audit_summary"] = str(audit.get("audit_summary") or "").strip() or None
            merged["supporting_reference_ids"] = [str(item) for item in (audit.get("supporting_reference_ids") or []) if str(item).strip()]
            merged["supporting_note_ids"] = [str(item) for item in (audit.get("supporting_note_ids") or []) if str(item).strip()]
            merged["missing_evidence"] = [str(item) for item in (audit.get("missing_evidence") or []) if str(item).strip()]
            merged["audit_confidence"] = audit.get("audit_confidence")
            merged["audited_at"] = str(audit.get("audited_at") or "").strip() or None
            next_claims.append(merged)
        authors, questions, claims, sections, results = self._normalize_paper_workspace(
            study_results=item.study_results or [],
            paper_authors=item.paper_authors or [],
            paper_questions=item.paper_questions or [],
            paper_claims=next_claims,
            paper_sections=item.paper_sections or [],
            member_ids={
                str(member_id)
                for member_id in self.db.scalars(
                    select(ResearchCollectionMember.member_id).where(ResearchCollectionMember.collection_id == collection_id)
                ).all()
            },
            reference_ids={
                str(ref_id)
                for ref_id in self.db.scalars(select(ResearchReference.id).where(ResearchReference.collection_id == collection_id)).all()
            },
            note_ids={
                str(note_id)
                for note_id in self.db.scalars(select(ResearchNote.id).where(ResearchNote.collection_id == collection_id)).all()
            },
            file_ids={
                str(file_id)
                for file_id in self.db.scalars(select(ResearchStudyFile.id).where(ResearchStudyFile.collection_id == collection_id)).all()
            },
        )
        item.study_results = results
        item.paper_authors = authors
        item.paper_questions = questions
        item.paper_claims = claims
        item.paper_sections = sections
        self.db.commit()
        self.db.refresh(item)
        return item

    def apply_paper_claim_audits_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        audits: list[dict[str, object]],
    ) -> ResearchCollection:
        item = self.get_collection_for_space(space_id, collection_id)
        current_claims = [claim for claim in (item.paper_claims or []) if isinstance(claim, dict)]
        audit_map = {str(audit.get("claim_id") or ""): audit for audit in audits if str(audit.get("claim_id") or "").strip()}
        next_claims: list[dict[str, object]] = []
        for claim in current_claims:
            claim_id = str(claim.get("id") or "")
            audit = audit_map.get(claim_id)
            if not audit:
                next_claims.append(claim)
                continue
            merged = dict(claim)
            merged["audit_status"] = str(audit.get("audit_status") or "").strip() or None
            merged["audit_summary"] = str(audit.get("audit_summary") or "").strip() or None
            merged["supporting_reference_ids"] = [str(item) for item in (audit.get("supporting_reference_ids") or []) if str(item).strip()]
            merged["supporting_note_ids"] = [str(item) for item in (audit.get("supporting_note_ids") or []) if str(item).strip()]
            merged["missing_evidence"] = [str(item) for item in (audit.get("missing_evidence") or []) if str(item).strip()]
            merged["audit_confidence"] = audit.get("audit_confidence")
            merged["audited_at"] = str(audit.get("audited_at") or "").strip() or None
            next_claims.append(merged)
        authors, questions, claims, sections, results = self._normalize_paper_workspace(
            study_results=item.study_results or [],
            paper_authors=item.paper_authors or [],
            paper_questions=item.paper_questions or [],
            paper_claims=next_claims,
            paper_sections=item.paper_sections or [],
            member_ids={
                str(member_id)
                for member_id in self.db.scalars(
                    select(ResearchCollectionMember.member_id).where(ResearchCollectionMember.collection_id == collection_id)
                ).all()
            },
            reference_ids={
                str(ref_id)
                for ref_id in self.db.scalars(select(ResearchReference.id).where(ResearchReference.collection_id == collection_id)).all()
            },
            note_ids={
                str(note_id)
                for note_id in self.db.scalars(select(ResearchNote.id).where(ResearchNote.collection_id == collection_id)).all()
            },
            file_ids={
                str(file_id)
                for file_id in self.db.scalars(select(ResearchStudyFile.id).where(ResearchStudyFile.collection_id == collection_id)).all()
            },
        )
        item.study_results = results
        item.paper_authors = authors
        item.paper_questions = questions
        item.paper_claims = claims
        item.paper_sections = sections
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_collection(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> None:
        if project_id == GLOBAL_RESEARCH_PROJECT_ID:
            item = self.get_collection_any(collection_id)
            self.db.delete(item)
            self.db.commit()
            return
        item = self.get_collection(project_id, collection_id)
        self.db.delete(item)
        self.db.commit()

    # ── collection members ─────────────────────────────────────────────

    def list_collection_members(self, project_id: uuid.UUID | None, collection_id: uuid.UUID) -> list[dict]:
        if project_id:
            self.get_collection(project_id, collection_id)
        else:
            self.get_collection_any(collection_id)
        return self._list_collection_members_common(collection_id)

    def list_collection_members_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID) -> list[dict]:
        self.get_collection_for_space(space_id, collection_id)
        return self._list_collection_members_common(collection_id)

    def _list_collection_members_common(self, collection_id: uuid.UUID) -> list[dict]:
        rows = self.db.scalars(
            select(ResearchCollectionMember)
            .where(ResearchCollectionMember.collection_id == collection_id)
            .order_by(ResearchCollectionMember.created_at)
        ).all()
        items: list[dict] = []
        for cm in rows:
            if cm.user_account_id:
                user = self.db.get(UserAccount, cm.user_account_id)
                items.append(
                    {
                        "item": cm,
                        "member_name": user.display_name if user else "",
                        "organization_short_name": (user.organization or "") if user else "",
                    }
                )
                continue
            if cm.member_id:
                row = self.db.execute(
                    select(TeamMember.full_name, PartnerOrganization.short_name)
                    .join(PartnerOrganization, TeamMember.organization_id == PartnerOrganization.id)
                    .where(TeamMember.id == cm.member_id)
                ).one_or_none()
                items.append(
                    {
                        "item": cm,
                        "member_name": row[0] if row else "",
                        "organization_short_name": row[1] if row else "",
                    }
                )
                continue
            items.append({"item": cm, "member_name": "", "organization_short_name": ""})
        return items

    def add_collection_member(
        self,
        project_id: uuid.UUID | None,
        collection_id: uuid.UUID,
        *,
        member_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        role: str = "contributor",
    ) -> dict:
        if project_id:
            self.get_collection(project_id, collection_id)
        else:
            collection = self.db.get(ResearchCollection, collection_id)
            if not collection:
                raise NotFoundError("Collection not found.")
        if not member_id and not user_id:
            raise ValidationError("Provide a member or user.")
        if member_id and user_id:
            raise ValidationError("Choose either a member or a user.")
        if member_id:
            existing = self.db.scalar(
                select(ResearchCollectionMember).where(
                    ResearchCollectionMember.collection_id == collection_id,
                    ResearchCollectionMember.member_id == member_id,
                )
            )
        else:
            existing = self.db.scalar(
                select(ResearchCollectionMember).where(
                    ResearchCollectionMember.collection_id == collection_id,
                    ResearchCollectionMember.user_account_id == user_id,
                )
            )
        if existing:
            raise ValidationError("Member already in collection.")
        cm = ResearchCollectionMember(
            collection_id=collection_id,
            member_id=member_id,
            user_account_id=user_id,
            role=self._member_role(role),
        )
        self.db.add(cm)
        self.db.commit()
        self.db.refresh(cm)
        return self._list_collection_members_common(collection_id)[-1]

    def add_collection_member_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        member_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        role: str = "contributor",
    ) -> dict:
        self.get_collection_for_space(space_id, collection_id)
        project_id = self._space_linked_project_id(space_id)
        if user_id:
            item = self.db.get(UserAccount, user_id)
            if not item or not item.can_access_research:
                raise ValidationError("User cannot be added to Research.")
            return self.add_collection_member(project_id, collection_id, user_id=user_id, role=role)
        if not project_id:
            raise ValidationError("Project-linked members require a linked project.")
        return self.add_collection_member(project_id, collection_id, member_id=member_id, role=role)

    def update_collection_member_role(
        self,
        project_id: uuid.UUID | None,
        collection_id: uuid.UUID,
        member_record_id: uuid.UUID,
        *,
        role: str,
    ) -> dict:
        if project_id:
            self.get_collection(project_id, collection_id)
        else:
            self.get_collection_any(collection_id)
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
        if cm.user_account_id:
            user = self.db.get(UserAccount, cm.user_account_id)
            return {
                "item": cm,
                "member_name": user.display_name if user else "",
                "organization_short_name": (user.organization or "") if user else "",
            }
        return {
            "item": cm,
            "member_name": row[0] if row else "",
            "organization_short_name": row[1] if row else "",
        }

    def update_collection_member_role_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        member_record_id: uuid.UUID,
        *,
        role: str,
    ) -> dict:
        self.get_collection_for_space(space_id, collection_id)
        return self.update_collection_member_role(self._get_space_project_id(space_id), collection_id, member_record_id, role=role)

    def remove_collection_member(
        self,
        project_id: uuid.UUID | None,
        collection_id: uuid.UUID,
        member_record_id: uuid.UUID,
    ) -> None:
        if project_id:
            self.get_collection(project_id, collection_id)
        else:
            self.get_collection_any(collection_id)
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

    def remove_collection_member_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID, member_record_id: uuid.UUID) -> None:
        self.get_collection_for_space(space_id, collection_id)
        self.remove_collection_member(self._get_space_project_id(space_id), collection_id, member_record_id)

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

    def set_wbs_links_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        wp_ids: list[str],
        task_ids: list[str],
        deliverable_ids: list[str],
    ) -> dict:
        project_id = self._require_space_project_id(space_id)
        self.get_collection_for_space(space_id, collection_id)
        return self.set_wbs_links(project_id, collection_id, wp_ids=wp_ids, task_ids=task_ids, deliverable_ids=deliverable_ids)

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

    def get_wbs_links_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID) -> dict:
        self.get_collection_for_space(space_id, collection_id)
        project_id = self._get_space_project_id(space_id)
        if not project_id:
            return {"wp_ids": [], "task_ids": [], "deliverable_ids": []}
        return self.get_wbs_links(project_id, collection_id)

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

    def list_collection_meetings_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID) -> list[MeetingRecord]:
        self.get_collection_for_space(space_id, collection_id)
        project_id = self._get_space_project_id(space_id)
        if not project_id:
            return []
        return self.list_collection_meetings(project_id, collection_id)

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

    def set_collection_meetings_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        meeting_ids: list[str],
    ) -> list[MeetingRecord]:
        project_id = self._require_space_project_id(space_id)
        self.get_collection_for_space(space_id, collection_id)
        return self.set_collection_meetings(project_id, collection_id, meeting_ids=meeting_ids)

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

    def list_references_for_space(
        self,
        space_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None = None,
        reading_status: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchReference], int]:
        self._get_space_record(space_id)
        stmt = select(ResearchReference).where(ResearchReference.research_space_id == space_id)
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

    def list_references_any(
        self,
        *,
        collection_id: uuid.UUID | None = None,
        reading_status: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchReference], int]:
        stmt = select(ResearchReference)
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

    def get_reference_for_space(self, space_id: uuid.UUID, reference_id: uuid.UUID) -> ResearchReference:
        item = self.db.scalar(
            select(ResearchReference).where(
                ResearchReference.research_space_id == space_id,
                ResearchReference.id == reference_id,
            )
        )
        if not item:
            raise NotFoundError("Reference not found.")
        return item

    def get_reference_any(self, reference_id: uuid.UUID) -> ResearchReference:
        item = self.db.get(ResearchReference, reference_id)
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

    def create_reference_for_space(
        self,
        space_id: uuid.UUID,
        **kwargs,
    ) -> ResearchReference:
        project_id = self._get_space_project_id(space_id)
        if project_id:
            item = self.create_reference(project_id, **kwargs)
        else:
            bibliography = self.create_bibliography_reference(
                title=kwargs["title"],
                authors=kwargs.get("authors") or [],
                year=kwargs.get("year"),
                venue=kwargs.get("venue"),
                doi=kwargs.get("doi"),
                url=kwargs.get("url"),
                abstract=kwargs.get("abstract"),
                bibtex_raw=None,
                visibility=kwargs.get("bibliography_visibility") or "shared",
                created_by_user_id=kwargs.get("created_by_user_id"),
            )
            item = ResearchReference(
                research_space_id=space_id,
                project_id=None,
                bibliography_reference_id=bibliography.id,
                title=kwargs["title"][:512].strip(),
                collection_id=kwargs.get("collection_id"),
                authors=kwargs.get("authors") or [],
                year=kwargs.get("year"),
                venue=(kwargs.get("venue") or "").strip() or None,
                doi=(kwargs.get("doi") or "").strip() or None,
                url=(kwargs.get("url") or "").strip() or None,
                abstract=(kwargs.get("abstract") or "").strip() or None,
                document_key=kwargs.get("document_key"),
                tags=kwargs.get("tags") or [],
                reading_status=self._reading_status(kwargs.get("reading_status") or "unread"),
                added_by_member_id=kwargs.get("added_by_member_id"),
            )
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
        item.research_space_id = space_id
        item.project_id = project_id
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_reference_for_collection(self, collection_id: uuid.UUID, **kwargs) -> ResearchReference:
        collection = self.get_collection_any(collection_id)
        primary_space_id = collection.research_space_id
        project_id = collection.project_id
        if primary_space_id:
            return self.create_reference_for_space(primary_space_id, collection_id=collection_id, **kwargs)
        if project_id:
            return self.create_reference(project_id, collection_id=collection_id, **kwargs)
        bibliography = self.create_bibliography_reference(
            title=kwargs["title"],
            authors=kwargs.get("authors") or [],
            year=kwargs.get("year"),
            venue=kwargs.get("venue"),
            doi=kwargs.get("doi"),
            url=kwargs.get("url"),
            abstract=kwargs.get("abstract"),
            bibtex_raw=None,
            visibility=kwargs.get("bibliography_visibility") or "shared",
            created_by_user_id=kwargs.get("created_by_user_id"),
        )
        item = ResearchReference(
            research_space_id=None,
            project_id=None,
            bibliography_reference_id=bibliography.id,
            title=kwargs["title"][:512].strip(),
            collection_id=collection_id,
            authors=kwargs.get("authors") or [],
            year=kwargs.get("year"),
            venue=(kwargs.get("venue") or "").strip() or None,
            doi=(kwargs.get("doi") or "").strip() or None,
            url=(kwargs.get("url") or "").strip() or None,
            abstract=(kwargs.get("abstract") or "").strip() or None,
            document_key=kwargs.get("document_key"),
            tags=kwargs.get("tags") or [],
            reading_status=self._reading_status(kwargs.get("reading_status") or "unread"),
            added_by_member_id=kwargs.get("added_by_member_id"),
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

    def update_reference_for_space(self, space_id: uuid.UUID, reference_id: uuid.UUID, **kwargs) -> ResearchReference:
        item = self.get_reference_for_space(space_id, reference_id)
        if item.project_id:
            return self.update_reference(item.project_id, reference_id, **kwargs)
        if kwargs.get("title") is not None:
            item.title = kwargs["title"][:512].strip()
        if kwargs.get("collection_id") is not None:
            item.collection_id = uuid.UUID(kwargs["collection_id"]) if kwargs["collection_id"] else None
        if kwargs.get("authors") is not None:
            item.authors = kwargs["authors"]
        if kwargs.get("year") is not None:
            item.year = kwargs["year"]
        if kwargs.get("venue") is not None:
            item.venue = kwargs["venue"].strip() or None
        if kwargs.get("doi") is not None:
            item.doi = kwargs["doi"].strip() or None
        if kwargs.get("url") is not None:
            item.url = kwargs["url"].strip() or None
        if kwargs.get("abstract") is not None:
            item.abstract = kwargs["abstract"].strip() or None
        if kwargs.get("document_key") is not None:
            item.document_key = uuid.UUID(kwargs["document_key"]) if kwargs["document_key"] else None
        if kwargs.get("tags") is not None:
            item.tags = kwargs["tags"]
        if kwargs.get("reading_status") is not None:
            item.reading_status = self._reading_status(kwargs["reading_status"])
        if item.bibliography_reference_id:
            bibliography = self.get_bibliography_reference(item.bibliography_reference_id)
            bibliography.title = item.title
            bibliography.authors = item.authors or []
            bibliography.year = item.year
            bibliography.venue = item.venue
            bibliography.doi = item.doi
            bibliography.url = item.url
            bibliography.abstract = item.abstract
            if kwargs.get("bibliography_visibility") is not None:
                bibliography.visibility = self._bibliography_visibility(kwargs["bibliography_visibility"])
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_reference_any(self, reference_id: uuid.UUID, **kwargs) -> ResearchReference:
        item = self.get_reference_any(reference_id)
        if item.project_id:
            return self.update_reference(item.project_id, reference_id, **kwargs)
        if item.research_space_id:
            return self.update_reference_for_space(item.research_space_id, reference_id, **kwargs)
        if kwargs.get("title") is not None:
            item.title = kwargs["title"][:512].strip()
        if kwargs.get("collection_id") is not None:
            item.collection_id = uuid.UUID(kwargs["collection_id"]) if kwargs["collection_id"] else None
        if kwargs.get("authors") is not None:
            item.authors = kwargs["authors"]
        if kwargs.get("year") is not None:
            item.year = kwargs["year"]
        if kwargs.get("venue") is not None:
            item.venue = kwargs["venue"].strip() or None
        if kwargs.get("doi") is not None:
            item.doi = kwargs["doi"].strip() or None
        if kwargs.get("url") is not None:
            item.url = kwargs["url"].strip() or None
        if kwargs.get("abstract") is not None:
            item.abstract = kwargs["abstract"].strip() or None
        if kwargs.get("document_key") is not None:
            item.document_key = uuid.UUID(kwargs["document_key"]) if kwargs["document_key"] else None
        if kwargs.get("tags") is not None:
            item.tags = kwargs["tags"]
        if kwargs.get("reading_status") is not None:
            item.reading_status = self._reading_status(kwargs["reading_status"])
        if item.bibliography_reference_id:
            bibliography = self.get_bibliography_reference(item.bibliography_reference_id)
            bibliography.title = item.title
            bibliography.authors = item.authors or []
            bibliography.year = item.year
            bibliography.venue = item.venue
            bibliography.doi = item.doi
            bibliography.url = item.url
            bibliography.abstract = item.abstract
            if kwargs.get("bibliography_visibility") is not None:
                bibliography.visibility = self._bibliography_visibility(kwargs["bibliography_visibility"])
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_reference_for_space(self, space_id: uuid.UUID, reference_id: uuid.UUID) -> None:
        item = self.get_reference_for_space(space_id, reference_id)
        self.db.delete(item)
        self.db.commit()

    def delete_reference_any(self, reference_id: uuid.UUID) -> None:
        item = self.get_reference_any(reference_id)
        self.db.delete(item)
        self.db.commit()

    def move_reference_for_space(self, space_id: uuid.UUID, reference_id: uuid.UUID, *, collection_id: uuid.UUID | None) -> ResearchReference:
        item = self.get_reference_for_space(space_id, reference_id)
        item.collection_id = collection_id
        self.db.commit()
        self.db.refresh(item)
        return item

    def move_reference_any(self, reference_id: uuid.UUID, *, collection_id: uuid.UUID | None) -> ResearchReference:
        item = self.get_reference_any(reference_id)
        item.collection_id = collection_id
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_reference_status_for_space(self, space_id: uuid.UUID, reference_id: uuid.UUID, *, reading_status: str) -> ResearchReference:
        item = self.get_reference_for_space(space_id, reference_id)
        item.reading_status = self._reading_status(reading_status)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_reference_status_any(self, reference_id: uuid.UUID, *, reading_status: str) -> ResearchReference:
        item = self.get_reference_any(reference_id)
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
            stmt = stmt.where(
                or_(
                    BibliographyReference.title.ilike(pattern),
                    cast(BibliographyReference.authors, Text).ilike(pattern),
                )
            )
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

    def link_bibliography_reference_for_space(
        self,
        space_id: uuid.UUID,
        *,
        bibliography_reference_id: uuid.UUID,
        collection_id: uuid.UUID | None = None,
        reading_status: str = "unread",
        added_by_member_id: uuid.UUID | None = None,
    ) -> ResearchReference:
        bibliography = self.get_bibliography_reference(bibliography_reference_id)
        if collection_id:
            self.get_collection_for_space(space_id, collection_id)
        existing = self.db.scalar(
            select(ResearchReference).where(
                ResearchReference.research_space_id == space_id,
                ResearchReference.collection_id == collection_id,
                ResearchReference.bibliography_reference_id == bibliography_reference_id,
            )
        )
        if existing:
            return existing

        project_id = self._get_space_project_id(space_id)
        linked_document_key = None
        if project_id and bibliography.document_key and bibliography.source_project_id:
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
            research_space_id=space_id,
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
        lane: str | None = None,
        note_type: str | None = None,
        author_member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchNote], int]:
        self._get_project(project_id)
        stmt = select(ResearchNote).where(ResearchNote.project_id == project_id)
        if collection_id:
            stmt = stmt.where(ResearchNote.collection_id == collection_id)
        normalized_lane = self._note_lane(lane)
        if lane is not None:
            if normalized_lane:
                stmt = stmt.where(ResearchNote.lane == normalized_lane)
            else:
                stmt = stmt.where(ResearchNote.lane.is_(None))
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

    def list_notes_for_space(
        self,
        space_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None = None,
        lane: str | None = None,
        note_type: str | None = None,
        author_member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchNote], int]:
        self._get_space_record(space_id)
        stmt = select(ResearchNote).where(ResearchNote.research_space_id == space_id)
        if collection_id:
            stmt = stmt.where(ResearchNote.collection_id == collection_id)
        normalized_lane = self._note_lane(lane)
        if lane is not None:
            if normalized_lane:
                stmt = stmt.where(ResearchNote.lane == normalized_lane)
            else:
                stmt = stmt.where(ResearchNote.lane.is_(None))
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

    def list_notes_any(
        self,
        *,
        collection_id: uuid.UUID | None = None,
        lane: str | None = None,
        note_type: str | None = None,
        author_member_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ResearchNote], int]:
        stmt = select(ResearchNote)
        if collection_id:
            stmt = stmt.where(ResearchNote.collection_id == collection_id)
        normalized_lane = self._note_lane(lane)
        if lane is not None:
            if normalized_lane:
                stmt = stmt.where(ResearchNote.lane == normalized_lane)
            else:
                stmt = stmt.where(ResearchNote.lane.is_(None))
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

    def get_note_for_space(self, space_id: uuid.UUID, note_id: uuid.UUID) -> ResearchNote:
        item = self.db.scalar(
            select(ResearchNote).where(
                ResearchNote.research_space_id == space_id,
                ResearchNote.id == note_id,
            )
        )
        if not item:
            raise NotFoundError("Note not found.")
        return item

    def get_note_any(self, note_id: uuid.UUID) -> ResearchNote:
        item = self.db.get(ResearchNote, note_id)
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
        lane: str | None = None,
        note_type: str = "observation",
        tags: list[str] | None = None,
        author_member_id: uuid.UUID | None = None,
        linked_reference_ids: list[str] | None = None,
        linked_file_ids: list[str] | None = None,
    ) -> ResearchNote:
        self._get_project(project_id)
        item = ResearchNote(
            project_id=project_id,
            title=title[:255].strip(),
            content=content.strip(),
            collection_id=collection_id,
            lane=self._note_lane(lane),
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
        if linked_file_ids:
            allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(collection_id)}
            for file_id in linked_file_ids:
                if file_id in allowed_ids:
                    self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(file_id)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_note_for_space(self, space_id: uuid.UUID, **kwargs) -> ResearchNote:
        project_id = self._get_space_project_id(space_id)
        if project_id:
            item = self.create_note(project_id, **kwargs)
        else:
            item = ResearchNote(
                research_space_id=space_id,
                project_id=None,
                title=kwargs["title"][:255].strip(),
                content=kwargs["content"].strip(),
                collection_id=kwargs.get("collection_id"),
                lane=self._note_lane(kwargs.get("lane")),
                note_type=self._note_type(kwargs.get("note_type") or "observation"),
                tags=kwargs.get("tags") or [],
                author_member_id=kwargs.get("author_member_id"),
            )
            self.db.add(item)
            self.db.flush()
            if kwargs.get("linked_reference_ids"):
                for rid in kwargs["linked_reference_ids"]:
                    self.db.execute(insert(research_note_references).values(note_id=item.id, reference_id=uuid.UUID(rid)))
            if kwargs.get("linked_file_ids"):
                allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(kwargs.get("collection_id"))}
                for file_id in kwargs["linked_file_ids"]:
                    if file_id in allowed_ids:
                        self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(file_id)))
            self.db.commit()
            self.db.refresh(item)
        item.research_space_id = space_id
        item.project_id = project_id
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_note_for_collection(self, collection_id: uuid.UUID, **kwargs) -> ResearchNote:
        collection = self.get_collection_any(collection_id)
        if collection.research_space_id:
            return self.create_note_for_space(collection.research_space_id, collection_id=collection_id, **kwargs)
        if collection.project_id:
            return self.create_note(collection.project_id, collection_id=collection_id, **kwargs)
        item = ResearchNote(
            research_space_id=None,
            project_id=None,
            title=kwargs["title"][:255].strip(),
            content=kwargs["content"].strip(),
            collection_id=collection_id,
            lane=self._note_lane(kwargs.get("lane")),
            note_type=self._note_type(kwargs.get("note_type") or "observation"),
            tags=kwargs.get("tags") or [],
            author_member_id=kwargs.get("author_member_id"),
        )
        self.db.add(item)
        self.db.flush()
        if kwargs.get("linked_reference_ids"):
            for rid in kwargs["linked_reference_ids"]:
                self.db.execute(insert(research_note_references).values(note_id=item.id, reference_id=uuid.UUID(rid)))
        if kwargs.get("linked_file_ids"):
            allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(collection_id)}
            for file_id in kwargs["linked_file_ids"]:
                if file_id in allowed_ids:
                    self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(file_id)))
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
        lane: str | None = None,
        note_type: str | None = None,
        tags: list[str] | None = None,
        linked_file_ids: list[str] | None = None,
    ) -> ResearchNote:
        item = self.get_note(project_id, note_id)
        if title is not None:
            item.title = title[:255].strip()
        if content is not None:
            item.content = content.strip()
        if collection_id is not None:
            item.collection_id = uuid.UUID(collection_id) if collection_id else None
        if lane is not None:
            item.lane = self._note_lane(lane)
        if note_type is not None:
            item.note_type = self._note_type(note_type)
        if tags is not None:
            item.tags = tags
        if linked_file_ids is not None:
            self.db.execute(delete(research_note_files).where(research_note_files.c.note_id == item.id))
            allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(item.collection_id)}
            for file_id in linked_file_ids:
                if file_id in allowed_ids:
                    self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(file_id)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_note_for_space(self, space_id: uuid.UUID, note_id: uuid.UUID, **kwargs) -> ResearchNote:
        item = self.get_note_for_space(space_id, note_id)
        if item.project_id:
            return self.update_note(item.project_id, note_id, **kwargs)
        if kwargs.get("title") is not None:
            item.title = kwargs["title"][:255].strip()
        if kwargs.get("content") is not None:
            item.content = kwargs["content"].strip()
        if kwargs.get("collection_id") is not None:
            item.collection_id = uuid.UUID(kwargs["collection_id"]) if kwargs["collection_id"] else None
        if kwargs.get("lane") is not None:
            item.lane = self._note_lane(kwargs["lane"])
        if kwargs.get("note_type") is not None:
            item.note_type = self._note_type(kwargs["note_type"])
        if kwargs.get("tags") is not None:
            item.tags = kwargs["tags"]
        if kwargs.get("linked_file_ids") is not None:
            self.db.execute(delete(research_note_files).where(research_note_files.c.note_id == item.id))
            allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(item.collection_id)}
            for file_id in kwargs["linked_file_ids"]:
                if file_id in allowed_ids:
                    self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(file_id)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_note_any(self, note_id: uuid.UUID, **kwargs) -> ResearchNote:
        item = self.get_note_any(note_id)
        if item.project_id:
            return self.update_note(item.project_id, note_id, **kwargs)
        if item.research_space_id:
            return self.update_note_for_space(item.research_space_id, note_id, **kwargs)
        if kwargs.get("title") is not None:
            item.title = kwargs["title"][:255].strip()
        if kwargs.get("content") is not None:
            item.content = kwargs["content"].strip()
        if kwargs.get("collection_id") is not None:
            item.collection_id = uuid.UUID(kwargs["collection_id"]) if kwargs["collection_id"] else None
        if kwargs.get("lane") is not None:
            item.lane = self._note_lane(kwargs["lane"])
        if kwargs.get("note_type") is not None:
            item.note_type = self._note_type(kwargs["note_type"])
        if kwargs.get("tags") is not None:
            item.tags = kwargs["tags"]
        if kwargs.get("linked_file_ids") is not None:
            self.db.execute(delete(research_note_files).where(research_note_files.c.note_id == item.id))
            allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(item.collection_id)}
            for file_id in kwargs["linked_file_ids"]:
                if file_id in allowed_ids:
                    self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(file_id)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_note_for_space(self, space_id: uuid.UUID, note_id: uuid.UUID) -> None:
        item = self.get_note_for_space(space_id, note_id)
        self.db.delete(item)
        self.db.commit()

    def delete_note_any(self, note_id: uuid.UUID) -> None:
        item = self.get_note_any(note_id)
        self.db.delete(item)
        self.db.commit()

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

    def set_note_references_for_space(
        self,
        space_id: uuid.UUID,
        note_id: uuid.UUID,
        *,
        reference_ids: list[str],
    ) -> ResearchNote:
        item = self.get_note_for_space(space_id, note_id)
        self.db.execute(delete(research_note_references).where(research_note_references.c.note_id == item.id))
        for rid in reference_ids:
            self.db.execute(insert(research_note_references).values(note_id=item.id, reference_id=uuid.UUID(rid)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def set_note_references_any(
        self,
        note_id: uuid.UUID,
        *,
        reference_ids: list[str],
    ) -> ResearchNote:
        item = self.get_note_any(note_id)
        self.db.execute(delete(research_note_references).where(research_note_references.c.note_id == item.id))
        for rid in reference_ids:
            self.db.execute(insert(research_note_references).values(note_id=item.id, reference_id=uuid.UUID(rid)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def get_note_reference_ids(self, note_id: uuid.UUID) -> list[str]:
        rows = self.db.execute(
            select(research_note_references.c.reference_id).where(research_note_references.c.note_id == note_id)
        ).all()
        return [str(r[0]) for r in rows]

    def get_note_file_ids(self, note_id: uuid.UUID) -> list[str]:
        rows = self.db.execute(
            select(research_note_files.c.file_id).where(research_note_files.c.note_id == note_id)
        ).all()
        return [str(r[0]) for r in rows]

    def set_note_files(
        self,
        project_id: uuid.UUID,
        note_id: uuid.UUID,
        *,
        file_ids: list[str],
    ) -> ResearchNote:
        item = self.get_note(project_id, note_id)
        allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(item.collection_id)}
        self.db.execute(delete(research_note_files).where(research_note_files.c.note_id == item.id))
        for raw_id in file_ids:
            if raw_id not in allowed_ids:
                continue
            self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(raw_id)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def set_note_files_for_space(
        self,
        space_id: uuid.UUID,
        note_id: uuid.UUID,
        *,
        file_ids: list[str],
    ) -> ResearchNote:
        item = self.get_note_for_space(space_id, note_id)
        allowed_ids = {str(file.id) for file in self.list_study_files_for_collection(item.collection_id)}
        self.db.execute(delete(research_note_files).where(research_note_files.c.note_id == item.id))
        for raw_id in file_ids:
            if raw_id not in allowed_ids:
                continue
            self.db.execute(insert(research_note_files).values(note_id=item.id, file_id=uuid.UUID(raw_id)))
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_study_files_for_collection(
        self,
        collection_id: uuid.UUID | None,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> list[ResearchStudyFile]:
        if not collection_id:
            return []
        return list(
            self.db.scalars(
                select(ResearchStudyFile)
                .where(ResearchStudyFile.collection_id == collection_id)
                .order_by(ResearchStudyFile.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )

    def list_study_files(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[ResearchStudyFile], int]:
        self.get_collection(project_id, collection_id)
        stmt = select(ResearchStudyFile).where(ResearchStudyFile.collection_id == collection_id)
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ResearchStudyFile.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return items, total

    def list_study_files_for_space_scope(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[ResearchStudyFile], int]:
        self.get_collection_for_space(space_id, collection_id)
        stmt = select(ResearchStudyFile).where(
            ResearchStudyFile.research_space_id == space_id,
            ResearchStudyFile.collection_id == collection_id,
        )
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ResearchStudyFile.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return items, total

    def list_study_files_for_collection_scope(
        self,
        collection_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[ResearchStudyFile], int]:
        self.get_collection_any(collection_id)
        stmt = select(ResearchStudyFile).where(ResearchStudyFile.collection_id == collection_id)
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ResearchStudyFile.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return items, total

    def upload_study_file(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        file_name: str,
        content_type: str | None,
        file_stream: BinaryIO,
    ) -> ResearchStudyFile:
        collection = self.get_collection(project_id, collection_id)
        file_id = uuid.uuid4()
        storage_path = self._study_file_storage_path(collection.id, file_id, file_name)
        file_size_bytes = self._write_study_file(file_stream, storage_path)
        item = ResearchStudyFile(
            id=file_id,
            project_id=project_id,
            research_space_id=collection.research_space_id,
            collection_id=collection.id,
            uploaded_by_user_id=actor_user_id,
            original_filename=Path(file_name).name or "file.bin",
            storage_uri=str(storage_path),
            mime_type=(content_type or "application/octet-stream").strip() or "application/octet-stream",
            file_size_bytes=file_size_bytes,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def upload_study_file_for_space(
        self,
        space_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        file_name: str,
        content_type: str | None,
        file_stream: BinaryIO,
    ) -> ResearchStudyFile:
        collection = self.get_collection_for_space(space_id, collection_id)
        file_id = uuid.uuid4()
        storage_path = self._study_file_storage_path(collection.id, file_id, file_name)
        file_size_bytes = self._write_study_file(file_stream, storage_path)
        item = ResearchStudyFile(
            id=file_id,
            project_id=collection.project_id,
            research_space_id=space_id,
            collection_id=collection.id,
            uploaded_by_user_id=actor_user_id,
            original_filename=Path(file_name).name or "file.bin",
            storage_uri=str(storage_path),
            mime_type=(content_type or "application/octet-stream").strip() or "application/octet-stream",
            file_size_bytes=file_size_bytes,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def upload_study_file_for_collection(
        self,
        collection_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID,
        file_name: str,
        content_type: str | None,
        file_stream: BinaryIO,
    ) -> ResearchStudyFile:
        collection = self.get_collection_any(collection_id)
        if collection.research_space_id:
            return self.upload_study_file_for_space(
                collection.research_space_id,
                collection_id,
                actor_user_id=actor_user_id,
                file_name=file_name,
                content_type=content_type,
                file_stream=file_stream,
            )
        if collection.project_id:
            return self.upload_study_file(
                collection.project_id,
                collection_id,
                actor_user_id=actor_user_id,
                file_name=file_name,
                content_type=content_type,
                file_stream=file_stream,
            )
        file_id = uuid.uuid4()
        storage_path = self._study_file_storage_path(collection.id, file_id, file_name)
        file_size_bytes = self._write_study_file(file_stream, storage_path)
        item = ResearchStudyFile(
            id=file_id,
            project_id=None,
            research_space_id=None,
            collection_id=collection.id,
            uploaded_by_user_id=actor_user_id,
            original_filename=Path(file_name).name or "file.bin",
            storage_uri=str(storage_path),
            mime_type=(content_type or "application/octet-stream").strip() or "application/octet-stream",
            file_size_bytes=file_size_bytes,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def get_study_file(self, project_id: uuid.UUID, collection_id: uuid.UUID, file_id: uuid.UUID) -> ResearchStudyFile:
        self.get_collection(project_id, collection_id)
        item = self.db.scalar(
            select(ResearchStudyFile).where(
                ResearchStudyFile.project_id == project_id,
                ResearchStudyFile.collection_id == collection_id,
                ResearchStudyFile.id == file_id,
            )
        )
        if not item:
            raise NotFoundError("Study file not found.")
        return item

    def get_study_file_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID, file_id: uuid.UUID) -> ResearchStudyFile:
        self.get_collection_for_space(space_id, collection_id)
        item = self.db.scalar(
            select(ResearchStudyFile).where(
                ResearchStudyFile.research_space_id == space_id,
                ResearchStudyFile.collection_id == collection_id,
                ResearchStudyFile.id == file_id,
            )
        )
        if not item:
            raise NotFoundError("Study file not found.")
        return item

    def get_study_file_any(self, collection_id: uuid.UUID, file_id: uuid.UUID) -> ResearchStudyFile:
        self.get_collection_any(collection_id)
        item = self.db.scalar(
            select(ResearchStudyFile).where(
                ResearchStudyFile.collection_id == collection_id,
                ResearchStudyFile.id == file_id,
            )
        )
        if not item:
            raise NotFoundError("Study file not found.")
        return item

    def delete_study_file(self, project_id: uuid.UUID, collection_id: uuid.UUID, file_id: uuid.UUID) -> None:
        item = self.get_study_file(project_id, collection_id, file_id)
        path = Path(item.storage_uri)
        self.db.delete(item)
        self.db.commit()
        if path.exists():
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass

    def delete_study_file_for_space(self, space_id: uuid.UUID, collection_id: uuid.UUID, file_id: uuid.UUID) -> None:
        item = self.get_study_file_for_space(space_id, collection_id, file_id)
        path = Path(item.storage_uri)
        self.db.delete(item)
        self.db.commit()
        if path.exists():
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass

    def delete_study_file_any(self, collection_id: uuid.UUID, file_id: uuid.UUID) -> None:
        item = self.get_study_file_any(collection_id, file_id)
        path = Path(item.storage_uri)
        self.db.delete(item)
        self.db.commit()
        if path.exists():
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass

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
