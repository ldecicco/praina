"""Retrieval agent — hybrid TF-IDF + vector search over project knowledge chunks."""

from __future__ import annotations

import logging
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import DocumentChunk, DocumentStatus, ProjectDocument
from app.models.meeting import MeetingChunk, MeetingRecord
from app.models.research import ResearchChunk, ResearchNote, ResearchReference
from app.models.resources import Equipment, EquipmentBlocker, EquipmentBooking, EquipmentDowntime, EquipmentRequirement
from app.models.teaching import TeachingChunk

logger = logging.getLogger(__name__)

MAX_CHUNK_SCAN = 400
MAX_RAW_MEETING_SCAN = 40
DEFAULT_TOP_K = 5

# Weight factors for hybrid scoring
TFIDF_WEIGHT = 0.4
VECTOR_WEIGHT = 0.6
VECTOR_TOP_K_SCAN = 40


@dataclass
class RetrievalResult:
    source_type: str
    source_id: str
    source_key: str
    title: str
    version: int
    chunk_index: int
    content: str
    score: float


class RetrievalAgent:
    """
    Two-tier hybrid retrieval over project knowledge base.

    Tier 1: TF-IDF-weighted token scoring with title boost and recency bonus.
    Tier 2: Cosine similarity on pgvector embeddings (when embeddings exist).

    Final score = TFIDF_WEIGHT * normalized_tfidf + VECTOR_WEIGHT * cosine_similarity
    """

    def __init__(self, db: Session):
        self.db = db

    def retrieve(
        self,
        query: str,
        project_id: uuid.UUID,
        *,
        top_k: int = DEFAULT_TOP_K,
        scope_filter: str | None = None,
        entity_id: uuid.UUID | None = None,
        referenced_document_keys: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve the most relevant chunks for a query using hybrid search."""
        tokens = self._tokenize(query)
        idf = self._compute_idf(tokens, project_id, scope_filter)

        # --- TF-IDF results ---
        tfidf_results: list[RetrievalResult] = []
        if scope_filter not in {"meetings", "research", "teaching", "resources"}:
            tfidf_results.extend(
                self._search_documents(project_id, tokens, idf, entity_id, referenced_document_keys)
            )
        if scope_filter not in {"documents", "research", "teaching", "resources"}:
            tfidf_results.extend(self._search_meeting_chunks(project_id, tokens, idf))
            tfidf_results.extend(self._search_raw_meetings(project_id, tokens, idf))
        if scope_filter is None or scope_filter == "research":
            tfidf_results.extend(self._search_research_chunks(project_id, tokens, idf))
        if scope_filter is None or scope_filter == "teaching":
            tfidf_results.extend(self._search_teaching_chunks(project_id, tokens, idf))
        if scope_filter is None or scope_filter == "resources":
            tfidf_results.extend(self._search_resource_records(project_id, tokens, idf))

        # --- Vector results ---
        vector_results: list[RetrievalResult] = []
        query_embedding = self._get_query_embedding(query)
        if query_embedding is not None:
            if scope_filter not in {"meetings", "research", "teaching", "resources"}:
                vector_results.extend(
                    self._vector_search_documents(
                        project_id, query_embedding, entity_id, referenced_document_keys
                    )
                )
            if scope_filter not in {"documents", "research", "teaching", "resources"}:
                vector_results.extend(
                    self._vector_search_meetings(project_id, query_embedding)
                )
            if scope_filter is None or scope_filter == "research":
                vector_results.extend(
                    self._vector_search_research(project_id, query_embedding)
                )
            if scope_filter is None or scope_filter == "teaching":
                vector_results.extend(
                    self._vector_search_teaching(project_id, query_embedding)
                )

        # --- Merge ---
        if vector_results:
            merged = self._merge_hybrid(tfidf_results, vector_results)
        else:
            merged = tfidf_results
            merged.sort(key=lambda r: r.score, reverse=True)

        return self._deduplicate(merged)[:top_k]

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def _get_query_embedding(self, query: str) -> list[float] | None:
        """Generate embedding for the query text. Returns None if unavailable."""
        try:
            from app.services.embedding_service import EmbeddingService
            svc = EmbeddingService(self.db)
            embeddings = svc.embed_texts([query])
            return embeddings[0] if embeddings else None
        except Exception:
            logger.debug("Query embedding generation unavailable, falling back to TF-IDF only")
            return None

    def _vector_search_documents(
        self,
        project_id: uuid.UUID,
        query_embedding: list[float],
        entity_id: uuid.UUID | None,
        referenced_keys: list[str] | None,
    ) -> list[RetrievalResult]:
        cosine_distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(
                DocumentChunk,
                ProjectDocument,
                (1 - cosine_distance).label("similarity"),
            )
            .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
            .where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.status == DocumentStatus.indexed.value,
                DocumentChunk.embedding.isnot(None),
            )
            .order_by(cosine_distance)
            .limit(VECTOR_TOP_K_SCAN)
        )
        if entity_id is not None:
            stmt = stmt.where(
                (ProjectDocument.wp_id == entity_id)
                | (ProjectDocument.task_id == entity_id)
                | (ProjectDocument.deliverable_id == entity_id)
                | (ProjectDocument.milestone_id == entity_id)
            )

        rows = self.db.execute(stmt).all()

        if referenced_keys:
            key_set = {str(k) for k in referenced_keys}
            rows = [r for r in rows if str(r[1].document_key) in key_set]

        results: list[RetrievalResult] = []
        for chunk, doc, similarity in rows:
            results.append(
                RetrievalResult(
                    source_type="document",
                    source_id=str(doc.id),
                    source_key=str(doc.document_key),
                    title=doc.title,
                    version=doc.version,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=float(similarity),
                )
            )
        return results

    def _vector_search_meetings(
        self,
        project_id: uuid.UUID,
        query_embedding: list[float],
    ) -> list[RetrievalResult]:
        cosine_distance = MeetingChunk.embedding.cosine_distance(query_embedding)
        rows = self.db.execute(
            select(
                MeetingChunk,
                MeetingRecord,
                (1 - cosine_distance).label("similarity"),
            )
            .join(MeetingRecord, MeetingChunk.meeting_id == MeetingRecord.id)
            .where(
                MeetingRecord.project_id == project_id,
                MeetingChunk.embedding.isnot(None),
            )
            .order_by(cosine_distance)
            .limit(VECTOR_TOP_K_SCAN)
        ).all()

        results: list[RetrievalResult] = []
        for chunk, meeting, similarity in rows:
            results.append(
                RetrievalResult(
                    source_type="meeting",
                    source_id=str(meeting.id),
                    source_key=f"meeting:{meeting.id}",
                    title=meeting.title,
                    version=1,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=float(similarity),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Research chunk search
    # ------------------------------------------------------------------

    def _search_research_chunks(
        self,
        project_id: uuid.UUID,
        tokens: list[str],
        idf: dict[str, float],
    ) -> list[RetrievalResult]:
        note_rows = self.db.execute(
            select(ResearchNote.id, ResearchNote.title, ResearchNote.note_type).where(
                ResearchNote.project_id == project_id
            )
        ).all()
        reference_rows = self.db.execute(
            select(ResearchReference.id, ResearchReference.title).where(
                ResearchReference.project_id == project_id
            )
        ).all()
        meeting_rows = self.db.execute(
            select(MeetingRecord.id, MeetingRecord.title).where(
                MeetingRecord.project_id == project_id
            )
        ).all()
        note_lookup = {
            str(item_id): {
                "title": title,
                "artifact_type": self._artifact_type_from_note_type(
                    note_type.value if hasattr(note_type, "value") else str(note_type)
                ),
            }
            for item_id, title, note_type in note_rows
        }
        reference_lookup = {
            str(item_id): {
                "title": title,
                "artifact_type": "research_reference",
            }
            for item_id, title in reference_rows
        }
        meeting_lookup = {
            str(item_id): {
                "title": title,
                "artifact_type": "research_discussion",
            }
            for item_id, title in meeting_rows
        }

        chunks = self.db.execute(
            select(ResearchChunk)
            .where(ResearchChunk.project_id == project_id)
            .limit(MAX_CHUNK_SCAN)
        ).scalars().all()

        results: list[RetrievalResult] = []
        for chunk in chunks:
            content = (chunk.content or "").lower()
            if not content:
                continue
            score = self._tfidf_score(content, tokens, idf)
            if score <= 0 and tokens:
                continue
            meta = self._research_chunk_meta(
                chunk_source_type=chunk.source_type,
                source_id=str(chunk.source_id),
                note_lookup=note_lookup,
                reference_lookup=reference_lookup,
                meeting_lookup=meeting_lookup,
            )
            results.append(
                RetrievalResult(
                    source_type=meta["source_type"],
                    source_id=str(chunk.source_id),
                    source_key=f"research:{chunk.source_type}:{chunk.source_id}",
                    title=meta["title"],
                    version=1,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=score,
                )
            )
        return results

    def _vector_search_research(
        self,
        project_id: uuid.UUID,
        query_embedding: list[float],
    ) -> list[RetrievalResult]:
        note_rows = self.db.execute(
            select(ResearchNote.id, ResearchNote.title, ResearchNote.note_type).where(
                ResearchNote.project_id == project_id
            )
        ).all()
        reference_rows = self.db.execute(
            select(ResearchReference.id, ResearchReference.title).where(
                ResearchReference.project_id == project_id
            )
        ).all()
        meeting_rows = self.db.execute(
            select(MeetingRecord.id, MeetingRecord.title).where(
                MeetingRecord.project_id == project_id
            )
        ).all()
        note_lookup = {
            str(item_id): {
                "title": title,
                "artifact_type": self._artifact_type_from_note_type(
                    note_type.value if hasattr(note_type, "value") else str(note_type)
                ),
            }
            for item_id, title, note_type in note_rows
        }
        reference_lookup = {
            str(item_id): {
                "title": title,
                "artifact_type": "research_reference",
            }
            for item_id, title in reference_rows
        }
        meeting_lookup = {
            str(item_id): {
                "title": title,
                "artifact_type": "research_discussion",
            }
            for item_id, title in meeting_rows
        }

        cosine_distance = ResearchChunk.embedding.cosine_distance(query_embedding)
        rows = self.db.execute(
            select(
                ResearchChunk,
                (1 - cosine_distance).label("similarity"),
            )
            .where(
                ResearchChunk.project_id == project_id,
                ResearchChunk.embedding.isnot(None),
            )
            .order_by(cosine_distance)
            .limit(VECTOR_TOP_K_SCAN)
        ).all()

        results: list[RetrievalResult] = []
        for chunk, similarity in rows:
            meta = self._research_chunk_meta(
                chunk_source_type=chunk.source_type,
                source_id=str(chunk.source_id),
                note_lookup=note_lookup,
                reference_lookup=reference_lookup,
                meeting_lookup=meeting_lookup,
            )
            results.append(
                RetrievalResult(
                    source_type=meta["source_type"],
                    source_id=str(chunk.source_id),
                    source_key=f"research:{chunk.source_type}:{chunk.source_id}",
                    title=meta["title"],
                    version=1,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=float(similarity),
                )
            )
        return results

    def _search_teaching_chunks(
        self,
        project_id: uuid.UUID,
        tokens: list[str],
        idf: dict[str, float],
    ) -> list[RetrievalResult]:
        chunks = self.db.execute(
            select(TeachingChunk)
            .where(TeachingChunk.project_id == project_id)
            .order_by(TeachingChunk.source_type.asc(), TeachingChunk.chunk_index.asc())
            .limit(MAX_CHUNK_SCAN)
        ).scalars().all()

        results: list[RetrievalResult] = []
        for chunk in chunks:
            content = (chunk.content or "").lower()
            if not content:
                continue
            score = self._tfidf_score(content, tokens, idf)
            if score <= 0 and tokens:
                continue

            results.append(
                RetrievalResult(
                    source_type=self._teaching_result_type(chunk.source_type),
                    source_id=str(chunk.source_id),
                    source_key=f"teaching:{chunk.source_type}:{chunk.source_id}",
                    title=self._teaching_chunk_title(chunk),
                    version=1,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=score,
                )
            )
        return results

    def _vector_search_teaching(
        self,
        project_id: uuid.UUID,
        query_embedding: list[float],
    ) -> list[RetrievalResult]:
        cosine_distance = TeachingChunk.embedding.cosine_distance(query_embedding)
        rows = self.db.execute(
            select(
                TeachingChunk,
                (1 - cosine_distance).label("similarity"),
            )
            .where(
                TeachingChunk.project_id == project_id,
                TeachingChunk.embedding.isnot(None),
            )
            .order_by(cosine_distance)
            .limit(VECTOR_TOP_K_SCAN)
        ).all()

        results: list[RetrievalResult] = []
        for chunk, similarity in rows:
            results.append(
                RetrievalResult(
                    source_type=self._teaching_result_type(chunk.source_type),
                    source_id=str(chunk.source_id),
                    source_key=f"teaching:{chunk.source_type}:{chunk.source_id}",
                    title=self._teaching_chunk_title(chunk),
                    version=1,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=float(similarity),
                )
            )
        return results

    def _teaching_result_type(self, source_type: str) -> str:
        normalized = (source_type or "").strip().lower()
        if normalized == "profile":
            return "teaching_profile"
        if normalized == "artifact":
            return "teaching_artifact"
        if normalized == "blocker":
            return "teaching_blocker"
        if normalized == "progress_report":
            return "teaching_progress"
        if normalized == "course_material":
            return "course_material"
        return "teaching_record"

    def _teaching_chunk_title(self, chunk: TeachingChunk) -> str:
        source_type = (chunk.source_type or "").replace("_", " ").strip().title() or "Teaching"
        first_line = (chunk.content or "").strip().splitlines()
        if first_line:
            return first_line[0][:160]
        return source_type

    def _artifact_type_from_note_type(self, note_type: str) -> str:
        normalized = (note_type or "").strip().lower()
        if normalized == "discussion":
            return "research_discussion"
        if normalized == "finding":
            return "research_finding"
        if normalized == "decision":
            return "research_decision"
        if normalized == "action_item":
            return "research_action_item"
        if normalized == "hypothesis":
            return "research_hypothesis"
        if normalized == "method":
            return "research_method"
        if normalized == "literature_review":
            return "research_literature_review"
        if normalized == "conclusion":
            return "research_conclusion"
        return "research_observation"

    def _search_resource_records(
        self,
        project_id: uuid.UUID,
        tokens: list[str],
        idf: dict[str, float],
    ) -> list[RetrievalResult]:
        requirements = list(
            self.db.scalars(
                select(EquipmentRequirement)
                .where(EquipmentRequirement.project_id == project_id)
                .order_by(EquipmentRequirement.created_at.desc())
            ).all()
        )
        bookings = list(
            self.db.scalars(
                select(EquipmentBooking)
                .where(EquipmentBooking.project_id == project_id)
                .order_by(EquipmentBooking.created_at.desc())
            ).all()
        )
        blockers = list(
            self.db.scalars(
                select(EquipmentBlocker)
                .where(EquipmentBlocker.project_id == project_id)
                .order_by(EquipmentBlocker.created_at.desc())
            ).all()
        )
        equipment_ids = {item.equipment_id for item in requirements} | {item.equipment_id for item in bookings} | {item.equipment_id for item in blockers}
        equipment_lookup = (
            {item.id: item for item in self.db.scalars(select(Equipment).where(Equipment.id.in_(equipment_ids))).all()}
            if equipment_ids
            else {}
        )
        downtime_rows = (
            list(
                self.db.scalars(
                    select(EquipmentDowntime)
                    .where(EquipmentDowntime.equipment_id.in_(equipment_ids))
                    .order_by(EquipmentDowntime.start_at.desc())
                ).all()
            )
            if equipment_ids
            else []
        )

        results: list[RetrievalResult] = []

        for item in requirements:
            equipment = equipment_lookup.get(item.equipment_id)
            text = "\n".join(
                part for part in [
                    f"Equipment Requirement: {equipment.name if equipment else 'Equipment'}",
                    f"Priority: {item.priority}",
                    f"Purpose: {item.purpose}",
                    f"Notes: {item.notes}" if item.notes else None,
                    f"Equipment Status: {equipment.status}" if equipment else None,
                ] if part
            )
            score = self._tfidf_score(text.lower(), tokens, idf)
            if score <= 0 and tokens:
                continue
            results.append(
                RetrievalResult(
                    source_type="resource_requirement",
                    source_id=str(item.id),
                    source_key=f"resource:requirement:{item.id}",
                    title=equipment.name if equipment else "Equipment Requirement",
                    version=1,
                    chunk_index=0,
                    content=text,
                    score=score,
                )
            )

        for item in bookings:
            equipment = equipment_lookup.get(item.equipment_id)
            text = "\n".join(
                part for part in [
                    f"Equipment Booking: {equipment.name if equipment else 'Equipment'}",
                    f"Status: {item.status}",
                    f"Purpose: {item.purpose}",
                    f"Start: {item.start_at.isoformat() if item.start_at else ''}",
                    f"End: {item.end_at.isoformat() if item.end_at else ''}",
                    f"Notes: {item.notes}" if item.notes else None,
                ] if part
            )
            score = self._tfidf_score(text.lower(), tokens, idf)
            if score <= 0 and tokens:
                continue
            results.append(
                RetrievalResult(
                    source_type="resource_booking",
                    source_id=str(item.id),
                    source_key=f"resource:booking:{item.id}",
                    title=equipment.name if equipment else "Equipment Booking",
                    version=1,
                    chunk_index=0,
                    content=text,
                    score=score,
                )
            )

        for item in blockers:
            equipment = equipment_lookup.get(item.equipment_id)
            text = "\n".join(
                part for part in [
                    f"Equipment Blocker: {equipment.name if equipment else 'Equipment'}",
                    f"Reason: {item.reason}",
                    f"Status: {item.status}",
                    f"Blocked Days: {item.blocked_days}",
                    f"Started At: {item.started_at.isoformat() if item.started_at else ''}",
                    f"Ended At: {item.ended_at.isoformat() if item.ended_at else ''}" if item.ended_at else None,
                ] if part
            )
            score = self._tfidf_score(text.lower(), tokens, idf)
            if score <= 0 and tokens:
                continue
            results.append(
                RetrievalResult(
                    source_type="resource_blocker",
                    source_id=str(item.id),
                    source_key=f"resource:blocker:{item.id}",
                    title=equipment.name if equipment else "Equipment Blocker",
                    version=1,
                    chunk_index=0,
                    content=text,
                    score=score,
                )
            )

        for item in downtime_rows:
            equipment = equipment_lookup.get(item.equipment_id)
            text = "\n".join(
                part for part in [
                    f"Equipment Downtime: {equipment.name if equipment else 'Equipment'}",
                    f"Reason: {item.reason}",
                    f"Start: {item.start_at.isoformat() if item.start_at else ''}",
                    f"End: {item.end_at.isoformat() if item.end_at else ''}",
                    f"Notes: {item.notes}" if item.notes else None,
                ] if part
            )
            score = self._tfidf_score(text.lower(), tokens, idf)
            if score <= 0 and tokens:
                continue
            results.append(
                RetrievalResult(
                    source_type="resource_downtime",
                    source_id=str(item.id),
                    source_key=f"resource:downtime:{item.id}",
                    title=equipment.name if equipment else "Equipment Downtime",
                    version=1,
                    chunk_index=0,
                    content=text,
                    score=score,
                )
            )
        return results

    def _research_chunk_meta(
        self,
        *,
        chunk_source_type: str,
        source_id: str,
        note_lookup: dict[str, dict[str, str]],
        reference_lookup: dict[str, dict[str, str]],
        meeting_lookup: dict[str, dict[str, str]],
    ) -> dict[str, str]:
        if chunk_source_type.startswith("note:"):
            meta = note_lookup.get(source_id, {})
            return {
                "source_type": str(meta.get("artifact_type") or "research_note"),
                "title": str(meta.get("title") or "Research note"),
            }
        if chunk_source_type == "meeting_discussion":
            meta = meeting_lookup.get(source_id, {})
            return {
                "source_type": str(meta.get("artifact_type") or "research_discussion"),
                "title": str(meta.get("title") or "Research discussion"),
            }
        meta = reference_lookup.get(source_id, {})
        return {
            "source_type": str(meta.get("artifact_type") or "research_reference"),
            "title": str(meta.get("title") or "Research reference"),
        }

    # ------------------------------------------------------------------
    # Hybrid merge
    # ------------------------------------------------------------------

    def _merge_hybrid(
        self,
        tfidf_results: list[RetrievalResult],
        vector_results: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """Combine TF-IDF and vector results using weighted normalization."""
        # Normalize TF-IDF scores to [0, 1]
        max_tfidf = max((r.score for r in tfidf_results), default=1.0) or 1.0

        # Build lookup: (source_id, chunk_index) -> result
        merged: dict[tuple[str, int], RetrievalResult] = {}
        tfidf_scores: dict[tuple[str, int], float] = {}
        vector_scores: dict[tuple[str, int], float] = {}

        for r in tfidf_results:
            key = (r.source_key, r.chunk_index)
            tfidf_scores[key] = r.score / max_tfidf
            merged[key] = r

        for r in vector_results:
            key = (r.source_key, r.chunk_index)
            vector_scores[key] = r.score  # already in [0, 1] (cosine similarity)
            if key not in merged:
                merged[key] = r

        # Compute hybrid score
        for key, result in merged.items():
            tf = tfidf_scores.get(key, 0.0)
            vec = vector_scores.get(key, 0.0)
            result.score = TFIDF_WEIGHT * tf + VECTOR_WEIGHT * vec

        results = list(merged.values())
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # TF-IDF document chunk search
    # ------------------------------------------------------------------

    def _search_documents(
        self,
        project_id: uuid.UUID,
        tokens: list[str],
        idf: dict[str, float],
        entity_id: uuid.UUID | None,
        referenced_keys: list[str] | None,
    ) -> list[RetrievalResult]:
        stmt = (
            select(DocumentChunk, ProjectDocument)
            .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
            .where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.status == DocumentStatus.indexed.value,
            )
            .order_by(ProjectDocument.updated_at.desc(), DocumentChunk.chunk_index.asc())
            .limit(MAX_CHUNK_SCAN)
        )
        if entity_id is not None:
            stmt = stmt.where(
                (ProjectDocument.wp_id == entity_id)
                | (ProjectDocument.task_id == entity_id)
                | (ProjectDocument.deliverable_id == entity_id)
                | (ProjectDocument.milestone_id == entity_id)
            )
        rows = self.db.execute(stmt).all()

        if referenced_keys:
            key_set = {str(k) for k in referenced_keys}
            rows = [(c, d) for c, d in rows if str(d.document_key) in key_set]

        results: list[RetrievalResult] = []
        now_ts = self._max_doc_timestamp(rows)

        for chunk, doc in rows:
            chunk_text = (chunk.content or "").lower()
            if not chunk_text:
                continue
            score = self._tfidf_score(chunk_text, tokens, idf)
            title_lower = (doc.title or "").lower()
            title_hits = sum(1 for t in tokens if t in title_lower)
            score += title_hits * 2.0
            score += self._recency_bonus(doc.updated_at, now_ts)

            if score <= 0 and tokens:
                continue

            results.append(
                RetrievalResult(
                    source_type="document",
                    source_id=str(doc.id),
                    source_key=str(doc.document_key),
                    title=doc.title,
                    version=doc.version,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=score,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Meeting chunk search (indexed meetings)
    # ------------------------------------------------------------------

    def _search_meeting_chunks(
        self,
        project_id: uuid.UUID,
        tokens: list[str],
        idf: dict[str, float],
    ) -> list[RetrievalResult]:
        rows = self.db.execute(
            select(MeetingChunk, MeetingRecord)
            .join(MeetingRecord, MeetingChunk.meeting_id == MeetingRecord.id)
            .where(MeetingRecord.project_id == project_id)
        ).all()

        results: list[RetrievalResult] = []
        for chunk, meeting in rows:
            content = (chunk.content or "").lower()
            if not content:
                continue
            score = self._tfidf_score(content, tokens, idf)
            title_lower = (meeting.title or "").lower()
            title_hits = sum(1 for t in tokens if t in title_lower)
            score += title_hits * 2.0

            if score <= 0 and tokens:
                continue

            results.append(
                RetrievalResult(
                    source_type="meeting",
                    source_id=str(meeting.id),
                    source_key=f"meeting:{meeting.id}",
                    title=meeting.title,
                    version=1,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content or "",
                    score=score,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Raw meeting fallback (non-indexed meetings)
    # ------------------------------------------------------------------

    def _search_raw_meetings(
        self,
        project_id: uuid.UUID,
        tokens: list[str],
        idf: dict[str, float],
    ) -> list[RetrievalResult]:
        meetings = self.db.scalars(
            select(MeetingRecord)
            .where(
                MeetingRecord.project_id == project_id,
                MeetingRecord.indexing_status != "indexed",
            )
            .order_by(MeetingRecord.starts_at.desc())
            .limit(MAX_RAW_MEETING_SCAN)
        ).all()

        results: list[RetrievalResult] = []
        for meeting in meetings:
            content = (meeting.content_text or "").lower()
            if not content:
                continue
            score = self._tfidf_score(content, tokens, idf)
            title_lower = (meeting.title or "").lower()
            title_hits = sum(1 for t in tokens if t in title_lower)
            score += title_hits * 2.0

            if score <= 0 and tokens:
                continue

            results.append(
                RetrievalResult(
                    source_type="meeting",
                    source_id=str(meeting.id),
                    source_key=f"meeting:{meeting.id}",
                    title=meeting.title,
                    version=1,
                    chunk_index=0,
                    content=meeting.content_text or "",
                    score=score,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        raw = re.split(r"[^a-zA-Z0-9]+", text.lower())
        seen: set[str] = set()
        tokens: list[str] = []
        for token in raw:
            if len(token) < 3 or token in seen:
                continue
            seen.add(token)
            tokens.append(token)
        return tokens

    def _compute_idf(
        self,
        tokens: list[str],
        project_id: uuid.UUID,
        scope_filter: str | None,
    ) -> dict[str, float]:
        if not tokens:
            return {}

        total_chunks = 0
        token_doc_freq: dict[str, int] = {t: 0 for t in tokens}

        if scope_filter not in {"meetings", "research", "teaching", "resources"}:
            doc_chunks = self.db.scalars(
                select(DocumentChunk.content)
                .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
                .where(
                    ProjectDocument.project_id == project_id,
                    ProjectDocument.status == DocumentStatus.indexed.value,
                )
                .limit(MAX_CHUNK_SCAN)
            ).all()
            total_chunks += len(doc_chunks)
            for content in doc_chunks:
                lower = (content or "").lower()
                for t in tokens:
                    if t in lower:
                        token_doc_freq[t] += 1

        if scope_filter not in {"documents", "research", "teaching", "resources"}:
            meeting_chunks = self.db.scalars(
                select(MeetingChunk.content)
                .join(MeetingRecord, MeetingChunk.meeting_id == MeetingRecord.id)
                .where(MeetingRecord.project_id == project_id)
            ).all()
            total_chunks += len(meeting_chunks)
            for content in meeting_chunks:
                lower = (content or "").lower()
                for t in tokens:
                    if t in lower:
                        token_doc_freq[t] += 1

        if scope_filter is None or scope_filter == "research":
            research_chunks = self.db.scalars(
                select(ResearchChunk.content)
                .where(ResearchChunk.project_id == project_id)
                .limit(MAX_CHUNK_SCAN)
            ).all()
            total_chunks += len(research_chunks)
            for content in research_chunks:
                lower = (content or "").lower()
                for t in tokens:
                    if t in lower:
                        token_doc_freq[t] += 1

        if scope_filter is None or scope_filter == "teaching":
            teaching_chunks = self.db.scalars(
                select(TeachingChunk.content)
                .where(TeachingChunk.project_id == project_id)
                .limit(MAX_CHUNK_SCAN)
            ).all()
            total_chunks += len(teaching_chunks)
            for content in teaching_chunks:
                lower = (content or "").lower()
                for t in tokens:
                    if t in lower:
                        token_doc_freq[t] += 1

        if scope_filter is None or scope_filter == "resources":
            resource_texts: list[str] = []
            resource_texts.extend(
                self.db.scalars(
                    select(EquipmentRequirement.purpose).where(EquipmentRequirement.project_id == project_id)
                ).all()
            )
            resource_texts.extend(
                self.db.scalars(
                    select(EquipmentBooking.purpose).where(EquipmentBooking.project_id == project_id)
                ).all()
            )
            resource_texts.extend(
                self.db.scalars(
                    select(EquipmentBlocker.reason).where(EquipmentBlocker.project_id == project_id)
                ).all()
            )
            total_chunks += len(resource_texts)
            for content in resource_texts:
                lower = (content or "").lower()
                for t in tokens:
                    if t in lower:
                        token_doc_freq[t] += 1

        if total_chunks == 0:
            return {t: 1.0 for t in tokens}

        idf: dict[str, float] = {}
        for t in tokens:
            df = token_doc_freq[t]
            idf[t] = math.log((total_chunks + 1) / (df + 1)) + 1.0
        return idf

    def _tfidf_score(
        self, text: str, tokens: list[str], idf: dict[str, float]
    ) -> float:
        score = 0.0
        for token in tokens:
            tf = text.count(token)
            if tf > 0:
                score += (1 + math.log(tf)) * idf.get(token, 1.0)
        return score

    def _recency_bonus(self, updated_at: Any, max_ts: float) -> float:
        if max_ts <= 0:
            return 0.0
        try:
            ts = updated_at.timestamp()
        except (AttributeError, TypeError):
            return 0.0
        if ts <= 0:
            return 0.0
        ratio = ts / max_ts
        return min(0.5, ratio * 0.5)

    def _max_doc_timestamp(self, rows: list[tuple]) -> float:
        max_ts = 0.0
        for _, doc in rows:
            try:
                ts = doc.updated_at.timestamp()
                if ts > max_ts:
                    max_ts = ts
            except (AttributeError, TypeError):
                pass
        return max_ts

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        seen: set[tuple[str, int]] = set()
        deduped: list[RetrievalResult] = []
        for r in results:
            key = (r.source_key, r.chunk_index)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped
