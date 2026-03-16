import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.document import DocumentChunk, DocumentStatus, ProjectDocument
from app.services.onboarding_service import NotFoundError
from app.services.text_extraction import chunk_text, extract_text

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 1000


@dataclass
class ReindexResult:
    document_id: uuid.UUID
    status: str
    chunks_indexed: int
    error: str | None = None


class DocumentIngestionService:
    """
    Handles document text extraction and chunk indexing lifecycle.
    """

    def __init__(self, db: Session):
        self.db = db

    def mark_for_reindex(self, project_id: uuid.UUID, document_id: uuid.UUID) -> ProjectDocument:
        document = self._get_document(project_id, document_id)
        document.status = DocumentStatus.uploaded.value
        document.ingestion_error = None
        document.indexed_at = None
        self.db.commit()
        self.db.refresh(document)
        return document

    def reindex_document(self, project_id: uuid.UUID, document_id: uuid.UUID) -> ReindexResult:
        document = self._get_document(project_id, document_id)
        try:
            text = extract_text(Path(document.storage_uri), document.mime_type)
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("Document contains no extractable text content.")

            self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
            for index, chunk in enumerate(chunks):
                self.db.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=index,
                        content=chunk,
                        embedding=None,
                    )
                )
            document.status = DocumentStatus.indexed.value
            document.indexed_at = datetime.now(timezone.utc)
            document.ingestion_error = None
            self.db.commit()

            # Best-effort embedding generation
            try:
                from app.services.embedding_service import EmbeddingService
                EmbeddingService(self.db).embed_document_chunks(document.id)
                self.db.commit()
            except Exception as exc:
                logger.warning("Embedding generation failed for document %s: %s", document.id, exc)

            return ReindexResult(document_id=document.id, status=document.status, chunks_indexed=len(chunks))
        except Exception as exc:  # pragma: no cover - branch exercised indirectly by API error handling
            self.db.rollback()
            failed_doc = self._get_document(project_id, document_id)
            failed_doc.status = DocumentStatus.failed.value
            failed_doc.indexed_at = None
            failed_doc.ingestion_error = str(exc)[:MAX_ERROR_LENGTH]
            self.db.commit()
            return ReindexResult(
                document_id=failed_doc.id,
                status=failed_doc.status,
                chunks_indexed=0,
                error=failed_doc.ingestion_error,
            )

    def _get_document(self, project_id: uuid.UUID, document_id: uuid.UUID) -> ProjectDocument:
        document = self.db.scalar(
            select(ProjectDocument).where(ProjectDocument.project_id == project_id, ProjectDocument.id == document_id)
        )
        if not document:
            raise NotFoundError("Document version not found in project.")
        return document

def run_document_reindex_job(project_id: uuid.UUID, document_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        DocumentIngestionService(db).reindex_document(project_id, document_id)
    finally:
        db.close()
