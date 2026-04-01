"""Research workspace API routes."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.chat_serialization import build_scoped_chat_message_payload
from app.core.config import settings
from app.core.security import decode_token, get_current_user
from app.db.session import SessionLocal, get_db
from app.models.auth import UserAccount
from app.models.collaboration_chat import ProjectChatRoomMember
from app.models.research import BibliographyReference
from app.models.organization import TeamMember
from app.schemas.research import (
    AISummaryRead,
    AISynthesisRead,
    BibliographyBibtexImportRead,
    BibliographyDuplicateCheckPayload,
    BibliographyDuplicateCheckRead,
    BibliographyDuplicateMatchRead,
    BibliographyGraphEdgeRead,
    BibliographyGraphNodeRead,
    BibliographyGraphRead,
    BibliographyGraphRequest,
    BibliographyIdentifierImportPayload,
    BibliographyIdentifierImportRead,
    BibliographyCollectionBulkResearchLinkPayload,
    BibliographyCollectionBulkTeachingLinkPayload,
    BibliographyCollectionCreate,
    BibliographyCollectionListRead,
    BibliographyCollectionRead,
    BibliographyCollectionReferenceUpsert,
    BibliographyCollectionUpdate,
    BibliographyLinkPayload,
    BibliographyNoteCreate,
    BibliographyNoteListRead,
    BibliographyNoteRead,
    BibliographyNoteUpdate,
    BibliographyReadingStatusRead,
    BibliographyReadingStatusUpdate,
    BibliographyReferenceCreate,
    BibliographyReferenceListRead,
    BibliographyReferenceRead,
    BibliographySemanticEvidenceRead,
    BibliographyReferenceUpdate,
    BibliographyTagListRead,
    BibliographyTagRead,
    BibtexImportPayload,
    BibtexImportRead,
    CollectionCreate,
    CollectionDetailRead,
    CollectionMeetingPayload,
    CollectionMeetingRead,
    CollectionListRead,
    CollectionMemberCreate,
    CollectionMemberRead,
    CollectionMemberUpdate,
    CollectionRead,
    CollectionUpdate,
    NoteCreate,
    NoteReplyCreate,
    NoteReplyRead,
    StudyFileListRead,
    StudyFileRead,
    NoteListRead,
    NoteRead,
    NoteReferencesPayload,
    NoteUpdate,
    ReferenceCreate,
    ReferenceListRead,
    ReferenceMetadataRead,
    ReferenceMovePayload,
    ReferenceRead,
    ReferenceStatusPayload,
    ReferenceUpdate,
    ResearchSpaceCreate,
    ResearchSpaceListRead,
    ResearchSpaceRead,
    ResearchSpaceUpdate,
    ResultComparisonRead,
    StudyChatRoomRead,
    StudyChatMessageCreate,
    StudyChatMessageListRead,
    StudyChatMessageRead,
    StudyChatReactionToggleRequest,
    WbsLinksPayload,
    WbsLinksRead,
)
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.research_service import DuplicateBibliographyError, GLOBAL_RESEARCH_PROJECT_ID, ResearchService


def require_research_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not current_user.can_access_research:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Research.")


def require_bibliography_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not (current_user.can_access_research or current_user.can_access_teaching):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Bibliography.")


router = APIRouter(dependencies=[Depends(require_research_access)])
websocket_router = APIRouter()
bibliography_router = APIRouter(prefix="/bibliography", dependencies=[Depends(require_bibliography_access)])


class StudyChatHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._presence_counts: dict[str, dict[str, int]] = defaultdict(dict)

    async def connect(self, room_key: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[room_key].add(websocket)

    def disconnect(self, room_key: str, websocket: WebSocket) -> None:
        if room_key in self._connections:
            self._connections[room_key].discard(websocket)
            if not self._connections[room_key]:
                del self._connections[room_key]
        if room_key in self._presence_counts and not self._presence_counts[room_key]:
            del self._presence_counts[room_key]

    def user_join(self, room_key: str, user_id: uuid.UUID) -> bool:
        key = str(user_id)
        room_map = self._presence_counts[room_key]
        previous = room_map.get(key, 0)
        room_map[key] = previous + 1
        return previous == 0

    def user_leave(self, room_key: str, user_id: uuid.UUID) -> bool:
        key = str(user_id)
        room_map = self._presence_counts.get(room_key, {})
        previous = room_map.get(key, 0)
        if previous <= 1:
            room_map.pop(key, None)
            if room_key in self._presence_counts and not self._presence_counts[room_key]:
                del self._presence_counts[room_key]
            return previous > 0
        room_map[key] = previous - 1
        return False

    def online_user_ids(self, room_key: str) -> list[str]:
        return sorted(self._presence_counts.get(room_key, {}).keys())

    async def broadcast(self, room_key: str, payload: dict) -> None:
        sockets = list(self._connections.get(room_key, set()))
        if not sockets:
            return
        text = json.dumps(payload, ensure_ascii=True)
        dead: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_text(text)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.disconnect(room_key, socket)


study_chat_hub = StudyChatHub()


def _resolve_member_id(db: Session, user: UserAccount, project_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(TeamMember.id).where(
            TeamMember.user_account_id == user.id,
            TeamMember.project_id == project_id,
            TeamMember.is_active.is_(True),
        )
    )


@router.get("/research/spaces", response_model=ResearchSpaceListRead)
def list_research_spaces(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ResearchSpaceListRead:
    svc = ResearchService(db)
    items, total = svc.list_research_spaces(current_user.id, page=page, page_size=page_size)
    return ResearchSpaceListRead(
        items=[_research_space_read(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/research/spaces", response_model=ResearchSpaceRead, status_code=status.HTTP_201_CREATED)
def create_research_space(
    payload: ResearchSpaceCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ResearchSpaceRead:
    svc = ResearchService(db)
    try:
        item = svc.create_research_space(
            actor_user_id=current_user.id,
            title=payload.title,
            focus=payload.focus,
            linked_project_id=uuid.UUID(payload.linked_project_id) if payload.linked_project_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid linked_project_id UUID.") from exc
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _research_space_read(item)


@router.put("/research/spaces/{space_id}", response_model=ResearchSpaceRead)
def update_research_space(
    space_id: uuid.UUID,
    payload: ResearchSpaceUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ResearchSpaceRead:
    svc = ResearchService(db)
    linked_project_id = ... if payload.linked_project_id is None and "linked_project_id" not in payload.model_fields_set else (
        uuid.UUID(payload.linked_project_id) if payload.linked_project_id else None
    )
    try:
        item = svc.update_research_space(
            space_id,
            current_user.id,
            title=payload.title,
            focus=payload.focus,
            linked_project_id=linked_project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid linked_project_id UUID.") from exc
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _research_space_read(item)


# ══════════════════════════════════════════════════════════════════════
# Collections
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/collections", response_model=CollectionListRead)
def list_collections(
    project_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    member_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CollectionListRead:
    svc = ResearchService(db)
    try:
        if space_id:
            items, total = svc.list_collections_for_space(
                uuid.UUID(space_id),
                status_filter=status_filter,
                member_id=uuid.UUID(member_id) if member_id else None,
                page=page,
                page_size=page_size,
            )
        else:
            items, total = svc.list_collections(
                None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id,
                status_filter=status_filter,
                member_id=uuid.UUID(member_id) if member_id else None,
                page=page,
                page_size=page_size,
            )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CollectionListRead(
        items=[_collection_read(svc, c) for c in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/collections", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    project_id: uuid.UUID,
    payload: CollectionCreate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> CollectionRead:
    svc = ResearchService(db)
    member_id = None if project_id == GLOBAL_RESEARCH_PROJECT_ID else _resolve_member_id(db, current_user, project_id)
    try:
        params = dict(
            title=payload.title,
            space_ids=[uuid.UUID(item) for item in payload.space_ids],
            description=payload.description,
            hypothesis=payload.hypothesis,
            open_questions=payload.open_questions,
            status=payload.status,
            tags=payload.tags,
            overleaf_url=payload.overleaf_url,
            paper_motivation=payload.paper_motivation,
            target_output_title=payload.target_output_title,
            target_venue=payload.target_venue,
            registration_deadline=payload.registration_deadline,
            submission_deadline=payload.submission_deadline,
            decision_date=payload.decision_date,
            study_iterations=[item.model_dump(mode="json") for item in payload.study_iterations],
            study_results=[item.model_dump(mode="json") for item in payload.study_results],
            paper_authors=[item.model_dump(mode="json") for item in payload.paper_authors],
            paper_questions=[item.model_dump(mode="json") for item in payload.paper_questions],
            paper_claims=[item.model_dump(mode="json") for item in payload.paper_claims],
            paper_sections=[item.model_dump(mode="json") for item in payload.paper_sections],
            output_status=payload.output_status,
            created_by_member_id=member_id,
            creator_user_id=current_user.id,
        )
        item = (
            svc.create_collection_for_space(uuid.UUID(space_id), **params)
            if space_id else
            svc.create_collection(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, **params)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _collection_read(svc, item)


@router.get("/{project_id}/research/collections/{collection_id}", response_model=CollectionDetailRead)
def get_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionDetailRead:
    svc = ResearchService(db)
    try:
        if space_id:
            sid = uuid.UUID(space_id)
            item = svc.get_collection_for_space(sid, collection_id)
            members_data = svc.list_collection_members_for_space(sid, collection_id)
            wbs = svc.get_wbs_links_for_space(sid, collection_id)
            meetings = svc.list_collection_meetings_for_space(sid, collection_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            item = svc.get_collection_any(collection_id)
            members_data = svc._list_collection_members_common(collection_id)
            wbs = {"wp_ids": [], "task_ids": [], "deliverable_ids": []}
            meetings = []
        else:
            item = svc.get_collection(project_id, collection_id)
            members_data = svc.list_collection_members(project_id, collection_id)
            wbs = svc.get_wbs_links(project_id, collection_id)
            meetings = svc.list_collection_meetings(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    read = _collection_read(svc, item)
    return CollectionDetailRead(
        **read.model_dump(),
        members=[_member_read(d) for d in members_data],
        wp_ids=wbs["wp_ids"],
        task_ids=wbs["task_ids"],
        deliverable_ids=wbs["deliverable_ids"],
        meetings=[_meeting_read(item) for item in meetings],
    )


@router.post("/{project_id}/research/collections/{collection_id}/chat-room", response_model=StudyChatRoomRead)
def ensure_collection_chat_room(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> StudyChatRoomRead:
    svc = ResearchService(db)
    try:
        room = (
            svc.ensure_collection_chat_room_for_space(uuid.UUID(space_id), collection_id, actor_user_id=current_user.id)
            if space_id
            else svc.ensure_collection_chat_room(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, collection_id, actor_user_id=current_user.id)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _study_chat_room_read(svc, room)


@router.get("/{project_id}/research/collections/{collection_id}/chat/messages", response_model=StudyChatMessageListRead)
def list_study_chat_messages(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> StudyChatMessageListRead:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.get_collection_for_space(uuid.UUID(space_id), collection_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.get_collection_any(collection_id)
        else:
            svc.get_collection(project_id, collection_id)
        items, total = svc.list_study_chat_messages(
            collection_id,
            actor_user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    message_ids = [item.id for item in items]
    reaction_map = svc.study_chat_reaction_summary_by_message(message_ids)
    reply_lookup = svc.study_chat_message_lookup([item.reply_to_message_id for item in items if item.reply_to_message_id])
    return StudyChatMessageListRead(
        items=[_study_chat_message_read(svc, collection_id, item, reaction_map, reply_lookup) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/collections/{collection_id}/chat/messages", response_model=StudyChatMessageRead)
async def create_study_chat_message(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: StudyChatMessageCreate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> StudyChatMessageRead:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.get_collection_for_space(uuid.UUID(space_id), collection_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.get_collection_any(collection_id)
        else:
            svc.get_collection(project_id, collection_id)
        reply_to_message_id = uuid.UUID(payload.reply_to_message_id) if payload.reply_to_message_id else None
        message = svc.create_study_chat_message(
            collection_id,
            actor_user_id=current_user.id,
            content=payload.content,
            reply_to_message_id=reply_to_message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid reply_to_message_id UUID.") from exc
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    reaction_map = svc.study_chat_reaction_summary_by_message([message.id])
    reply_lookup = svc.study_chat_message_lookup([message.reply_to_message_id] if message.reply_to_message_id else [])
    rendered = _study_chat_message_read(svc, collection_id, message, reaction_map, reply_lookup)
    room_key = _study_chat_room_key(collection_id)
    return_payload = rendered.model_dump(mode="json")
    asyncio.create_task(study_chat_hub.broadcast(room_key, {"event": "message", "message": return_payload}))
    return rendered


@router.post("/{project_id}/research/collections/{collection_id}/chat/messages/{message_id}/reactions", response_model=StudyChatMessageRead)
async def toggle_study_chat_reaction(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: StudyChatReactionToggleRequest,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> StudyChatMessageRead:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.get_collection_for_space(uuid.UUID(space_id), collection_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.get_collection_any(collection_id)
        else:
            svc.get_collection(project_id, collection_id)
        message = svc.toggle_study_chat_reaction(
            collection_id,
            message_id,
            actor_user_id=current_user.id,
            emoji=payload.emoji,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    reaction_map = svc.study_chat_reaction_summary_by_message([message.id])
    reply_lookup = svc.study_chat_message_lookup([message.reply_to_message_id] if message.reply_to_message_id else [])
    rendered = _study_chat_message_read(svc, collection_id, message, reaction_map, reply_lookup)
    room_key = _study_chat_room_key(collection_id)
    return_payload = rendered.model_dump(mode="json")
    asyncio.create_task(study_chat_hub.broadcast(room_key, {"event": "message_update", "message": return_payload}))
    return rendered


@websocket_router.websocket("/{project_id}/research/collections/{collection_id}/chat/ws")
async def websocket_study_chat(
    websocket: WebSocket,
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
) -> None:
    token = websocket.query_params.get("token")
    raw_space_id = websocket.query_params.get("space_id")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return
    try:
        token_payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(str(token_payload["sub"]))
    except Exception:
        await websocket.close(code=4401, reason="Invalid token")
        return

    with SessionLocal() as db:
        svc = ResearchService(db)
        try:
            if raw_space_id:
                svc.get_collection_for_space(uuid.UUID(raw_space_id), collection_id)
            elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
                svc.get_collection_any(collection_id)
            else:
                svc.get_collection(project_id, collection_id)
            if not svc.can_access_collection_chat(collection_id, user_id):
                raise ValidationError("Forbidden")
            user = db.get(UserAccount, user_id)
            if not user:
                raise NotFoundError("User not found.")
        except Exception:
            await websocket.close(code=4403, reason="Forbidden")
            return
        display_name = user.display_name

    room_key = _study_chat_room_key(collection_id)
    await study_chat_hub.connect(room_key, websocket)
    became_online = study_chat_hub.user_join(room_key, user_id)

    try:
        await websocket.send_text(json.dumps({"event": "presence_snapshot", "user_ids": study_chat_hub.online_user_ids(room_key)}))
        if became_online:
            await study_chat_hub.broadcast(
                room_key,
                {"event": "presence", "status": "joined", "user_id": str(user_id), "display_name": display_name},
            )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        study_chat_hub.disconnect(room_key, websocket)
        became_offline = study_chat_hub.user_leave(room_key, user_id)
        if became_offline:
            await study_chat_hub.broadcast(
                room_key,
                {"event": "presence", "status": "left", "user_id": str(user_id), "display_name": display_name},
            )


@router.put("/{project_id}/research/collections/{collection_id}", response_model=CollectionRead)
def update_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: CollectionUpdate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionRead:
    svc = ResearchService(db)
    try:
        params = dict(
            title=payload.title,
            space_ids=[uuid.UUID(item) for item in payload.space_ids] if payload.space_ids is not None else None,
            description=payload.description,
            hypothesis=payload.hypothesis,
            open_questions=payload.open_questions,
            status=payload.status,
            tags=payload.tags,
            overleaf_url=payload.overleaf_url,
            paper_motivation=payload.paper_motivation,
            target_output_title=payload.target_output_title,
            target_venue=payload.target_venue,
            registration_deadline=payload.registration_deadline,
            submission_deadline=payload.submission_deadline,
            decision_date=payload.decision_date,
            study_iterations=[item.model_dump(mode="json") for item in payload.study_iterations] if payload.study_iterations is not None else None,
            study_results=[item.model_dump(mode="json") for item in payload.study_results] if payload.study_results is not None else None,
            paper_authors=[item.model_dump(mode="json") for item in payload.paper_authors] if payload.paper_authors is not None else None,
            paper_questions=[item.model_dump(mode="json") for item in payload.paper_questions] if payload.paper_questions is not None else None,
            paper_claims=[item.model_dump(mode="json") for item in payload.paper_claims] if payload.paper_claims is not None else None,
            paper_sections=[item.model_dump(mode="json") for item in payload.paper_sections] if payload.paper_sections is not None else None,
            output_status=payload.output_status,
        )
        item = (
            svc.update_collection_for_space(uuid.UUID(space_id), collection_id, **params)
            if space_id else
            svc.update_collection(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, collection_id, **params)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _collection_read(svc, item)


@router.post("/{project_id}/research/collections/{collection_id}/paper/audit-claims", response_model=CollectionDetailRead)
def audit_collection_paper_claims(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionDetailRead:
    from app.agents.paper_claim_audit_agent import PaperClaimAuditAgent

    svc = ResearchService(db)
    try:
        effective_project_id = project_id
        if effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            effective_project_id = svc.get_collection_any(collection_id).project_id or GLOBAL_RESEARCH_PROJECT_ID
        audits = PaperClaimAuditAgent().audit_collection_claims(effective_project_id, collection_id, db, space_id=uuid.UUID(space_id) if space_id else None)
        audit_payload = [
            {
                "claim_id": audit.claim_id,
                "audit_status": audit.audit_status,
                "audit_summary": audit.audit_summary,
                "supporting_reference_ids": audit.supporting_reference_ids,
                "supporting_note_ids": audit.supporting_note_ids,
                "missing_evidence": audit.missing_evidence,
                "audit_confidence": audit.audit_confidence,
                "audited_at": audit.audited_at,
            }
            for audit in audits
        ]
        item = (
            svc.apply_paper_claim_audits_for_space(uuid.UUID(space_id), collection_id, audits=audit_payload)
            if space_id else
            svc.apply_paper_claim_audits(effective_project_id, collection_id, audits=audit_payload)
        )
        if space_id:
            sid = uuid.UUID(space_id)
            members_data = svc.list_collection_members_for_space(sid, collection_id)
            wbs = svc.get_wbs_links_for_space(sid, collection_id)
            meetings = svc.list_collection_meetings_for_space(sid, collection_id)
        elif effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            members_data = svc._list_collection_members_common(collection_id)
            wbs = {"wp_ids": [], "task_ids": [], "deliverable_ids": []}
            meetings = []
        else:
            members_data = svc.list_collection_members(effective_project_id, collection_id)
            wbs = svc.get_wbs_links(effective_project_id, collection_id)
            meetings = svc.list_collection_meetings(effective_project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Claim audit failed: {exc}") from exc
    read = _collection_read(svc, item)
    return CollectionDetailRead(
        **read.model_dump(),
        members=[_member_read(d) for d in members_data],
        wp_ids=wbs["wp_ids"],
        task_ids=wbs["task_ids"],
        deliverable_ids=wbs["deliverable_ids"],
        meetings=[_meeting_read(item) for item in meetings],
    )


@router.post("/{project_id}/research/collections/{collection_id}/paper/build-outline", response_model=CollectionDetailRead)
def build_collection_paper_outline(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionDetailRead:
    from app.agents.paper_outline_agent import PaperOutlineAgent

    svc = ResearchService(db)
    try:
        effective_project_id = project_id
        if effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            effective_project_id = svc.get_collection_any(collection_id).project_id or GLOBAL_RESEARCH_PROJECT_ID
        sections = PaperOutlineAgent().build_collection_outline(effective_project_id, collection_id, db, space_id=uuid.UUID(space_id) if space_id else None)
        paper_sections = [
            {
                "id": str(uuid.uuid4()),
                "title": section.title,
                "question_ids": section.question_ids,
                "claim_ids": section.claim_ids,
                "reference_ids": section.reference_ids,
                "note_ids": section.note_ids,
                "status": section.status,
            }
            for section in sections
        ]
        item = (
            svc.update_collection_for_space(uuid.UUID(space_id), collection_id, paper_sections=paper_sections)
            if space_id else
            svc.update_collection(effective_project_id, collection_id, paper_sections=paper_sections)
        )
        if space_id:
            sid = uuid.UUID(space_id)
            members_data = svc.list_collection_members_for_space(sid, collection_id)
            wbs = svc.get_wbs_links_for_space(sid, collection_id)
            meetings = svc.list_collection_meetings_for_space(sid, collection_id)
        elif effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            members_data = svc._list_collection_members_common(collection_id)
            wbs = {"wp_ids": [], "task_ids": [], "deliverable_ids": []}
            meetings = []
        else:
            members_data = svc.list_collection_members(effective_project_id, collection_id)
            wbs = svc.get_wbs_links(effective_project_id, collection_id)
            meetings = svc.list_collection_meetings(effective_project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Outline build failed: {exc}") from exc
    read = _collection_read(svc, item)
    return CollectionDetailRead(
        **read.model_dump(),
        members=[_member_read(d) for d in members_data],
        wp_ids=wbs["wp_ids"],
        task_ids=wbs["task_ids"],
        deliverable_ids=wbs["deliverable_ids"],
        meetings=[_meeting_read(item) for item in meetings],
    )


@router.post("/{project_id}/research/collections/{collection_id}/paper/draft-from-gap", response_model=CollectionDetailRead)
def draft_collection_paper_from_gap(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionDetailRead:
    from app.agents.paper_gap_agent import PaperGapAgent

    svc = ResearchService(db)
    try:
        current = (
            svc.get_collection_for_space(uuid.UUID(space_id), collection_id)
            if space_id else
            svc.get_collection_any(collection_id)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.get_collection(project_id, collection_id)
        )
        effective_project_id = current.project_id or GLOBAL_RESEARCH_PROJECT_ID
        draft = PaperGapAgent().build_gap_draft(effective_project_id, collection_id, db, space_id=uuid.UUID(space_id) if space_id else None)
        existing_questions = [item for item in (current.paper_questions or []) if isinstance(item, dict)]
        existing_texts = {
            " ".join(str(item.get("text") or "").strip().lower().split())
            for item in existing_questions
            if str(item.get("text") or "").strip()
        }
        next_questions = list(existing_questions)
        for text in draft.questions:
            normalized = " ".join(text.strip().lower().split())
            if not normalized or normalized in existing_texts:
                continue
            existing_texts.add(normalized)
            next_questions.append({"id": str(uuid.uuid4()), "text": text, "note_ids": []})
        item = (
            svc.update_collection_for_space(uuid.UUID(space_id), collection_id, paper_motivation=draft.motivation or current.paper_motivation, paper_questions=next_questions)
            if space_id else
            svc.update_collection(effective_project_id, collection_id, paper_motivation=draft.motivation or current.paper_motivation, paper_questions=next_questions)
        )
        if space_id:
            sid = uuid.UUID(space_id)
            members_data = svc.list_collection_members_for_space(sid, collection_id)
            wbs = svc.get_wbs_links_for_space(sid, collection_id)
            meetings = svc.list_collection_meetings_for_space(sid, collection_id)
        elif effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            members_data = svc._list_collection_members_common(collection_id)
            wbs = {"wp_ids": [], "task_ids": [], "deliverable_ids": []}
            meetings = []
        else:
            members_data = svc.list_collection_members(effective_project_id, collection_id)
            wbs = svc.get_wbs_links(effective_project_id, collection_id)
            meetings = svc.list_collection_meetings(effective_project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gap draft failed: {exc}") from exc
    read = _collection_read(svc, item)
    return CollectionDetailRead(
        **read.model_dump(),
        members=[_member_read(d) for d in members_data],
        wp_ids=wbs["wp_ids"],
        task_ids=wbs["task_ids"],
        deliverable_ids=wbs["deliverable_ids"],
        meetings=[_meeting_read(item) for item in meetings],
    )


@router.post("/{project_id}/research/collections/{collection_id}/iterations/{iteration_id}/review", response_model=CollectionDetailRead)
def review_collection_iteration(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    iteration_id: str,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionDetailRead:
    from app.agents.iteration_review_agent import IterationReviewAgent

    svc = ResearchService(db)
    try:
        current = (
            svc.get_collection_for_space(uuid.UUID(space_id), collection_id)
            if space_id else
            svc.get_collection_any(collection_id)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.get_collection(project_id, collection_id)
        )
        iterations = [item for item in (current.study_iterations or []) if isinstance(item, dict)]
        target = next((item for item in iterations if str(item.get("id") or "") == iteration_id), None)
        if not target:
            raise NotFoundError("Iteration not found.")
        effective_project_id = current.project_id or GLOBAL_RESEARCH_PROJECT_ID
        review = IterationReviewAgent().review_iteration(effective_project_id, collection_id, target, db, space_id=uuid.UUID(space_id) if space_id else None)
        next_iterations = []
        for item in iterations:
            if str(item.get("id") or "") != iteration_id:
                next_iterations.append(item)
                continue
            merged = dict(item)
            merged["summary"] = review.summary
            merged["what_changed"] = review.what_changed
            merged["improvements"] = review.improvements
            merged["regressions"] = review.regressions
            merged["unclear_points"] = review.unclear_points
            merged["next_actions"] = review.next_actions
            merged["reviewed_at"] = review.reviewed_at
            next_iterations.append(merged)
        item = svc.update_collection_for_space(uuid.UUID(space_id), collection_id, study_iterations=next_iterations) if space_id else svc.update_collection(effective_project_id, collection_id, study_iterations=next_iterations)
        if space_id:
            sid = uuid.UUID(space_id)
            members_data = svc.list_collection_members_for_space(sid, collection_id)
            wbs = svc.get_wbs_links_for_space(sid, collection_id)
            meetings = svc.list_collection_meetings_for_space(sid, collection_id)
        elif effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            members_data = svc._list_collection_members_common(collection_id)
            wbs = {"wp_ids": [], "task_ids": [], "deliverable_ids": []}
            meetings = []
        else:
            members_data = svc.list_collection_members(effective_project_id, collection_id)
            wbs = svc.get_wbs_links(effective_project_id, collection_id)
            meetings = svc.list_collection_meetings(effective_project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Iteration review failed: {exc}") from exc
    read = _collection_read(svc, item)
    return CollectionDetailRead(
        **read.model_dump(),
        members=[_member_read(d) for d in members_data],
        wp_ids=wbs["wp_ids"],
        task_ids=wbs["task_ids"],
        deliverable_ids=wbs["deliverable_ids"],
        meetings=[_meeting_read(item) for item in meetings],
    )


@router.post("/{project_id}/research/collections/{collection_id}/results/compare", response_model=ResultComparisonRead)
def compare_collection_results(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ResultComparisonRead:
    from app.agents.result_comparison_agent import ResultComparisonAgent

    svc = ResearchService(db)
    try:
        effective_project_id = project_id
        if effective_project_id == GLOBAL_RESEARCH_PROJECT_ID:
            effective_project_id = svc.get_collection_any(collection_id).project_id or GLOBAL_RESEARCH_PROJECT_ID
        report = ResultComparisonAgent().compare_recent_results(effective_project_id, collection_id, db, space_id=uuid.UUID(space_id) if space_id else None)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Result comparison failed: {exc}") from exc
    return ResultComparisonRead(**report.__dict__)


@router.delete("/{project_id}/research/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.delete_collection_for_space(uuid.UUID(space_id), collection_id)
        else:
            svc.delete_collection(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Collection members ────────────────────────────────────────────────


@router.get("/{project_id}/research/collections/{collection_id}/members", response_model=list[CollectionMemberRead])
def list_collection_members(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CollectionMemberRead]:
    svc = ResearchService(db)
    try:
        members_data = (
            svc.list_collection_members_for_space(uuid.UUID(space_id), collection_id)
            if space_id else
            svc.list_collection_members(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, collection_id)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_member_read(d) for d in members_data]


@router.post("/{project_id}/research/collections/{collection_id}/members", response_model=CollectionMemberRead, status_code=status.HTTP_201_CREATED)
def add_collection_member(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: CollectionMemberCreate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionMemberRead:
    svc = ResearchService(db)
    try:
        member_uuid = uuid.UUID(payload.member_id) if payload.member_id else None
        user_uuid = uuid.UUID(payload.user_id) if payload.user_id else None
        data = (
            svc.add_collection_member_for_space(uuid.UUID(space_id), collection_id, member_id=member_uuid, user_id=user_uuid, role=payload.role)
            if space_id else
            svc.add_collection_member(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, collection_id, member_id=member_uuid, user_id=user_uuid, role=payload.role)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid member/user UUID.") from exc
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _member_read(data)


@router.put("/{project_id}/research/collections/{collection_id}/members/{member_record_id}", response_model=CollectionMemberRead)
def update_collection_member(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    member_record_id: uuid.UUID,
    payload: CollectionMemberUpdate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CollectionMemberRead:
    svc = ResearchService(db)
    try:
        data = (
            svc.update_collection_member_role_for_space(uuid.UUID(space_id), collection_id, member_record_id, role=payload.role)
            if space_id else
            svc.update_collection_member_role(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, collection_id, member_record_id, role=payload.role)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _member_read(data)


@router.delete("/{project_id}/research/collections/{collection_id}/members/{member_record_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collection_member(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    member_record_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.remove_collection_member_for_space(uuid.UUID(space_id), collection_id, member_record_id)
        else:
            svc.remove_collection_member(None if project_id == GLOBAL_RESEARCH_PROJECT_ID else project_id, collection_id, member_record_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── WBS links ─────────────────────────────────────────────────────────


@router.put("/{project_id}/research/collections/{collection_id}/wbs-links", response_model=WbsLinksRead)
def set_wbs_links(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: WbsLinksPayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> WbsLinksRead:
    svc = ResearchService(db)
    try:
        result = (
            svc.set_wbs_links_for_space(uuid.UUID(space_id), collection_id, wp_ids=payload.wp_ids, task_ids=payload.task_ids, deliverable_ids=payload.deliverable_ids)
            if space_id else
            svc.set_wbs_links(project_id, collection_id, wp_ids=payload.wp_ids, task_ids=payload.task_ids, deliverable_ids=payload.deliverable_ids)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WbsLinksRead(**result)


@router.put("/{project_id}/research/collections/{collection_id}/meetings", response_model=list[CollectionMeetingRead])
def set_collection_meetings(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: CollectionMeetingPayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CollectionMeetingRead]:
    svc = ResearchService(db)
    try:
        items = (
            svc.set_collection_meetings_for_space(uuid.UUID(space_id), collection_id, meeting_ids=payload.meeting_ids)
            if space_id else
            svc.set_collection_meetings(project_id, collection_id, meeting_ids=payload.meeting_ids)
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return [_meeting_read(item) for item in items]


# ══════════════════════════════════════════════════════════════════════
# References
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/references", response_model=ReferenceListRead)
def list_references(
    project_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    reading_status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None, alias="q"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ReferenceListRead:
    svc = ResearchService(db)
    try:
        if space_id:
            items, total = svc.list_references_for_space(
                uuid.UUID(space_id),
                collection_id=uuid.UUID(collection_id) if collection_id else None,
                reading_status=reading_status,
                tag=tag,
                search=search,
                page=page,
                page_size=page_size,
            )
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            items, total = svc.list_references_any(
                collection_id=uuid.UUID(collection_id) if collection_id else None,
                reading_status=reading_status,
                tag=tag,
                search=search,
                page=page,
                page_size=page_size,
            )
        else:
            items, total = svc.list_references(
                project_id,
                collection_id=uuid.UUID(collection_id) if collection_id else None,
                reading_status=reading_status,
                tag=tag,
                search=search,
                page=page,
                page_size=page_size,
            )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReferenceListRead(
        items=[_reference_read(svc, r) for r in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/references", response_model=ReferenceRead, status_code=status.HTTP_201_CREATED)
def create_reference(
    project_id: uuid.UUID,
    payload: ReferenceCreate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ReferenceRead:
    svc = ResearchService(db)
    member_id = None if project_id == GLOBAL_RESEARCH_PROJECT_ID else _resolve_member_id(db, current_user, project_id)
    try:
        params = dict(
            title=payload.title,
            collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            document_key=uuid.UUID(payload.document_key) if payload.document_key else None,
            tags=payload.tags,
            reading_status=payload.reading_status,
            bibliography_visibility=payload.bibliography_visibility,
            added_by_member_id=member_id,
            created_by_user_id=current_user.id,
        )
        item = (
            svc.create_reference_for_space(uuid.UUID(space_id), **params)
            if space_id else
            svc.create_reference_for_collection(uuid.UUID(payload.collection_id), **params)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID and payload.collection_id else
            svc.create_reference(project_id, **params)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.post("/{project_id}/research/references/import-bibtex", response_model=BibtexImportRead)
def import_bibtex(
    project_id: uuid.UUID,
    payload: BibtexImportPayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibtexImportRead:
    from app.services.bibtex_parser import parse_bibtex

    member_id = None if project_id == GLOBAL_RESEARCH_PROJECT_ID else _resolve_member_id(db, current_user, project_id)
    entries = parse_bibtex(payload.bibtex)
    if not entries:
        raise HTTPException(status_code=400, detail="No valid BibTeX entries found")

    svc = ResearchService(db)
    created: list[ReferenceRead] = []
    errors: list[str] = []
    collection_id = uuid.UUID(payload.collection_id) if payload.collection_id else None
    for entry in entries:
        try:
            params = dict(
                title=entry["title"],
                collection_id=collection_id,
                authors=entry["authors"],
                year=entry["year"],
                venue=entry["venue"],
                doi=entry["doi"],
                url=entry["url"],
                abstract=entry["abstract"],
                bibliography_visibility=payload.visibility,
                added_by_member_id=member_id,
                created_by_user_id=current_user.id,
            )
            item = (
                svc.create_reference_for_space(uuid.UUID(space_id), **params)
                if space_id else
                svc.create_reference_for_collection(collection_id, **params)
                if project_id == GLOBAL_RESEARCH_PROJECT_ID and collection_id else
                svc.create_reference(project_id, **params)
            )
            created.append(_reference_read(svc, item))
        except Exception as exc:
            errors.append(f"{entry.get('cite_key', '?')}: {exc}")
    return BibtexImportRead(created=created, errors=errors)


@router.get("/{project_id}/research/references/{reference_id}", response_model=ReferenceRead)
def get_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = (
            svc.get_reference_for_space(uuid.UUID(space_id), reference_id)
            if space_id else
            svc.get_reference_any(reference_id)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.get_reference(project_id, reference_id)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.put("/{project_id}/research/references/{reference_id}", response_model=ReferenceRead)
def update_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    payload: ReferenceUpdate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        params = dict(
            title=payload.title,
            collection_id=payload.collection_id,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            document_key=payload.document_key,
            tags=payload.tags,
            reading_status=payload.reading_status,
            bibliography_visibility=payload.bibliography_visibility,
        )
        item = (
            svc.update_reference_for_space(uuid.UUID(space_id), reference_id, **params)
            if space_id else
            svc.update_reference_any(reference_id, **params)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.update_reference(project_id, reference_id, **params)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


# ══════════════════════════════════════════════════════════════════════
# Bibliography
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/bibliography", response_model=BibliographyReferenceListRead)
def list_bibliography(
    project_id: uuid.UUID,
    bibliography_collection_id: str | None = Query(default=None),
    search: str | None = Query(default=None, alias="q"),
    visibility: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceListRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        items, total = svc.list_bibliography(
            current_user.id,
            bibliography_collection_id=uuid.UUID(bibliography_collection_id) if bibliography_collection_id else None,
            search=search,
            visibility=visibility,
            page=page,
            page_size=page_size,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return BibliographyReferenceListRead(
        items=[_bibliography_read(svc, project_id, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/bibliography", response_model=BibliographyReferenceRead, status_code=status.HTTP_201_CREATED)
def create_bibliography_reference(
    project_id: uuid.UUID,
    payload: BibliographyReferenceCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.create_bibliography_reference(
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
            created_by_user_id=current_user.id,
            allow_duplicate=payload.allow_duplicate,
            reuse_existing_id=uuid.UUID(payload.reuse_existing_id) if payload.reuse_existing_id else None,
        )
    except (NotFoundError, ValidationError, DuplicateBibliographyError) as exc:
        if isinstance(exc, DuplicateBibliographyError):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "matches": [
                        {
                            "match_reason": reason,
                            "reference": _bibliography_read_global(svc, item),
                        }
                        for reason, item in exc.matches
                    ],
                },
            ) from exc
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read(svc, project_id, item)


@router.put("/{project_id}/research/bibliography/{bibliography_reference_id}", response_model=BibliographyReferenceRead)
def update_bibliography_reference(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyReferenceUpdate,
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.update_bibliography_reference(
            bibliography_reference_id,
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read(svc, project_id, item)


@router.delete("/{project_id}/research/bibliography/{bibliography_reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bibliography_reference(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        svc.delete_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/research/bibliography/import-bibtex", response_model=BibliographyBibtexImportRead)
def import_bibliography_bibtex(
    project_id: uuid.UUID,
    payload: BibtexImportPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyBibtexImportRead:
    from app.services.bibtex_parser import parse_bibtex

    entries = parse_bibtex(payload.bibtex)
    if not entries:
        raise HTTPException(status_code=400, detail="No valid BibTeX entries found")

    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    created: list[BibliographyReferenceRead] = []
    errors: list[str] = []
    for entry in entries:
        try:
            item = svc.create_bibliography_reference(
                title=entry["title"],
                authors=entry["authors"],
                year=entry["year"],
                venue=entry["venue"],
                doi=entry["doi"],
                url=entry["url"],
                abstract=entry["abstract"],
                bibtex_raw=entry.get("raw") or None,
                visibility=payload.visibility,
                created_by_user_id=current_user.id,
            )
            created.append(_bibliography_read(svc, project_id, item))
        except DuplicateBibliographyError as exc:
            duplicate_titles = ", ".join(item.title for _, item in exc.matches[:2])
            errors.append(f"{entry.get('cite_key', '?')}: duplicate ({duplicate_titles})")
        except Exception as exc:
            errors.append(f"{entry.get('cite_key', '?')}: {exc}")
    return BibliographyBibtexImportRead(created=created, errors=errors)


@router.post("/{project_id}/research/bibliography/link", response_model=ReferenceRead, status_code=status.HTTP_201_CREATED)
def link_bibliography_reference(
    project_id: uuid.UUID,
    payload: BibliographyLinkPayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ReferenceRead:
    svc = ResearchService(db)
    use_space = space_id or project_id == GLOBAL_RESEARCH_PROJECT_ID
    if use_space:
        resolved_space_id = uuid.UUID(space_id) if space_id else None
        if not resolved_space_id and payload.collection_id:
            resolved_space_id = next(iter(svc.collection_space_ids(uuid.UUID(payload.collection_id))), None)
        if not resolved_space_id:
            raise HTTPException(status_code=400, detail="Cannot determine research space.")
        member_id = svc._space_member_id(resolved_space_id, current_user.id)
    else:
        resolved_space_id = None
        member_id = _resolve_member_id(db, current_user, project_id)
    try:
        item = (
            svc.link_bibliography_reference_for_space(
                resolved_space_id,
                bibliography_reference_id=uuid.UUID(payload.bibliography_reference_id),
                collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
                reading_status=payload.reading_status,
                added_by_member_id=member_id,
            )
            if use_space else
            svc.link_bibliography_reference(
                project_id,
                bibliography_reference_id=uuid.UUID(payload.bibliography_reference_id),
                collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
                reading_status=payload.reading_status,
                added_by_member_id=member_id,
            )
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.post("/{project_id}/research/bibliography/{bibliography_reference_id}/attachment", response_model=BibliographyReferenceRead)
async def upload_bibliography_attachment(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.attach_bibliography_file(
            project_id,
            bibliography_reference_id,
            file_name=file.filename or "reference.pdf",
            content_type=file.content_type or "application/pdf",
            file_stream=file.file,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await file.close()
    return _bibliography_read(svc, project_id, item)


@router.get("/{project_id}/research/bibliography/{bibliography_reference_id}/file")
def download_bibliography_attachment(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.get_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if item.document_key and item.source_project_id:
        from app.models.document import ProjectDocument

        document = db.scalar(
            select(ProjectDocument)
            .where(
                ProjectDocument.project_id == item.source_project_id,
                ProjectDocument.document_key == item.document_key,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if document and Path(document.storage_uri).exists():
            return FileResponse(
                str(Path(document.storage_uri)),
                media_type=document.mime_type or "application/pdf",
                filename=document.original_filename or item.attachment_filename or "reference.pdf",
            )
    if not item.attachment_path:
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    path = Path(item.attachment_path)
    if not path.is_absolute():
        base = Path(settings.documents_storage_path)
        if not base.is_absolute():
            base = (Path.cwd() / base).resolve()
        path = (base / path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    return FileResponse(
        path,
        media_type=item.attachment_mime_type or "application/pdf",
        filename=item.attachment_filename or path.name,
    )


@bibliography_router.get("/collections", response_model=BibliographyCollectionListRead)
def list_bibliography_collections(
    visibility: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyCollectionListRead:
    svc = ResearchService(db)
    items, total = svc.list_bibliography_collections(current_user.id, visibility=visibility, page=page, page_size=page_size)
    return BibliographyCollectionListRead(
        items=[_bibliography_collection_read(svc, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@bibliography_router.post("/collections", response_model=BibliographyCollectionRead, status_code=status.HTTP_201_CREATED)
def create_bibliography_collection(
    payload: BibliographyCollectionCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyCollectionRead:
    svc = ResearchService(db)
    item = svc.create_bibliography_collection(
        current_user.id,
        title=payload.title,
        description=payload.description,
        visibility=payload.visibility,
    )
    return _bibliography_collection_read(svc, item)


@bibliography_router.put("/collections/{bibliography_collection_id}", response_model=BibliographyCollectionRead)
def update_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyCollectionRead:
    svc = ResearchService(db)
    try:
        item = svc.update_bibliography_collection(
            bibliography_collection_id,
            current_user.id,
            title=payload.title,
            description=payload.description,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _bibliography_collection_read(svc, item)


@bibliography_router.delete("/collections/{bibliography_collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_bibliography_collection(bibliography_collection_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc


@bibliography_router.post("/collections/{bibliography_collection_id}/papers", status_code=status.HTTP_204_NO_CONTENT)
def add_paper_to_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionReferenceUpsert,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.add_reference_to_bibliography_collection(
            bibliography_collection_id,
            uuid.UUID(payload.bibliography_reference_id),
            current_user.id,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc


@bibliography_router.delete("/collections/{bibliography_collection_id}/papers/{bibliography_reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_paper_from_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.remove_reference_from_bibliography_collection(
            bibliography_collection_id,
            bibliography_reference_id,
            current_user.id,
        )
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc


@bibliography_router.get("/collections/{bibliography_collection_id}/paper-ids", response_model=list[str])
def list_bibliography_collection_paper_ids(
    bibliography_collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> list[str]:
    svc = ResearchService(db)
    try:
        ids = svc.bibliography_reference_ids_for_collection(bibliography_collection_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return [str(item) for item in ids]


@bibliography_router.post("/collections/{bibliography_collection_id}/link/research")
def bulk_link_bibliography_collection_to_research(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionBulkResearchLinkPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> dict[str, int]:
    svc = ResearchService(db)
    member_id = _resolve_member_id(db, current_user, uuid.UUID(payload.project_id))
    try:
        count = svc.bulk_link_bibliography_collection_to_research(
            bibliography_collection_id,
            project_id=uuid.UUID(payload.project_id),
            collection_id=uuid.UUID(payload.collection_id),
            actor_user_id=current_user.id,
            added_by_member_id=member_id,
            reading_status=payload.reading_status,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return {"linked": count}


@bibliography_router.post("/collections/{bibliography_collection_id}/link/teaching")
def bulk_link_bibliography_collection_to_teaching(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionBulkTeachingLinkPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> dict[str, int]:
    svc = ResearchService(db)
    try:
        count = svc.bulk_link_bibliography_collection_to_teaching(
            bibliography_collection_id,
            project_id=uuid.UUID(payload.project_id),
            actor_user_id=current_user.id,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return {"linked": count}


@bibliography_router.get("", response_model=BibliographyReferenceListRead)
def list_global_bibliography(
    bibliography_collection_id: str | None = Query(default=None),
    search: str | None = Query(default=None, alias="q"),
    visibility: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceListRead:
    svc = ResearchService(db)
    try:
        items, total = svc.list_bibliography(
            current_user.id,
            bibliography_collection_id=uuid.UUID(bibliography_collection_id) if bibliography_collection_id else None,
            search=search,
            visibility=visibility,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ref_ids = [item.id for item in items]
    note_counts = svc.bibliography_note_counts(ref_ids)
    reading_statuses = svc.get_bibliography_reading_statuses(current_user.id, ref_ids)
    return BibliographyReferenceListRead(
        items=[
            _bibliography_read_global(svc, item, note_counts=note_counts, reading_statuses=reading_statuses)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@bibliography_router.get("/search", response_model=BibliographyReferenceListRead)
def search_global_bibliography_semantic(
    q: str = Query(..., min_length=1),
    visibility: str | None = Query(default=None),
    top_k: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceListRead:
    """Semantic search over bibliography references using vector embeddings."""
    svc = ResearchService(db)
    results = svc.search_bibliography_semantic_with_evidence(current_user.id, q, visibility=visibility, top_k=top_k)
    items = [item for item, _ in results]
    ref_ids = [item.id for item in items]
    note_counts = svc.bibliography_note_counts(ref_ids)
    reading_statuses = svc.get_bibliography_reading_statuses(current_user.id, ref_ids)
    return BibliographyReferenceListRead(
        items=[
            _bibliography_read_global(
                svc,
                item,
                note_counts=note_counts,
                reading_statuses=reading_statuses,
                semantic_evidence=evidence,
            )
            for item, evidence in results
        ],
        page=1,
        page_size=top_k,
        total=len(items),
    )


@bibliography_router.post("/embed-backfill")
def bibliography_embed_backfill(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> dict[str, int]:
    """Backfill embeddings for bibliography references that don't have one yet."""
    svc = ResearchService(db)
    count = svc.embed_bibliography_backfill()
    db.commit()
    return {"embedded": count}


