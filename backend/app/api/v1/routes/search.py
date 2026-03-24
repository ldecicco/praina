"""Semantic search endpoint — hybrid TF-IDF + vector retrieval."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.retrieval_agent import RetrievalAgent
from app.db.session import get_db
from app.core.security import get_current_user
from app.models.auth import UserAccount
from app.services.embedding_service import EmbeddingService

router = APIRouter()


class SearchResultItem(BaseModel):
    source_type: str
    source_id: str
    source_key: str
    title: str
    version: int
    chunk_index: int
    content: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int


class EmbedBackfillResponse(BaseModel):
    documents: int
    meetings: int
    research: int = 0
    teaching: int = 0


@router.get("/{project_id}/search", response_model=SearchResponse)
def search_project(
    project_id: uuid.UUID,
    q: str = Query(..., min_length=1, description="Search query"),
    scope: str | None = Query(None, description="'documents', 'meetings', 'research', 'teaching', 'resources', or None for all"),
    top_k: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> SearchResponse:
    """Hybrid semantic + keyword search across project documents and meetings."""
    agent = RetrievalAgent(db)
    results = agent.retrieve(
        query=q,
        project_id=project_id,
        top_k=top_k,
        scope_filter=scope,
    )
    return SearchResponse(
        query=q,
        results=[
            SearchResultItem(
                source_type=r.source_type,
                source_id=r.source_id,
                source_key=r.source_key,
                title=r.title,
                version=r.version,
                chunk_index=r.chunk_index,
                content=r.content,
                score=r.score,
            )
            for r in results
        ],
        total=len(results),
    )


@router.post("/{project_id}/search/embed-backfill", response_model=EmbedBackfillResponse)
def embed_backfill(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EmbedBackfillResponse:
    """Backfill embeddings for all un-embedded chunks in a project."""
    svc = EmbeddingService(db)
    result = svc.embed_all_unembedded(project_id)
    db.commit()
    return EmbedBackfillResponse(**result)
