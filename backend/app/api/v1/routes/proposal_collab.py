import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.auth import UserAccount
from app.models.proposal import ProjectProposalSection
from app.services.onboarding_service import NotFoundError
from app.services.proposal_collab_service import (
    AWARENESS_MESSAGE,
    SYNC_MESSAGE,
    ProposalCollabUnavailableError,
    proposal_collab_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class CollabRoom:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, sender: WebSocket | None, payload: bytes) -> None:
        dead: list[WebSocket] = []
        for socket in list(self.connections):
            if sender is not None and socket is sender:
                continue
            try:
                await socket.send_bytes(payload)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.disconnect(socket)


class CollabHub:
    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, CollabRoom] = {}
        self._presence: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)

    def get_or_create_room(self, section_id: uuid.UUID) -> CollabRoom:
        room = self._rooms.get(section_id)
        if room is None:
            room = CollabRoom()
            self._rooms[section_id] = room
        return room

    def remove_connection(self, section_id: uuid.UUID, websocket: WebSocket) -> None:
        room = self._rooms.get(section_id)
        if not room:
            return
        room.disconnect(websocket)
        if not room.connections:
            self._rooms.pop(section_id, None)

    def user_join(self, section_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        key = str(user_id)
        count = self._presence[section_id].get(key, 0)
        self._presence[section_id][key] = count + 1
        return count == 0

    def user_leave(self, section_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        key = str(user_id)
        room_presence = self._presence.get(section_id, {})
        count = room_presence.get(key, 0)
        if count <= 1:
            room_presence.pop(key, None)
            if not room_presence:
                self._presence.pop(section_id, None)
            return count > 0
        room_presence[key] = count - 1
        return False


hub = CollabHub()


@router.websocket("/projects/{project_id}/proposal-sections/{section_id}/ws")
async def proposal_section_ws(
    websocket: WebSocket,
    project_id: uuid.UUID,
    section_id: uuid.UUID,
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
        try:
            user = db.get(UserAccount, user_id)
            if not user:
                raise NotFoundError("User not found.")
            section = db.scalar(
                select(ProjectProposalSection).where(
                    ProjectProposalSection.id == section_id,
                    ProjectProposalSection.project_id == project_id,
                )
            )
            if not section:
                raise NotFoundError("Proposal section not found.")
        except NotFoundError:
            await websocket.close(code=4403, reason="Forbidden")
            return

        try:
            initial_sync = proposal_collab_service.build_sync_message(db, section_id)
        except ValueError:
            await websocket.close(code=4404, reason="Proposal section not found")
            return
        except ProposalCollabUnavailableError:
            await websocket.close(code=1013, reason="Collaboration dependency unavailable")
            return

    room = hub.get_or_create_room(section_id)
    await room.connect(websocket)
    hub.user_join(section_id, user_id)
    logger.info(
        "Proposal collab connected: project_id=%s section_id=%s user_id=%s connections=%s",
        project_id,
        section_id,
        user_id,
        len(room.connections),
    )

    try:
        # pycrdt's create_sync_message / handle_sync_message already include
        # the YMessageType.SYNC prefix byte — don't add another one.
        await websocket.send_bytes(initial_sync)
        while True:
            payload = await websocket.receive_bytes()
            if not payload:
                continue
            message_type = payload[0]
            if message_type == SYNC_MESSAGE:
                logger.info(
                    "Proposal collab sync message: section_id=%s user_id=%s subtype=%s size=%s",
                    section_id,
                    user_id,
                    payload[1] if len(payload) > 1 else None,
                    len(payload),
                )
                with SessionLocal() as db:
                    response = proposal_collab_service.handle_sync_message(db, section_id, payload)
                if response:
                    await websocket.send_bytes(response)
                if len(payload) > 1 and payload[1] in {1, 2}:
                    logger.info(
                        "Proposal collab broadcast sync: section_id=%s sender=%s peers=%s subtype=%s",
                        section_id,
                        user_id,
                        max(0, len(room.connections) - 1),
                        payload[1],
                    )
                    await room.broadcast(websocket, payload)
                continue
            if message_type == AWARENESS_MESSAGE:
                logger.info(
                    "Proposal collab awareness: section_id=%s user_id=%s size=%s peers=%s",
                    section_id,
                    user_id,
                    len(payload),
                    max(0, len(room.connections) - 1),
                )
                await room.broadcast(websocket, payload)
                continue
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove_connection(section_id, websocket)
        became_offline = hub.user_leave(section_id, user_id)
        logger.info(
            "Proposal collab disconnected: project_id=%s section_id=%s user_id=%s remaining=%s",
            project_id,
            section_id,
            user_id,
            len(room.connections),
        )
        if became_offline:
            try:
                proposal_collab_service.persist(section_id)
            except ProposalCollabUnavailableError:
                pass
