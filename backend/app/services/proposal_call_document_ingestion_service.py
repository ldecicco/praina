import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.proposal import ProposalCallLibraryDocument, ProposalCallLibraryDocumentChunk
from app.services.onboarding_service import NotFoundError
from app.services.text_extraction import chunk_text, extract_text

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 1000
STORAGE_ROOT = Path(getattr(settings, "storage_root", "storage"))


@dataclass
class CallDocumentReindexResult:
    document_id: uuid.UUID
    status: str
    chunks_indexed: int
    error: str | None = None


class ProposalCallDocumentIngestionService:
    def __init__(self, db: Session):
        self.db = db

    def mark_for_reindex(self, library_entry_id: uuid.UUID, document_id: uuid.UUID) -> ProposalCallLibraryDocument:
        document = self._get_document(library_entry_id, document_id)
        document.indexing_status = "uploaded"
        document.ingestion_error = None
        document.indexed_at = None
        self.db.commit()
        self.db.refresh(document)
        return document

    def reindex_document(self, library_entry_id: uuid.UUID, document_id: uuid.UUID) -> CallDocumentReindexResult:
        document = self._get_document(library_entry_id, document_id)
        try:
            document.indexing_status = "processing"
            document.ingestion_error = None
            self.db.commit()

            text = extract_text(STORAGE_ROOT / document.storage_path, document.mime_type)
            chunks = chunk_text(text)
            if not chunks:
                raise ValueError("Document contains no extractable text content.")

            self.db.execute(
                delete(ProposalCallLibraryDocumentChunk).where(ProposalCallLibraryDocumentChunk.document_id == document.id)
            )
            for index, chunk in enumerate(chunks):
                self.db.add(
                    ProposalCallLibraryDocumentChunk(
                        document_id=document.id,
                        chunk_index=index,
                        content=chunk,
                        embedding=None,
                    )
                )

            document.extracted_text = text
            document.indexing_status = "indexed"
            document.indexed_at = datetime.now(timezone.utc)
            document.ingestion_error = None
            self.db.commit()

            try:
                from app.services.embedding_service import EmbeddingService

                EmbeddingService(self.db).embed_call_document_chunks(document.id)
                self.db.commit()
            except Exception as exc:
                logger.warning("Embedding generation failed for call document %s: %s", document.id, exc)

            return CallDocumentReindexResult(document_id=document.id, status=document.indexing_status, chunks_indexed=len(chunks))
        except Exception as exc:
            self.db.rollback()
            failed_doc = self._get_document(library_entry_id, document_id)
            failed_doc.indexing_status = "failed"
            failed_doc.indexed_at = None
            failed_doc.ingestion_error = str(exc)[:MAX_ERROR_LENGTH]
            self.db.commit()
            return CallDocumentReindexResult(
                document_id=failed_doc.id,
                status=failed_doc.indexing_status,
                chunks_indexed=0,
                error=failed_doc.ingestion_error,
            )

    def _get_document(self, library_entry_id: uuid.UUID, document_id: uuid.UUID) -> ProposalCallLibraryDocument:
        document = self.db.scalar(
            select(ProposalCallLibraryDocument).where(
                ProposalCallLibraryDocument.library_entry_id == library_entry_id,
                ProposalCallLibraryDocument.id == document_id,
            )
        )
        if not document:
            raise NotFoundError("Call document not found.")
        return document


def run_call_document_reindex_job(library_entry_id: uuid.UUID, document_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        ProposalCallDocumentIngestionService(db).reindex_document(library_entry_id, document_id)
    finally:
        db.close()
