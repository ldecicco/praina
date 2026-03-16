"""Embedding service — generates vector embeddings via Ollama and stores them in pgvector columns."""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import DocumentChunk, ProjectDocument
from app.models.meeting import MeetingChunk, MeetingRecord
from app.models.proposal import ProposalCallLibraryDocumentChunk
from app.models.research import ResearchChunk

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates embeddings using Ollama's /api/embed endpoint and writes them to pgvector columns."""

    def __init__(self, db: Session):
        self.db = db
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_embedding_model
        self.dimension = settings.embedding_dimension
        self.batch_size = max(1, settings.embedding_batch_size)
        self.timeout_seconds = max(30, settings.embedding_http_timeout_seconds)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Call Ollama /api/embed with a batch of texts and return embedding vectors."""
        if not texts:
            return []
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
        embeddings = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        return embeddings

    def embed_document_chunks(self, document_id: uuid.UUID) -> int:
        """Generate and store embeddings for all chunks of a document. Returns count embedded."""
        chunks = self.db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()
        if not chunks:
            return 0
        return self._embed_chunk_batch(chunks)

    def embed_meeting_chunks(self, meeting_id: uuid.UUID) -> int:
        """Generate and store embeddings for all chunks of a meeting. Returns count embedded."""
        chunks = self.db.scalars(
            select(MeetingChunk)
            .where(MeetingChunk.meeting_id == meeting_id)
            .order_by(MeetingChunk.chunk_index)
        ).all()
        if not chunks:
            return 0
        return self._embed_chunk_batch(chunks)

    def embed_research_chunks(self, project_id: uuid.UUID) -> int:
        """Generate and store embeddings for all unembedded research chunks in a project."""
        chunks = self.db.scalars(
            select(ResearchChunk)
            .where(
                ResearchChunk.project_id == project_id,
                ResearchChunk.embedding.is_(None),
            )
            .order_by(ResearchChunk.source_id, ResearchChunk.chunk_index)
        ).all()
        if not chunks:
            return 0
        return self._embed_chunk_batch(chunks)

    def embed_call_document_chunks(self, document_id: uuid.UUID) -> int:
        chunks = self.db.scalars(
            select(ProposalCallLibraryDocumentChunk)
            .where(ProposalCallLibraryDocumentChunk.document_id == document_id)
            .order_by(ProposalCallLibraryDocumentChunk.chunk_index)
        ).all()
        if not chunks:
            return 0
        return self._embed_chunk_batch(chunks)

    def embed_all_unembedded(self, project_id: uuid.UUID) -> dict[str, int]:
        """Backfill embeddings for all chunks in a project that have embedding=NULL."""
        doc_count = self._embed_unembedded_document_chunks(project_id)
        meeting_count = self._embed_unembedded_meeting_chunks(project_id)
        research_count = self.embed_research_chunks(project_id)
        return {"documents": doc_count, "meetings": meeting_count, "research": research_count}

    def _embed_unembedded_document_chunks(self, project_id: uuid.UUID) -> int:
        chunks = self.db.scalars(
            select(DocumentChunk)
            .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
            .where(
                ProjectDocument.project_id == project_id,
                DocumentChunk.embedding.is_(None),
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        ).all()
        if not chunks:
            return 0
        return self._embed_chunk_batch(chunks)

    def _embed_unembedded_meeting_chunks(self, project_id: uuid.UUID) -> int:
        chunks = self.db.scalars(
            select(MeetingChunk)
            .join(MeetingRecord, MeetingChunk.meeting_id == MeetingRecord.id)
            .where(
                MeetingRecord.project_id == project_id,
                MeetingChunk.embedding.is_(None),
            )
            .order_by(MeetingChunk.meeting_id, MeetingChunk.chunk_index)
        ).all()
        if not chunks:
            return 0
        return self._embed_chunk_batch(chunks)

    def _embed_chunk_batch(self, chunks: list) -> int:
        """Process a list of chunk ORM objects in batches, setting their embedding field."""
        total = 0
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            total += self._embed_chunk_batch_resilient(batch, offset=i)
        self.db.flush()
        return total

    def _embed_chunk_batch_resilient(self, chunks: list, *, offset: int) -> int:
        if not chunks:
            return 0
        texts = [c.content or "" for c in chunks]
        try:
            embeddings = self.embed_texts(texts)
        except httpx.ReadTimeout:
            if len(chunks) == 1:
                logger.exception("Embedding chunk timed out at offset %d", offset)
                return 0
            midpoint = max(1, len(chunks) // 2)
            logger.warning(
                "Embedding batch timed out at offset %d with %d chunks; retrying in smaller batches",
                offset,
                len(chunks),
            )
            return self._embed_chunk_batch_resilient(chunks[:midpoint], offset=offset) + self._embed_chunk_batch_resilient(
                chunks[midpoint:],
                offset=offset + midpoint,
            )
        except Exception:
            logger.exception("Embedding batch failed at offset %d", offset)
            return 0

        for chunk, vec in zip(chunks, embeddings):
            chunk.embedding = vec
        return len(chunks)
