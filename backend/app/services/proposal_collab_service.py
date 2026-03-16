import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.proposal import ProjectProposalSection

logger = logging.getLogger(__name__)

SYNC_MESSAGE = 0
AWARENESS_MESSAGE = 1


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _LoadedDoc:
    doc: object
    last_touched_at: datetime = field(default_factory=_utcnow)
    dirty: bool = False


class ProposalCollabUnavailableError(RuntimeError):
    pass


class ProposalCollabService:
    def __init__(self) -> None:
        self._docs: dict[uuid.UUID, _LoadedDoc] = {}
        self._listeners: dict[uuid.UUID, set[Callable[[bytes], None]]] = defaultdict(set)
        self._lock = Lock()

    def _require_pycrdt(self):
        try:
            from pycrdt import Doc
            from pycrdt import create_sync_message, create_update_message, handle_sync_message
        except ImportError as exc:
            raise ProposalCollabUnavailableError(
                "Proposal collaboration requires the optional backend dependency 'pycrdt'."
            ) from exc
        return Doc, create_sync_message, create_update_message, handle_sync_message

    def is_available(self) -> bool:
        try:
            self._require_pycrdt()
        except ProposalCollabUnavailableError:
            return False
        return True

    def load_or_create(self, db: Session, section_id: uuid.UUID):
        _, _, _, _ = self._require_pycrdt()
        with self._lock:
            cached = self._docs.get(section_id)
            if cached:
                cached.last_touched_at = _utcnow()
                return cached.doc

            section = db.get(ProjectProposalSection, section_id)
            if not section:
                raise ValueError("Proposal section not found.")

            Doc, _, create_update_message, _ = self._require_pycrdt()
            doc = Doc()
            loaded = _LoadedDoc(doc=doc, last_touched_at=_utcnow(), dirty=False)
            self._docs[section_id] = loaded

            def _on_update(event) -> None:
                loaded.last_touched_at = _utcnow()
                loaded.dirty = True
                update_message = bytes(create_update_message(event.update))
                for listener in list(self._listeners.get(section_id, set())):
                    try:
                        listener(update_message)
                    except Exception:
                        logger.exception("Failed to notify proposal collab listener for section %s", section_id)

            doc.observe(_on_update)
            if section.yjs_state:
                doc.apply_update(section.yjs_state)
            return doc

    def build_sync_message(self, db: Session, section_id: uuid.UUID) -> bytes:
        doc = self.load_or_create(db, section_id)
        _, create_sync_message, _, _ = self._require_pycrdt()
        message = bytes(create_sync_message(doc))
        if message and message[0] == SYNC_MESSAGE:
            return message
        return bytes([SYNC_MESSAGE]) + message

    def handle_sync_message(self, db: Session, section_id: uuid.UUID, payload: bytes) -> bytes | None:
        doc = self.load_or_create(db, section_id)
        _, _, _, handle_sync_message = self._require_pycrdt()
        response = self._apply_sync_message(handle_sync_message, payload, doc)
        loaded = self._docs[section_id]
        loaded.last_touched_at = _utcnow()
        loaded.dirty = True
        if response is None:
            return None
        encoded = bytes(response)
        if encoded and encoded[0] == SYNC_MESSAGE:
            return encoded
        return bytes([SYNC_MESSAGE]) + encoded

    def _apply_sync_message(self, handle_sync_message, payload: bytes, doc: object):
        if not payload:
            return None
        if payload[0] == SYNC_MESSAGE:
            try:
                return handle_sync_message(payload, doc)
            except Exception:
                logger.debug("Retrying pycrdt sync handling with stripped sync prefix", exc_info=True)
                return handle_sync_message(payload[1:], doc)
        try:
            return handle_sync_message(payload, doc)
        except Exception:
            logger.debug("Retrying pycrdt sync handling with prefixed sync byte", exc_info=True)
            return handle_sync_message(bytes([SYNC_MESSAGE]) + payload, doc)

    def register_listener(self, section_id: uuid.UUID, listener: Callable[[bytes], None]) -> None:
        self._listeners[section_id].add(listener)

    def unregister_listener(self, section_id: uuid.UUID, listener: Callable[[bytes], None]) -> None:
        listeners = self._listeners.get(section_id)
        if not listeners:
            return
        listeners.discard(listener)
        if not listeners:
            self._listeners.pop(section_id, None)

    def invalidate(self, section_id: uuid.UUID) -> None:
        with self._lock:
            self._docs.pop(section_id, None)

    def persist(self, section_id: uuid.UUID) -> None:
        _, _, _, _ = self._require_pycrdt()
        with self._lock:
            loaded = self._docs.get(section_id)
            if not loaded or not loaded.dirty:
                return
            state = bytes(loaded.doc.get_update())
            loaded.dirty = False

        with SessionLocal() as db:
            section = db.get(ProjectProposalSection, section_id)
            if not section:
                return
            section.yjs_state = state
            db.commit()

    def cleanup_idle(self, *, max_age: timedelta = timedelta(minutes=30)) -> None:
        cutoff = _utcnow() - max_age
        stale_ids: list[uuid.UUID] = []
        with self._lock:
            for section_id, loaded in self._docs.items():
                if loaded.last_touched_at < cutoff:
                    stale_ids.append(section_id)
        for section_id in stale_ids:
            self.persist(section_id)
            with self._lock:
                self._docs.pop(section_id, None)

    async def persist_loop(self, *, interval_seconds: int = 5) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            for section_id in list(self._docs):
                try:
                    self.persist(section_id)
                except ProposalCollabUnavailableError:
                    return
                except Exception:
                    logger.exception("Failed to persist proposal collab state for section %s", section_id)
            try:
                self.cleanup_idle()
            except ProposalCollabUnavailableError:
                return
            except Exception:
                logger.exception("Failed to clean up proposal collab documents")


proposal_collab_service = ProposalCollabService()
