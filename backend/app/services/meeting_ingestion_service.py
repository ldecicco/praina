"""Meeting content indexing and best-effort action extraction."""

import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.meeting import MeetingChunk, MeetingRecord
from app.services.action_item_service import ActionItemService
from app.services.text_extraction import chunk_text, extract_text

logger = logging.getLogger(__name__)


class MeetingIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def index_meeting(self, meeting: MeetingRecord) -> int:
        """Chunk the meeting's content_text, replace existing chunks, and mark as indexed.

        Returns the number of chunks created.
        """
        text = meeting.content_text or ""
        chunks = chunk_text(text)

        # Delete old chunks
        self.db.execute(delete(MeetingChunk).where(MeetingChunk.meeting_id == meeting.id))

        for index, chunk_content in enumerate(chunks):
            self.db.add(
                MeetingChunk(
                    meeting_id=meeting.id,
                    chunk_index=index,
                    content=chunk_content,
                    embedding=None,
                )
            )

        meeting.indexing_status = "indexed" if chunks else "empty"
        self.db.commit()

        # Best-effort embedding generation
        if chunks:
            try:
                from app.services.embedding_service import EmbeddingService
                EmbeddingService(self.db).embed_meeting_chunks(meeting.id)
                self.db.commit()
            except Exception as exc:
                logger.warning("Embedding generation failed for meeting %s: %s", meeting.id, exc)

        self._auto_extract_actions(meeting)
        self.db.refresh(meeting)
        return len(chunks)

    def extract_and_index_from_file(
        self,
        meeting: MeetingRecord,
        file_path: Path,
        mime_type: str,
    ) -> int:
        """Extract text from a file, set it as the meeting's content, then index.

        Returns the number of chunks created.
        """
        text = extract_text(file_path, mime_type)
        if not text.strip():
            raise ValueError("Could not extract any text from the uploaded file.")
        meeting.content_text = text.strip()
        self.db.flush()
        return self.index_meeting(meeting)

    def _auto_extract_actions(self, meeting: MeetingRecord) -> None:
        if not (meeting.content_text or "").strip():
            return
        try:
            service = ActionItemService(self.db)
            result = service._extract_from_content(meeting.project_id, meeting.content_text)
            if not result:
                logger.warning("Meeting action extraction returned no result for meeting %s", meeting.id)
                return
            meeting.summary = result.get("summary")
            service.bulk_create(meeting.project_id, meeting.id, result.get("action_items", []), "assistant")
        except Exception as exc:  # pragma: no cover - best-effort logging path
            logger.warning("Meeting action extraction failed for meeting %s: %s", meeting.id, exc)
