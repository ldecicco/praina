import json
import asyncio
import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.agents.chat_assistant_agent import ChatAssistantAgent
from app.core.security import decode_token, get_current_user
from app.db.session import SessionLocal, get_db
from app.models.auth import UserAccount
from app.api.v1.routes.chat_serialization import build_scoped_chat_message_payload
from app.schemas.auth import MembershipListRead, MembershipRead, MembershipUpsertRequest
from app.schemas.project_chat import (
    ChatMessageCreateRequest,
    ChatMessageListRead,
    ChatMessageReactionToggleRequest,
    ChatMessageRead,
    ChatRoomCreateRequest,
    ChatRoomListRead,
    ChatRoomRead,
    ProjectBroadcastCreateRequest,
    ProjectBroadcastListRead,
    ProjectBroadcastRead,
    RoomMemberAddRequest,
)
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.project_chat_service import ProjectChatService
from app.services.project_broadcast_service import ProjectBroadcastService
from app.services.project_chatops_service import ProjectChatOpsService

router = APIRouter()
logger = logging.getLogger(__name__)


class RoomHub:
    def __init__(self):
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
        dead: list[WebSocket] = []
        text = json.dumps(payload, ensure_ascii=True)
        for socket in sockets:
            try:
                await socket.send_text(text)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.disconnect(room_key, socket)


hub = RoomHub()