@bibliography_router.post("/{bibliography_reference_id}/summarize", response_model=AISummaryRead)
def summarize_bibliography_reference(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> AISummaryRead:
    from app.services.research_ai_service import ResearchAIService

    svc = ResearchService(db)
    try:
        svc.get_bibliography_reference_visible_to_user(bibliography_reference_id, user_id=current_user.id)
        ref = ResearchAIService(db).summarize_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI summarization failed: {exc}") from exc
    return AISummaryRead(ai_summary=ref.ai_summary, ai_summary_at=ref.ai_summary_at)


@bibliography_router.post("/graph", response_model=BibliographyGraphRead)
def build_bibliography_graph(
    payload: BibliographyGraphRequest,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyGraphRead:
    svc = ResearchService(db)
    try:
        graph = svc.bibliography_graph(
            user_id=current_user.id,
            reference_ids=[uuid.UUID(item) for item in payload.reference_ids],
            include_authors=payload.include_authors,
            include_concepts=payload.include_concepts,
            include_tags=payload.include_tags,
            include_semantic=payload.include_semantic,
            include_bibliography_collections=payload.include_bibliography_collections,
            include_research_links=payload.include_research_links,
            include_teaching_links=payload.include_teaching_links,
            semantic_threshold=payload.semantic_threshold,
            semantic_top_k=payload.semantic_top_k,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BibliographyGraphRead(
        nodes=[BibliographyGraphNodeRead(**item) for item in graph["nodes"]],
        edges=[BibliographyGraphEdgeRead(**item) for item in graph["edges"]],
    )


@bibliography_router.get("/tags", response_model=BibliographyTagListRead)
def list_global_bibliography_tags(
    search: str | None = Query(default=None, alias="q"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> BibliographyTagListRead:
    svc = ResearchService(db)
    items, total = svc.list_bibliography_tags(search=search, page=page, page_size=page_size)
    return BibliographyTagListRead(
        items=[
            BibliographyTagRead(
                id=str(item.id),
                label=item.label,
                slug=item.slug,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@bibliography_router.post("", response_model=BibliographyReferenceRead, status_code=status.HTTP_201_CREATED)
def create_global_bibliography_reference(
    payload: BibliographyReferenceCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.create_bibliography_reference(
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
            created_by_user_id=current_user.id,
            allow_duplicate=payload.allow_duplicate,
            reuse_existing_id=uuid.UUID(payload.reuse_existing_id) if payload.reuse_existing_id else None,
        )
    except DuplicateBibliographyError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "matches": [
                    {
                        "match_reason": reason,
                        "reference": _bibliography_read_global(svc, item),
                    }
                    for reason, item in exc.matches
                ],
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.post("/check-duplicates", response_model=BibliographyDuplicateCheckRead)
def check_global_bibliography_duplicates(
    payload: BibliographyDuplicateCheckPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyDuplicateCheckRead:
    svc = ResearchService(db)
    matches = svc.find_bibliography_duplicates(
        created_by_user_id=current_user.id,
        doi=payload.doi,
        title=payload.title,
    )
    return BibliographyDuplicateCheckRead(
        matches=[
            BibliographyDuplicateMatchRead(
                match_reason=reason,
                reference=_bibliography_read_global(svc, item),
            )
            for reason, item in matches
        ]
    )


@bibliography_router.put("/{bibliography_reference_id}", response_model=BibliographyReferenceRead)
def update_global_bibliography_reference(
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyReferenceUpdate,
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.update_bibliography_reference(
            bibliography_reference_id,
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.delete("/{bibliography_reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_bibliography_reference(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@bibliography_router.post("/import-bibtex", response_model=BibliographyBibtexImportRead)
def import_global_bibliography_bibtex(
    payload: BibtexImportPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyBibtexImportRead:
    from app.services.bibtex_parser import parse_bibtex

    entries = parse_bibtex(payload.bibtex)
    if not entries:
        raise HTTPException(status_code=400, detail="No valid BibTeX entries found")

    svc = ResearchService(db)
    created: list[BibliographyReferenceRead] = []
    errors: list[str] = []
    for entry in entries:
        try:
            item = svc.create_bibliography_reference(
                title=entry["title"],
                authors=entry["authors"],
                year=entry["year"],
                venue=entry["venue"],
                doi=entry["doi"],
                url=entry["url"],
                abstract=entry["abstract"],
                bibtex_raw=entry.get("raw") or None,
                visibility=payload.visibility,
                created_by_user_id=current_user.id,
            )
            created.append(_bibliography_read_global(svc, item))
        except DuplicateBibliographyError as exc:
            duplicate_titles = ", ".join(item.title for _, item in exc.matches[:2])
            errors.append(f"{entry.get('cite_key', '?')}: duplicate ({duplicate_titles})")
        except Exception as exc:
            errors.append(f"{entry.get('cite_key', '?')}: {exc}")
    return BibliographyBibtexImportRead(created=created, errors=errors)


@bibliography_router.post("/import-identifiers", response_model=BibliographyIdentifierImportRead)
def import_global_bibliography_identifiers(
    payload: BibliographyIdentifierImportPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyIdentifierImportRead:
    svc = ResearchService(db)
    try:
        created, reused, errors = svc.import_bibliography_identifiers(
            identifiers=payload.identifiers,
            visibility=payload.visibility,
            created_by_user_id=current_user.id,
            source_project_id=uuid.UUID(payload.source_project_id) if payload.source_project_id else None,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BibliographyIdentifierImportRead(
        created=[_bibliography_read_global(svc, item) for item in created],
        reused=[_bibliography_read_global(svc, item) for item in reused],
        errors=errors,
    )


@bibliography_router.post("/{bibliography_reference_id}/attachment", response_model=BibliographyReferenceRead)
async def upload_global_bibliography_attachment(
    bibliography_reference_id: uuid.UUID,
    source_project_id: uuid.UUID = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.attach_bibliography_file(
            source_project_id,
            bibliography_reference_id,
            file_name=file.filename or "reference.pdf",
            content_type=file.content_type or "application/pdf",
            file_stream=file.file,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await file.close()
    return _bibliography_read_global(svc, item)


@bibliography_router.post("/{bibliography_reference_id}/ingest", response_model=BibliographyReferenceRead)
def ingest_global_bibliography_attachment(
    bibliography_reference_id: uuid.UUID,
    source_project_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.ensure_bibliography_document_ingested(
            bibliography_reference_id,
            source_project_id=source_project_id,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.post("/{bibliography_reference_id}/extract-abstract", response_model=BibliographyReferenceRead)
def extract_global_bibliography_abstract(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.extract_bibliography_abstract(bibliography_reference_id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.post("/{bibliography_reference_id}/extract-concepts", response_model=BibliographyReferenceRead)
def extract_global_bibliography_concepts(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceRead:
    from app.services.research_ai_service import ResearchAIService

    svc = ResearchService(db)
    try:
        svc.get_bibliography_reference_visible_to_user(bibliography_reference_id, user_id=current_user.id)
        labels = ResearchAIService(db).extract_bibliography_concepts(bibliography_reference_id)
        item = svc.set_bibliography_reference_concepts(bibliography_reference_id, labels)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI concept extraction failed: {exc}") from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.get("/{bibliography_reference_id}/file")
def download_global_bibliography_attachment(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    svc = ResearchService(db)
    try:
        item = svc.get_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if item.document_key and item.source_project_id:
        from app.models.document import ProjectDocument

        document = db.scalar(
            select(ProjectDocument)
            .where(
                ProjectDocument.project_id == item.source_project_id,
                ProjectDocument.document_key == item.document_key,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if document and Path(document.storage_uri).exists():
            return FileResponse(
                str(Path(document.storage_uri)),
                media_type=document.mime_type or "application/pdf",
                filename=document.original_filename or item.attachment_filename or "reference.pdf",
            )
    if not item.attachment_path:
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    path = Path(item.attachment_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    return FileResponse(
        path,
        media_type=item.attachment_mime_type or "application/pdf",
        filename=item.attachment_filename or path.name,
    )


# ── Bibliography notes ─────────────────────────────────────────────


def _bibliography_note_read(note, display_name: str) -> BibliographyNoteRead:
    return BibliographyNoteRead(
        id=str(note.id),
        bibliography_reference_id=str(note.bibliography_reference_id),
        user_id=str(note.user_id),
        user_display_name=display_name,
        content=note.content,
        note_type=note.note_type,
        visibility=note.visibility.value if hasattr(note.visibility, "value") else str(note.visibility),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@bibliography_router.get("/{bibliography_reference_id}/notes", response_model=BibliographyNoteListRead)
def list_bibliography_notes(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyNoteListRead:
    svc = ResearchService(db)
    rows = svc.list_bibliography_notes(bibliography_reference_id, current_user.id)
    return BibliographyNoteListRead(
        items=[_bibliography_note_read(note, display_name) for note, display_name in rows],
    )


@bibliography_router.post("/{bibliography_reference_id}/notes", response_model=BibliographyNoteRead, status_code=status.HTTP_201_CREATED)
def create_bibliography_note(
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyNoteCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyNoteRead:
    svc = ResearchService(db)
    try:
        item = svc.create_bibliography_note(
            bibliography_reference_id,
            current_user.id,
            content=payload.content,
            note_type=payload.note_type,
            visibility=payload.visibility,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _bibliography_note_read(item, current_user.display_name)


@bibliography_router.put("/notes/{note_id}", response_model=BibliographyNoteRead)
def update_bibliography_note(
    note_id: uuid.UUID,
    payload: BibliographyNoteUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyNoteRead:
    svc = ResearchService(db)
    try:
        item = svc.update_bibliography_note(
            note_id,
            current_user.id,
            content=payload.content,
            note_type=payload.note_type,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_note_read(item, current_user.display_name)


@bibliography_router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bibliography_note(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_bibliography_note(note_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 403
        raise HTTPException(status_code=code, detail=str(exc)) from exc


# ── Bibliography reading status ───────────────────────────────────


@bibliography_router.get("/{bibliography_reference_id}/status", response_model=BibliographyReadingStatusRead)
def get_bibliography_reading_status(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReadingStatusRead:
    svc = ResearchService(db)
    return BibliographyReadingStatusRead(
        reading_status=svc.get_bibliography_reading_status(bibliography_reference_id, current_user.id),
    )


@bibliography_router.put("/{bibliography_reference_id}/status", response_model=BibliographyReadingStatusRead)
def set_bibliography_reading_status(
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyReadingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReadingStatusRead:
    svc = ResearchService(db)
    try:
        result = svc.set_bibliography_reading_status(bibliography_reference_id, current_user.id, payload.reading_status)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BibliographyReadingStatusRead(reading_status=result)


@router.delete("/{project_id}/research/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.delete_reference_for_space(uuid.UUID(space_id), reference_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.delete_reference_any(reference_id)
        else:
            svc.delete_reference(project_id, reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{project_id}/research/references/{reference_id}/move", response_model=ReferenceRead)
def move_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    payload: ReferenceMovePayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = (
            svc.move_reference_for_space(uuid.UUID(space_id), reference_id, collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None)
            if space_id else
            svc.move_reference_any(reference_id, collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.move_reference(project_id, reference_id, collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.put("/{project_id}/research/references/{reference_id}/status", response_model=ReferenceRead)
def update_reference_status(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    payload: ReferenceStatusPayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = (
            svc.update_reference_status_for_space(uuid.UUID(space_id), reference_id, reading_status=payload.reading_status)
            if space_id else
            svc.update_reference_status_any(reference_id, reading_status=payload.reading_status)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.update_reference_status(project_id, reference_id, reading_status=payload.reading_status)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


# ══════════════════════════════════════════════════════════════════════
# Notes
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/notes", response_model=NoteListRead)
def list_notes(
    project_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    collection_id: str | None = Query(default=None),
    lane: str | None = Query(default=None),
    note_type: str | None = Query(default=None),
    author_member_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> NoteListRead:
    svc = ResearchService(db)
    try:
        items, total = (
            svc.list_notes_for_space(
                uuid.UUID(space_id),
                collection_id=uuid.UUID(collection_id) if collection_id else None,
                lane=lane,
                note_type=note_type,
                author_member_id=uuid.UUID(author_member_id) if author_member_id else None,
                page=page,
                page_size=page_size,
            )
            if space_id else
            svc.list_notes_any(
                collection_id=uuid.UUID(collection_id) if collection_id else None,
                lane=lane,
                note_type=note_type,
                author_member_id=uuid.UUID(author_member_id) if author_member_id else None,
                page=page,
                page_size=page_size,
            )
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.list_notes(
                project_id,
                collection_id=uuid.UUID(collection_id) if collection_id else None,
                lane=lane,
                note_type=note_type,
                author_member_id=uuid.UUID(author_member_id) if author_member_id else None,
                page=page,
                page_size=page_size,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return NoteListRead(
        items=[_note_read(svc, n) for n in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    project_id: uuid.UUID,
    payload: NoteCreate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> NoteRead:
    svc = ResearchService(db)
    member_id = None if project_id == GLOBAL_RESEARCH_PROJECT_ID else _resolve_member_id(db, current_user, project_id)
    try:
        params = dict(
            title=payload.title,
            content=payload.content,
            lane=payload.lane,
            note_type=payload.note_type,
            tags=payload.tags,
            author_member_id=member_id,
            user_account_id=current_user.id,
            linked_reference_ids=payload.linked_reference_ids,
            linked_file_ids=payload.linked_file_ids,
        )
        item = (
            svc.create_note_for_space(uuid.UUID(space_id), **params)
            if space_id else
            svc.create_note_for_collection(uuid.UUID(payload.collection_id), **params)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID and payload.collection_id else
            svc.create_note(project_id, **params)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.post("/{project_id}/research/notes/{note_id}/replies", response_model=NoteReplyRead, status_code=status.HTTP_201_CREATED)
def create_note_reply(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: NoteReplyCreate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> NoteReplyRead:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.get_note_for_space(uuid.UUID(space_id), note_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.get_note_any(note_id)
        else:
            svc.get_note(project_id, note_id)
        reply = svc.create_note_reply(
            note_id,
            user_account_id=current_user.id,
            content=payload.content,
            linked_reference_ids=payload.linked_reference_ids,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return NoteReplyRead(
        id=str(reply.id),
        note_id=str(reply.note_id),
        user_account_id=str(reply.user_account_id) if reply.user_account_id else None,
        author_name=current_user.display_name,
        author_avatar_url=current_user.avatar_path,
        content=reply.content,
        linked_reference_ids=svc.get_note_reply_reference_ids(reply.id),
        created_at=reply.created_at,
        updated_at=reply.updated_at,
    )


@router.get("/{project_id}/research/notes/{note_id}", response_model=NoteRead)
def get_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> NoteRead:
    svc = ResearchService(db)
    try:
        item = (
            svc.get_note_for_space(uuid.UUID(space_id), note_id)
            if space_id else
            svc.get_note_any(note_id)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.get_note(project_id, note_id)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.put("/{project_id}/research/notes/{note_id}", response_model=NoteRead)
def update_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: NoteUpdate,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> NoteRead:
    svc = ResearchService(db)
    try:
        params = dict(
            title=payload.title,
            content=payload.content,
            collection_id=payload.collection_id,
            lane=payload.lane,
            note_type=payload.note_type,
            tags=payload.tags,
            linked_file_ids=payload.linked_file_ids,
        )
        item = (
            svc.update_note_for_space(uuid.UUID(space_id), note_id, **params)
            if space_id else
            svc.update_note_any(note_id, **params)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.update_note(project_id, note_id, **params)
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.delete("/{project_id}/research/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.delete_note_for_space(uuid.UUID(space_id), note_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.delete_note_any(note_id)
        else:
            svc.delete_note(project_id, note_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{project_id}/research/notes/{note_id}/references", response_model=NoteRead)
def set_note_references(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: NoteReferencesPayload,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> NoteRead:
    svc = ResearchService(db)
    try:
        item = (
            svc.set_note_references_for_space(uuid.UUID(space_id), note_id, reference_ids=payload.reference_ids)
            if space_id else
            svc.set_note_references_any(note_id, reference_ids=payload.reference_ids)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.set_note_references(project_id, note_id, reference_ids=payload.reference_ids)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.get("/{project_id}/research/collections/{collection_id}/files", response_model=StudyFileListRead)
def list_study_files(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StudyFileListRead:
    svc = ResearchService(db)
    try:
        items, total = (
            svc.list_study_files_for_space_scope(uuid.UUID(space_id), collection_id, page=page, page_size=page_size)
            if space_id else
            svc.list_study_files_for_collection_scope(collection_id, page=page, page_size=page_size)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.list_study_files(project_id, collection_id, page=page, page_size=page_size)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StudyFileListRead(
        items=[_study_file_read(project_id if project_id != GLOBAL_RESEARCH_PROJECT_ID else (item.project_id or GLOBAL_RESEARCH_PROJECT_ID), svc, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/collections/{collection_id}/files", response_model=StudyFileRead, status_code=status.HTTP_201_CREATED)
def upload_study_file(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    file: UploadFile = File(...),
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> StudyFileRead:
    svc = ResearchService(db)
    try:
        item = (
            svc.upload_study_file_for_space(
                uuid.UUID(space_id),
                collection_id,
                actor_user_id=current_user.id,
                file_name=file.filename or "file.bin",
                content_type=file.content_type,
                file_stream=file.file,
            )
            if space_id else
            svc.upload_study_file_for_collection(
                collection_id,
                actor_user_id=current_user.id,
                file_name=file.filename or "file.bin",
                content_type=file.content_type,
                file_stream=file.file,
            )
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.upload_study_file(
                project_id,
                collection_id,
                actor_user_id=current_user.id,
                file_name=file.filename or "file.bin",
                content_type=file.content_type,
                file_stream=file.file,
            )
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    resolved_project_id = project_id if project_id != GLOBAL_RESEARCH_PROJECT_ID else (item.project_id or GLOBAL_RESEARCH_PROJECT_ID)
    return _study_file_read(resolved_project_id, svc, item)


@router.get("/{project_id}/research/collections/{collection_id}/files/{file_id}/download")
def download_study_file(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    file_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> FileResponse:
    svc = ResearchService(db)
    try:
        item = (
            svc.get_study_file_for_space(uuid.UUID(space_id), collection_id, file_id)
            if space_id else
            svc.get_study_file_any(collection_id, file_id)
            if project_id == GLOBAL_RESEARCH_PROJECT_ID else
            svc.get_study_file(project_id, collection_id, file_id)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    file_path = Path(item.storage_uri)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Study file is missing from storage.")
    return FileResponse(str(file_path), filename=item.original_filename, media_type=item.mime_type or "application/octet-stream")


@router.delete("/{project_id}/research/collections/{collection_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_study_file(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    file_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        if space_id:
            svc.delete_study_file_for_space(uuid.UUID(space_id), collection_id, file_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            svc.delete_study_file_any(collection_id, file_id)
        else:
            svc.delete_study_file(project_id, collection_id, file_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ══════════════════════════════════════════════════════════════════════
# AI
# ══════════════════════════════════════════════════════════════════════


@router.post("/{project_id}/research/references/{reference_id}/summarize", response_model=AISummaryRead)
def summarize_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AISummaryRead:
    from app.services.research_ai_service import ResearchAIService
    ai_svc = ResearchAIService(db)
    research_svc = ResearchService(db)
    try:
        if space_id:
            ref = ai_svc.summarize_reference_for_space(uuid.UUID(space_id), reference_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            current = research_svc.get_reference_any(reference_id)
            if current.research_space_id:
                ref = ai_svc.summarize_reference_for_space(current.research_space_id, reference_id)
            elif current.project_id:
                ref = ai_svc.summarize_reference(current.project_id, reference_id)
            else:
                raise ValidationError("AI summary requires the study to be linked to a space or project.")
        else:
            ref = ai_svc.summarize_reference(project_id, reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI summarization failed: {exc}") from exc
    return AISummaryRead(ai_summary=ref.ai_summary, ai_summary_at=ref.ai_summary_at)


@router.post("/{project_id}/research/references/extract-from-pdf", response_model=ReferenceMetadataRead)
def extract_metadata_from_pdf(
    project_id: uuid.UUID,
    document_key: str = Query(...),
    db: Session = Depends(get_db),
) -> ReferenceMetadataRead:
    from app.services.research_ai_service import ResearchAIService
    svc = ResearchAIService(db)
    try:
        metadata = svc.extract_metadata_from_pdf(project_id, uuid.UUID(document_key))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Metadata extraction failed: {exc}") from exc
    return ReferenceMetadataRead(**metadata)


@router.post("/{project_id}/research/collections/{collection_id}/synthesize", response_model=AISynthesisRead)
def synthesize_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    space_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AISynthesisRead:
    from app.services.research_ai_service import ResearchAIService
    ai_svc = ResearchAIService(db)
    research_svc = ResearchService(db)
    try:
        if space_id:
            col = ai_svc.synthesize_collection_for_space(uuid.UUID(space_id), collection_id)
        elif project_id == GLOBAL_RESEARCH_PROJECT_ID:
            current = research_svc.get_collection_any(collection_id)
            if current.research_space_id:
                col = ai_svc.synthesize_collection_for_space(current.research_space_id, collection_id)
            elif current.project_id:
                col = ai_svc.synthesize_collection(current.project_id, collection_id)
            else:
                raise ValidationError("AI synthesis requires the study to be linked to a space or project.")
        else:
            col = ai_svc.synthesize_collection(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI synthesis failed: {exc}") from exc
    return AISynthesisRead(ai_synthesis=col.ai_synthesis, ai_synthesis_at=col.ai_synthesis_at)


# ══════════════════════════════════════════════════════════════════════
# Read helpers
# ══════════════════════════════════════════════════════════════════════


def _research_space_read(item) -> ResearchSpaceRead:
    return ResearchSpaceRead(
        id=str(item.id),
        title=item.title,
        focus=item.focus,
        linked_project_id=str(item.linked_project_id) if item.linked_project_id else None,
        owner_user_id=str(item.owner_user_id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _collection_read(svc: ResearchService, item) -> CollectionRead:
    space_ids = [str(space_id) for space_id in svc.collection_space_ids(item.id)]
    return CollectionRead(
        id=str(item.id),
        research_space_id=str(item.research_space_id) if item.research_space_id else None,
        space_ids=space_ids,
        project_id=str(item.project_id) if item.project_id else None,
        title=item.title,
        description=item.description,
        hypothesis=item.hypothesis,
        open_questions=item.open_questions or [],
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        tags=item.tags or [],
        overleaf_url=item.overleaf_url,
        paper_motivation=item.paper_motivation,
        target_output_title=item.target_output_title,
        target_venue=item.target_venue,
        registration_deadline=item.registration_deadline,
        submission_deadline=item.submission_deadline,
        decision_date=item.decision_date,
        study_iterations=item.study_iterations or [],
        study_results=item.study_results or [],
        paper_authors=item.paper_authors or [],
        paper_questions=item.paper_questions or [],
        paper_claims=item.paper_claims or [],
        paper_sections=item.paper_sections or [],
        output_status=item.output_status.value if hasattr(item.output_status, "value") else str(item.output_status),
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        ai_synthesis=item.ai_synthesis,
        ai_synthesis_at=item.ai_synthesis_at,
        reference_count=svc._reference_count(item.id),
        note_count=svc._note_count(item.id),
        member_count=svc._member_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _member_read(data: dict) -> CollectionMemberRead:
    cm = data["item"]
    avatar_url = f"/auth/users/{cm.user_account_id}/avatar" if cm.user_account_id else None
    return CollectionMemberRead(
        id=str(cm.id),
        member_id=str(cm.user_account_id or cm.member_id),
        user_id=str(cm.user_account_id) if cm.user_account_id else None,
        member_name=data.get("member_name", ""),
        organization_short_name=data.get("organization_short_name", ""),
        avatar_url=avatar_url,
        role=cm.role.value if hasattr(cm.role, "value") else str(cm.role),
        created_at=cm.created_at,
        updated_at=cm.updated_at,
    )


def _meeting_read(item) -> CollectionMeetingRead:
    return CollectionMeetingRead(
        id=str(item.id),
        title=item.title,
        starts_at=item.starts_at,
        source_type=item.source_type.value if hasattr(item.source_type, "value") else str(item.source_type),
        summary=item.summary,
    )


def _study_chat_room_read(svc: ResearchService, room) -> StudyChatRoomRead:
    member_user_ids = [
        str(user_id)
        for user_id in svc.db.scalars(
            select(ProjectChatRoomMember.user_id).where(ProjectChatRoomMember.thread_id == room.id)
        ).all()
    ]
    return StudyChatRoomRead(
        project_id=str(room.project_id) if room.project_id else None,
        room_id=str(room.id),
        room_name=room.name,
        member_user_ids=member_user_ids,
    )


def _study_chat_room_key(collection_id: uuid.UUID) -> str:
    return f"study:{collection_id}"


def _study_chat_message_read(
    svc: ResearchService,
    collection_id: uuid.UUID,
    item,
    reaction_map: dict[uuid.UUID, list[dict]] | None = None,
    reply_lookup: dict[uuid.UUID, object] | None = None,
) -> StudyChatMessageRead:
    return StudyChatMessageRead(
        id=str(item.id),
        collection_id=str(collection_id),
        **build_scoped_chat_message_payload(
            item=item,
            get_display_name=svc.get_user_display_name,
            reaction_map=reaction_map,
            reply_lookup=reply_lookup,
            fallback_reply_lookup=svc.study_chat_message_lookup,
        ),
    )


def _reference_read(svc: ResearchService, item) -> ReferenceRead:
    bibliography = svc.get_bibliography_reference(item.bibliography_reference_id) if item.bibliography_reference_id else None
    return ReferenceRead(
        id=str(item.id),
        research_space_id=str(item.research_space_id) if item.research_space_id else None,
        project_id=str(item.project_id) if item.project_id else None,
        bibliography_reference_id=str(item.bibliography_reference_id) if item.bibliography_reference_id else None,
        collection_id=str(item.collection_id) if item.collection_id else None,
        title=item.title,
        authors=item.authors or [],
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        url=item.url,
        abstract=item.abstract,
        document_key=str(item.document_key) if item.document_key else None,
        tags=item.tags or [],
        bibliography_visibility=(
            bibliography.visibility.value if bibliography and hasattr(bibliography.visibility, "value")
            else str(bibliography.visibility) if bibliography and bibliography.visibility
            else None
        ),
        bibliography_attachment_filename=bibliography.attachment_filename if bibliography else None,
        bibliography_attachment_url=(
            f"/projects/{item.project_id}/research/bibliography/{item.bibliography_reference_id}/file"
            if bibliography and bibliography.attachment_path and item.project_id
            else None
        ),
        reading_status=item.reading_status.value if hasattr(item.reading_status, "value") else str(item.reading_status),
        added_by_member_id=str(item.added_by_member_id) if item.added_by_member_id else None,
        ai_summary=bibliography.ai_summary if bibliography and bibliography.ai_summary else item.ai_summary,
        ai_summary_at=bibliography.ai_summary_at if bibliography and bibliography.ai_summary_at else item.ai_summary_at,
        note_count=svc._ref_note_count(item.id),
        annotation_count=svc._ref_annotation_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _bibliography_read(svc: ResearchService, project_id: uuid.UUID, item: BibliographyReference) -> BibliographyReferenceRead:
    return BibliographyReferenceRead(
        id=str(item.id),
        source_project_id=str(item.source_project_id) if item.source_project_id else None,
        document_key=str(item.document_key) if item.document_key else None,
        title=item.title,
        authors=item.authors or [],
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        url=item.url,
        abstract=item.abstract,
        bibtex_raw=item.bibtex_raw,
        tags=svc.bibliography_tags_for_reference(item.id),
        concepts=svc.bibliography_concepts_for_reference(item.id),
        visibility=item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility),
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        attachment_filename=item.attachment_filename,
        document_status=svc.bibliography_document_status(item.id),
        warning=svc.bibliography_ingestion_warning(item.id),
        attachment_url=(
            f"/projects/{project_id}/research/bibliography/{item.id}/file"
            if item.attachment_path
            else None
        ),
        linked_project_count=svc.bibliography_link_count(item.id),
        ai_summary=item.ai_summary,
        ai_summary_at=item.ai_summary_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _bibliography_read_global(
    svc: ResearchService,
    item: BibliographyReference,
    *,
    note_counts: dict | None = None,
    reading_statuses: dict | None = None,
    semantic_evidence: list[dict] | None = None,
) -> BibliographyReferenceRead:
    return BibliographyReferenceRead(
        id=str(item.id),
        source_project_id=str(item.source_project_id) if item.source_project_id else None,
        document_key=str(item.document_key) if item.document_key else None,
        title=item.title,
        authors=item.authors or [],
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        url=item.url,
        abstract=item.abstract,
        bibtex_raw=item.bibtex_raw,
        tags=svc.bibliography_tags_for_reference(item.id),
        concepts=svc.bibliography_concepts_for_reference(item.id),
        visibility=item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility),
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        attachment_filename=item.attachment_filename,
        document_status=svc.bibliography_document_status(item.id),
        warning=svc.bibliography_ingestion_warning(item.id),
        attachment_url=(f"/bibliography/{item.id}/file" if (item.document_key or item.attachment_path) else None),
        linked_project_count=svc.bibliography_link_count(item.id),
        note_count=note_counts.get(item.id, 0) if note_counts else svc.bibliography_note_count(item.id),
        reading_status=reading_statuses.get(item.id, "unread") if reading_statuses else "unread",
        ai_summary=item.ai_summary,
        ai_summary_at=item.ai_summary_at,
        semantic_evidence=[
            BibliographySemanticEvidenceRead(
                text=str(entry.get("text") or ""),
                similarity=float(entry["similarity"]) if entry.get("similarity") is not None else None,
            )
            for entry in (semantic_evidence or [])
            if str(entry.get("text") or "").strip()
        ],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _bibliography_collection_read(svc: ResearchService, item) -> BibliographyCollectionRead:
    return BibliographyCollectionRead(
        id=str(item.id),
        title=item.title,
        description=item.description,
        visibility=item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility),
        owner_user_id=str(item.owner_user_id),
        reference_count=svc.bibliography_collection_reference_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _note_read(svc: ResearchService, item) -> NoteRead:
    author_name, author_avatar_url, author_user_id = svc.get_note_author(item)
    return NoteRead(
        id=str(item.id),
        research_space_id=str(item.research_space_id) if item.research_space_id else None,
        project_id=str(item.project_id) if item.project_id else None,
        collection_id=str(item.collection_id) if item.collection_id else None,
        author_member_id=str(item.author_member_id) if item.author_member_id else None,
        user_account_id=str(author_user_id) if author_user_id else None,
        author_name=author_name,
        author_avatar_url=author_avatar_url,
        title=item.title,
        content=item.content,
        lane=item.lane,
        note_type=item.note_type.value if hasattr(item.note_type, "value") else str(item.note_type),
        tags=item.tags or [],
        linked_reference_ids=svc.get_note_reference_ids(item.id),
        linked_file_ids=svc.get_note_file_ids(item.id),
        replies=[
            NoteReplyRead(
                id=str(reply.id),
                note_id=str(reply.note_id),
                user_account_id=str(reply.user_account_id) if reply.user_account_id else None,
                author_name=svc.get_user_display_name(reply.user_account_id) if reply.user_account_id else None,
                author_avatar_url=svc.get_user_avatar_url(reply.user_account_id),
                content=reply.content,
                linked_reference_ids=svc.get_note_reply_reference_ids(reply.id),
                created_at=reply.created_at,
                updated_at=reply.updated_at,
            )
            for reply in svc.list_note_replies(item.id)
        ],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _study_file_read(project_id: uuid.UUID, svc: ResearchService, item) -> StudyFileRead:
    return StudyFileRead(
        id=str(item.id),
        research_space_id=str(item.research_space_id) if item.research_space_id else None,
        project_id=str(item.project_id) if item.project_id else None,
        collection_id=str(item.collection_id),
        uploaded_by_user_id=str(item.uploaded_by_user_id) if item.uploaded_by_user_id else None,
        uploaded_by_name=svc.get_user_display_name(item.uploaded_by_user_id) if item.uploaded_by_user_id else None,
        original_filename=item.original_filename,
        mime_type=item.mime_type,
        file_size_bytes=item.file_size_bytes,
        download_url=f"/projects/{project_id}/research/collections/{item.collection_id}/files/{item.id}/download",
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