@router.get("/{project_id}/memberships", response_model=MembershipListRead)
def list_memberships(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipListRead:
    service = AuthService(db)
    try:
        memberships = service.list_project_memberships_for_actor(project_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return MembershipListRead(
        items=[_membership_read(item) for item in memberships],
        page=1,
        page_size=max(1, len(memberships)),
        total=len(memberships),
    )


@router.post("/{project_id}/memberships", response_model=MembershipRead)
def upsert_membership(
    project_id: uuid.UUID,
    payload: MembershipUpsertRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipRead:
    service = AuthService(db)
    try:
        membership = service.upsert_membership(
            project_id=project_id,
            actor_user_id=current_user.id,
            user_id=uuid.UUID(payload.user_id),
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID in payload.") from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _membership_read(membership)


@router.get("/{project_id}/rooms", response_model=ChatRoomListRead)
def list_rooms(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatRoomListRead:
    service = ProjectChatService(db)
    try:
        rooms = service.list_rooms(project_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ChatRoomListRead(
        items=[_room_read(service, room) for room in rooms],
        page=1,
        page_size=max(1, len(rooms)),
        total=len(rooms),
    )


@router.post("/{project_id}/rooms", response_model=ChatRoomRead)
def create_room(
    project_id: uuid.UUID,
    payload: ChatRoomCreateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatRoomRead:
    service = ProjectChatService(db)
    try:
        room = service.create_room(
            project_id=project_id,
            user_id=current_user.id,
            name=payload.name,
            description=payload.description,
            scope_type=payload.scope_type,
            scope_ref_id=uuid.UUID(payload.scope_ref_id) if payload.scope_ref_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scope_ref_id UUID.") from exc
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _room_read(service, room)


@router.get("/{project_id}/broadcasts", response_model=ProjectBroadcastListRead)
def list_project_broadcasts(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectBroadcastListRead:
    service = ProjectBroadcastService(db)
    try:
        items, total = service.list_broadcasts(project_id, current_user.id, page, page_size)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    broadcast_ids = [item.id for item in items]
    author_ids = [item.author_user_id for item in items]
    recipient_counts = service.recipient_count_by_broadcast(broadcast_ids)
    authors = service.author_lookup(author_ids)
    return ProjectBroadcastListRead(
        items=[_broadcast_read(item, authors, recipient_counts) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/broadcasts", response_model=ProjectBroadcastRead)
def create_project_broadcast(
    project_id: uuid.UUID,
    payload: ProjectBroadcastCreateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectBroadcastRead:
    service = ProjectBroadcastService(db)
    try:
        item = service.create_broadcast(
            project_id,
            current_user.id,
            title=payload.title,
            body=payload.body,
            severity=payload.severity,
            deliver_telegram=payload.deliver_telegram,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    recipient_counts = service.recipient_count_by_broadcast([item.id])
    authors = service.author_lookup([item.author_user_id])
    return _broadcast_read(item, authors, recipient_counts)


@router.post("/{project_id}/rooms/{room_id}/members", response_model=ChatRoomRead)
def add_room_member(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: RoomMemberAddRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatRoomRead:
    service = ProjectChatService(db)
    try:
        target_user_id = uuid.UUID(payload.user_id)
        service.add_room_member(project_id, room_id, current_user.id, target_user_id)
        room = service.get_room(project_id, room_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id UUID.") from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _room_read(service, room)


@router.delete("/{project_id}/rooms/{room_id}/members/{user_id}", response_model=ChatRoomRead)
def remove_room_member(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatRoomRead:
    service = ProjectChatService(db)
    try:
        service.remove_room_member(project_id, room_id, current_user.id, user_id)
        room = service.get_room(project_id, room_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _room_read(service, room)


@router.get("/{project_id}/rooms/{room_id}/messages", response_model=ChatMessageListRead)
def list_messages(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageListRead:
    service = ProjectChatService(db)
    try:
        items, total = service.list_messages(project_id, room_id, current_user.id, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    message_ids = [item.id for item in items]
    reaction_map = service.reaction_summary_by_message(message_ids)
    reply_lookup = service.message_lookup(
        [item.reply_to_message_id for item in items if item.reply_to_message_id]
    )
    return ChatMessageListRead(
        items=[_message_read(service, project_id, room_id, item, reaction_map, reply_lookup) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/rooms/{room_id}/messages", response_model=ChatMessageRead)
async def create_message(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: ChatMessageCreateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageRead:
    service = ProjectChatService(db)
    try:
        reply_to_message_id = uuid.UUID(payload.reply_to_message_id) if payload.reply_to_message_id else None
        message = service.create_message(
            project_id,
            room_id,
            current_user.id,
            payload.content,
            reply_to_message_id=reply_to_message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reply_to_message_id UUID.") from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    reaction_map = service.reaction_summary_by_message([message.id])
    reply_lookup = service.message_lookup([message.reply_to_message_id] if message.reply_to_message_id else [])
    rendered = _message_read(service, project_id, room_id, message, reaction_map, reply_lookup)
    await hub.broadcast(_room_key(project_id, room_id), {"event": "message", "message": rendered.model_dump(mode="json")})
    asyncio.create_task(_maybe_generate_bot_reply(project_id, room_id, current_user.id, payload.content))
    return rendered


@router.post("/{project_id}/rooms/{room_id}/messages/{message_id}/reactions", response_model=ChatMessageRead)
async def toggle_message_reaction(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ChatMessageReactionToggleRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageRead:
    service = ProjectChatService(db)
    try:
        message = service.toggle_message_reaction(project_id, room_id, message_id, current_user.id, payload.emoji)
        fresh = service.get_message(project_id, room_id, current_user.id, message.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    reaction_map = service.reaction_summary_by_message([fresh.id])
    reply_lookup = service.message_lookup([fresh.reply_to_message_id] if fresh.reply_to_message_id else [])
    rendered = _message_read(service, project_id, room_id, fresh, reaction_map, reply_lookup)
    await hub.broadcast(
        _room_key(project_id, room_id),
        {"event": "message_updated", "message": rendered.model_dump(mode="json")},
    )
    return rendered


@router.websocket("/{project_id}/rooms/{room_id}/ws")
async def websocket_room(
    websocket: WebSocket,
    project_id: uuid.UUID,
    room_id: uuid.UUID,
) -> None:
    token = websocket.query_params.get("token")
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
        service = ProjectChatService(db)
        try:
            # Validation side effect: role and room access checks.
            service.list_messages(project_id, room_id, user_id, page=1, page_size=1)
            user = db.get(UserAccount, user_id)
            if not user:
                raise NotFoundError("User not found.")
        except (NotFoundError, ValidationError):
            await websocket.close(code=4403, reason="Forbidden")
            return
        display_name = user.display_name

    room_key = _room_key(project_id, room_id)
    await hub.connect(room_key, websocket)
    became_online = hub.user_join(room_key, user_id)
    await websocket.send_text(json.dumps({"event": "presence_snapshot", "user_ids": hub.online_user_ids(room_key)}))
    if became_online:
        await hub.broadcast(
            room_key,
            {"event": "presence", "status": "joined", "user_id": str(user_id), "display_name": display_name},
        )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                content = str(payload.get("content", ""))
                reply_to_message_id = payload.get("reply_to_message_id")
                reply_to_uuid = uuid.UUID(reply_to_message_id) if reply_to_message_id else None
            except Exception:
                await websocket.send_text(json.dumps({"event": "error", "detail": "Invalid message payload."}))
                continue

            with SessionLocal() as db:
                service = ProjectChatService(db)
                try:
                    message = service.create_message(
                        project_id,
                        room_id,
                        user_id,
                        content,
                        reply_to_message_id=reply_to_uuid,
                    )
                except (NotFoundError, ValidationError) as exc:
                    await websocket.send_text(json.dumps({"event": "error", "detail": str(exc)}))
                    continue
                reaction_map = service.reaction_summary_by_message([message.id])
                reply_lookup = service.message_lookup([message.reply_to_message_id] if message.reply_to_message_id else [])
                rendered = _message_read(service, project_id, room_id, message, reaction_map, reply_lookup)
            await hub.broadcast(room_key, {"event": "message", "message": rendered.model_dump(mode="json")})
            asyncio.create_task(_maybe_generate_bot_reply(project_id, room_id, user_id, content))
    except WebSocketDisconnect:
        hub.disconnect(room_key, websocket)
        became_offline = hub.user_leave(room_key, user_id)
        if became_offline:
            await hub.broadcast(
                room_key,
                {"event": "presence", "status": "left", "user_id": str(user_id), "display_name": display_name},
            )


def _room_key(project_id: uuid.UUID, room_id: uuid.UUID) -> str:
    return f"{project_id}:{room_id}"


async def _maybe_generate_bot_reply(project_id: uuid.UUID, room_id: uuid.UUID, sender_user_id: uuid.UUID, raw_content: str) -> None:
    room_key = _room_key(project_id, room_id)
    stream_id = str(uuid.uuid4())
    try:
        if not ProjectChatService.has_bot_mention(raw_content):
            return

        await hub.broadcast(room_key, {"event": "bot_status", "status": "start", "stream_id": stream_id})

        with SessionLocal() as db:
            service = ProjectChatService(db)
            prompt = ProjectChatService.strip_bot_mentions(raw_content)
            if not prompt:
                prompt = "Help with the current project chat thread."
            project_context = service.project_context_for_agent(project_id)
            chatops = ProjectChatOpsService(db)
            reply = await asyncio.to_thread(
                chatops.handle_mentioned_message,
                project_id=project_id,
                room_id=room_id,
                sender_user_id=sender_user_id,
                prompt=prompt,
                project_context=project_context,
            )
            citations: list[dict] = []
            if reply is None:
                assistant_context = ChatService(db).project_context_for_assistant(project_id)
                recent_messages = service.recent_messages_for_agent(project_id, room_id, limit=12)
                citations = service.retrieve_citations(project_id, prompt)
                agent = ChatAssistantAgent()
                reply = await asyncio.to_thread(
                    agent.generate,
                    user_prompt=prompt,
                    project_context=assistant_context,
                    recent_messages=recent_messages,
                    evidence=citations,
                )
        if not reply:
            with SessionLocal() as db:
                service = ProjectChatService(db)
                reply = service.compose_fallback_reply(project_id, prompt, project_context, citations)

        for chunk in _stream_chunks(reply):
            await hub.broadcast(room_key, {"event": "bot_stream", "stream_id": stream_id, "chunk": chunk})
            await asyncio.sleep(0.015)

        with SessionLocal() as db:
            service = ProjectChatService(db)
            try:
                bot_message = service.create_bot_message(project_id, room_id, reply)
            except (NotFoundError, ValidationError):
                await hub.broadcast(room_key, {"event": "bot_status", "status": "stop", "stream_id": stream_id})
                return
            reaction_map = service.reaction_summary_by_message([bot_message.id])
            rendered = _message_read(service, project_id, room_id, bot_message, reaction_map, {})

        await hub.broadcast(room_key, {"event": "message", "message": rendered.model_dump(mode="json")})
        await hub.broadcast(room_key, {"event": "bot_status", "status": "stop", "stream_id": stream_id})
    except Exception:
        logger.exception("Project chat bot reply generation failed for project=%s room=%s", project_id, room_id)
        await hub.broadcast(room_key, {"event": "bot_status", "status": "stop", "stream_id": stream_id})
        return


def _stream_chunks(text: str) -> list[str]:
    # Chunk by short token groups for responsive UI streaming.
    words = text.split()
    if not words:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(current) >= 4:
            chunks.append(" ".join(current) + " ")
            current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


def _membership_read(item) -> MembershipRead:
    return MembershipRead(
        id=str(item.id),
        project_id=str(item.project_id),
        user_id=str(item.user_id),
        role=item.role,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _room_read(service: ProjectChatService, item) -> ChatRoomRead:
    return ChatRoomRead(
        id=str(item.id),
        project_id=str(item.project_id),
        name=item.name,
        description=item.description,
        scope_type=item.scope_type,
        scope_ref_id=str(item.scope_ref_id) if item.scope_ref_id else None,
        is_archived=item.is_archived,
        member_user_ids=[str(user_id) for user_id in service.room_member_ids(item.id)],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _message_read(
    service: ProjectChatService,
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    item,
    reaction_map: dict[uuid.UUID, list[dict]] | None = None,
    reply_lookup: dict[uuid.UUID, object] | None = None,
) -> ChatMessageRead:
    return ChatMessageRead(
        id=str(item.id),
        project_id=str(project_id),
        room_id=str(room_id),
        **build_scoped_chat_message_payload(
            item=item,
            get_display_name=service.get_user_display_name,
            reaction_map=reaction_map,
            reply_lookup=reply_lookup,
            fallback_reply_lookup=service.message_lookup,
        ),
    )


def _broadcast_read(item, authors: dict[uuid.UUID, UserAccount], recipient_counts: dict[uuid.UUID, int]) -> ProjectBroadcastRead:
    author = authors.get(item.author_user_id)
    return ProjectBroadcastRead(
        id=str(item.id),
        project_id=str(item.project_id) if item.project_id else None,
        lab_id=str(item.lab_id) if item.lab_id else None,
        author_user_id=str(item.author_user_id),
        author_display_name=author.display_name if author else "Unknown",
        title=item.title,
        body=item.body,
        severity=item.severity,
        deliver_telegram=item.deliver_telegram,
        recipient_count=int(recipient_counts.get(item.id, 0)),
        sent_at=item.sent_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
