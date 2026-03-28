"""Research AI service — summarization, synthesis, metadata extraction, and embedding."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.llm.factory import get_text_provider
from app.llm.json_utils import extract_json_object
from app.models.document import DocumentChunk, ProjectDocument
from app.models.meeting import MeetingRecord
from app.models.research import (
    BibliographyReference,
    ResearchChunk,
    ResearchCollection,
    ResearchNote,
    ResearchReference,
    research_collection_deliverables,
    research_collection_meetings,
    research_collection_tasks,
    research_collection_wps,
)
from app.models.work import Deliverable, Task, WorkPackage
from app.services.onboarding_service import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800  # characters per chunk
SUMMARY_BEGINNING_CHUNKS = 3
SUMMARY_MIDDLE_CHUNKS = 2
SUMMARY_ENDING_CHUNKS = 3
SUMMARY_MAX_CHUNKS = 18
SUMMARY_MAP_GROUP_SIZE = 2

SUMMARY_QUERY_INTENTS = [
    "What problem does this paper solve?",
    "What is the main contribution?",
    "How does the proposed method work?",
    "What data or benchmarks are used?",
    "What are the main quantitative results?",
    "What limitations or caveats are mentioned?",
    "What conclusions or future work are stated?",
]

ROLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "abstract": ("abstract",),
    "introduction": ("introduction", "background", "motivation"),
    "problem": ("problem", "challenge", "task", "objective", "we address", "we study"),
    "method": ("method", "methods", "approach", "architecture", "framework", "model", "algorithm"),
    "experimental_setup": ("experiment", "experimental setup", "dataset", "benchmark", "training", "implementation details"),
    "results": ("results", "evaluation", "performance", "accuracy", "f1", "bleu", "rouge", "score", "table"),
    "discussion": ("discussion", "analysis", "ablation", "error analysis"),
    "limitations": ("limitation", "limitations", "caveat", "failure case", "threats to validity"),
    "conclusion": ("conclusion", "future work", "we conclude", "in conclusion"),
}

GENERIC_CONCEPT_TERMS = {
    "paper",
    "study",
    "method",
    "approach",
    "result",
    "results",
    "performance",
    "experiment",
    "experiments",
    "evaluation",
    "model",
    "models",
    "framework",
    "task",
}

MAP_SUMMARY_SYSTEM_PROMPT = """
You are extracting grounded academic paper notes from source chunks.

Return ONLY valid JSON with this shape:
{
  "notes": [
    {
      "claim": "",
      "evidence": "",
      "method_details": "",
      "results": "",
      "caveats": "",
      "source_chunk_ids": []
    }
  ]
}

Rules:
- Use only facts explicitly supported by the provided chunks.
- Every note must include one or more source_chunk_ids like ["chunk_12"].
- If no method, result, or caveat is present, use an empty string.
- Prefer precise extraction over fluent prose.
- Do not invent section names, numbers, datasets, or conclusions.
""".strip()

REDUCE_SUMMARY_SYSTEM_PROMPT = """
You consolidate grounded academic notes into a structured evidence inventory.

Return ONLY valid JSON with this shape:
{
  "title": "",
  "document_type": "academic_paper",
  "summary_points": [],
  "contributions": [],
  "methods": [],
  "results": [],
  "limitations": [],
  "conclusion_points": [],
  "open_questions": [],
  "evidence": [
    {
      "claim": "",
      "chunk_ids": []
    }
  ]
}

Rules:
- Keep only claims supported by source_chunk_ids.
- Merge duplicates.
- Resolve conflicts conservatively by preserving uncertainty.
- Maintain chunk references for every evidence item.
- Separate contributions, methods, results, limitations, and conclusion points.
""".strip()

FINAL_SYNTHESIS_SYSTEM_PROMPT = """
You produce the final grounded summary for an academic paper.

Return ONLY valid JSON with this exact shape:
{
  "title": "",
  "document_type": "academic_paper",
  "summary": "",
  "contributions": [],
  "methods": [],
  "results": [],
  "limitations": [],
  "conclusion": "",
  "open_questions": [],
  "evidence": [
    {
      "claim": "",
      "chunk_ids": []
    }
  ]
}

Rules:
- Every major statement must be grounded in chunk_ids.
- Be concise but information-dense.
- Explicitly distinguish contributions from validated results.
- Include limitations when supported.
- Avoid hype and unsupported inferences.
- Keep numbers only when grounded in source chunks.
- Do not repeat the abstract verbatim.
""".strip()

COLLECTION_SYNTHESIS_SYSTEM_PROMPT = """
You synthesize the state of a research topic from grounded project material.

Return ONLY valid JSON with this exact shape:
{
  "summary": "",
  "knowledge_state": [],
  "discussion_points": [],
  "findings": [],
  "decisions": [],
  "tasks": [],
  "output_readiness": {
    "status": "",
    "missing": [],
    "next_actions": []
  },
  "open_questions": [],
  "evidence": [
    {
      "claim": "",
      "sources": []
    }
  ]
}

Rules:
- Use only the provided material.
- Separate discussions, findings, decisions, and tasks explicitly.
- Keep the output concise but information-dense.
- If evidence is weak or incomplete, say so conservatively.
- `sources` must reference the provided artifact labels such as note titles, reference titles, meeting titles, task codes, or deliverable codes.
- Do not invent experiments, results, task ownership, or publication state.
""".strip()

CONCEPT_EXTRACTION_SYSTEM_PROMPT = """
You extract the core technical concepts from an academic paper title and abstract.

Return ONLY valid JSON with this exact shape:
{
  "concepts": []
}

Rules:
- Return 5 to 12 concepts.
- Concepts must be short technical noun phrases, not sentences.
- Keep canonical labels concise.
- Preserve important acronyms such as VLM, RAG, SLAM, RL, LLM when central.
- Avoid generic terms such as paper, study, method, approach, result, performance, experiment, evaluation.
- Avoid duplicates, near-duplicates, or trivial restatements of the title.
""".strip()


@dataclass
class SummaryChunk:
    id: str
    chunk_index: int
    content: str
    role: str
    score: float = 0.0
    reasons: set[str] = field(default_factory=set)
    position_bucket: str = "middle"


class ResearchAIService:
    def __init__(self, db: Session):
        self.db = db
        self.provider = get_text_provider()

    # ── Ollama chat helper ─────────────────────────────────────────────

    def _chat(self, system: str, user: str) -> str:
        return self.provider.generate(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            timeout=180,
        )

    def _chat_json(self, system: str, user: str) -> dict[str, Any]:
        raw = self._chat(system, user)
        cleaned = extract_json_object(raw)
        return json.loads(cleaned)

    def _load_json_object(self, value: str | None) -> dict[str, Any] | None:
        if not value:
            return None
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _summary_payload_as_text(self, value: str | None) -> str:
        payload = self._load_json_object(value)
        if not payload:
            return (value or "").strip()

        parts: list[str] = []
        summary = str(payload.get("summary") or "").strip()
        if summary:
            parts.append(summary)
        for key in ("contributions", "methods", "results", "limitations", "open_questions"):
            entries = payload.get(key)
            if isinstance(entries, list):
                parts.extend(str(item).strip() for item in entries if str(item).strip())
        conclusion = str(payload.get("conclusion") or "").strip()
        if conclusion:
            parts.append(conclusion)
        return "\n".join(parts).strip()

    def build_summary_queries(self, document_metadata: dict[str, Any]) -> list[str]:
        title = str(document_metadata.get("title") or "").strip()
        title_prefix = f"Paper title: {title}. " if title else ""
        return [f"{title_prefix}{intent}" for intent in SUMMARY_QUERY_INTENTS]

    def classify_chunk_role(self, chunk: DocumentChunk | SummaryChunk | str) -> str:
        text = chunk if isinstance(chunk, str) else chunk.content
        normalized = f" {re.sub(r'\\s+', ' ', text.lower())} "
        for role, patterns in ROLE_PATTERNS.items():
            if any(f" {pattern} " in normalized for pattern in patterns):
                return role
        return "other"

    def retrieve_summary_chunks(self, doc_id: uuid.UUID, queries: list[str], per_query_k: int = 5) -> list[SummaryChunk]:
        chunk_rows = list(
            self.db.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index)
            ).all()
        )
        if not chunk_rows:
            return []

        candidates: dict[str, SummaryChunk] = {}
        for selected in self._boundary_chunks(chunk_rows):
            candidates[selected.id] = selected

        for selected in self._heuristic_role_chunks(chunk_rows):
            self._merge_candidate(candidates, selected)

        for selected in self._semantic_query_chunks(doc_id, queries, per_query_k=per_query_k):
            self._merge_candidate(candidates, selected)

        return self.select_balanced_chunks(list(candidates.values()))

    def select_balanced_chunks(self, chunks: list[SummaryChunk]) -> list[SummaryChunk]:
        if not chunks:
            return []

        ranked = sorted(
            chunks,
            key=lambda chunk: (
                len(chunk.reasons),
                1 if chunk.position_bucket == "beginning" else 0,
                1 if chunk.position_bucket == "ending" else 0,
                chunk.score,
                -chunk.chunk_index,
            ),
            reverse=True,
        )

        selected: list[SummaryChunk] = []
        seen_ids: set[str] = set()
        role_counts: dict[str, int] = {}
        bucket_counts: dict[str, int] = {"beginning": 0, "middle": 0, "ending": 0}

        required_roles = ["abstract", "introduction", "problem", "method", "experimental_setup", "results", "limitations", "conclusion"]
        for role in required_roles:
            chunk = next((item for item in ranked if item.role == role and item.id not in seen_ids), None)
            if chunk is None:
                continue
            selected.append(chunk)
            seen_ids.add(chunk.id)
            role_counts[chunk.role] = role_counts.get(chunk.role, 0) + 1
            bucket_counts[chunk.position_bucket] = bucket_counts.get(chunk.position_bucket, 0) + 1
            if len(selected) >= SUMMARY_MAX_CHUNKS:
                return sorted(selected, key=lambda item: item.chunk_index)

        for chunk in ranked:
            if chunk.id in seen_ids:
                continue
            if role_counts.get(chunk.role, 0) >= 2 and chunk.role not in {"results", "method"}:
                continue
            if bucket_counts.get(chunk.position_bucket, 0) >= 6:
                continue
            if any(abs(existing.chunk_index - chunk.chunk_index) <= 1 for existing in selected):
                continue
            selected.append(chunk)
            seen_ids.add(chunk.id)
            role_counts[chunk.role] = role_counts.get(chunk.role, 0) + 1
            bucket_counts[chunk.position_bucket] = bucket_counts.get(chunk.position_bucket, 0) + 1
            if len(selected) >= SUMMARY_MAX_CHUNKS:
                break

        return sorted(selected, key=lambda item: item.chunk_index)

    def summarize_chunk_map(self, chunks: list[SummaryChunk]) -> list[dict[str, Any]]:
        if not chunks:
            return []
        outputs: list[dict[str, Any]] = []
        for group in self._group_summary_chunks(chunks):
            chunk_payload = [
                {
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "role": chunk.role,
                    "content": chunk.content,
                }
                for chunk in group
            ]
            user_prompt = (
                "Extract grounded academic notes from these chunks.\n"
                "Focus on contribution, method, experimental setup, results, limitations, and conclusion when present.\n"
                "Chunks:\n"
                f"{json.dumps(chunk_payload, ensure_ascii=False)}"
            )
            payload = self._chat_json(MAP_SUMMARY_SYSTEM_PROMPT, user_prompt)
            outputs.extend(payload.get("notes") or [])
        return outputs

    def reduce_summaries(self, map_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        user_prompt = (
            "Consolidate these grounded academic notes into a structured evidence inventory.\n"
            f"Notes:\n{json.dumps(map_outputs, ensure_ascii=False)}"
        )
        return self._chat_json(REDUCE_SUMMARY_SYSTEM_PROMPT, user_prompt)

    def generate_final_summary(self, reduced: dict[str, Any]) -> dict[str, Any]:
        user_prompt = (
            "Generate the final grounded academic-paper summary JSON.\n"
            f"Reduced evidence:\n{json.dumps(reduced, ensure_ascii=False)}"
        )
        return self._chat_json(FINAL_SYNTHESIS_SYSTEM_PROMPT, user_prompt)

    def generate_collection_synthesis(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_prompt = (
            "Synthesize the current state of this research collection.\n"
            "Treat references as external evidence, notes as internal reasoning artifacts, meetings as discussions, "
            "and work links as execution context.\n"
            f"Collection payload:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        return self._chat_json(COLLECTION_SYNTHESIS_SYSTEM_PROMPT, user_prompt)

    # ── Summarize reference ────────────────────────────────────────────

    def summarize_reference(self, project_id: uuid.UUID, reference_id: uuid.UUID) -> ResearchReference:
        ref = self.db.scalar(
            select(ResearchReference).where(
                ResearchReference.project_id == project_id,
                ResearchReference.id == reference_id,
            )
        )
        if not ref:
            raise NotFoundError("Reference not found.")
        summary_payload = self._summarize_reference_payload(project_id, ref)
        ref.ai_summary = json.dumps(summary_payload, ensure_ascii=False, indent=2)
        ref.ai_summary_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(ref)
        return ref

    def summarize_bibliography_reference(self, bibliography_reference_id: uuid.UUID) -> BibliographyReference:
        ref = self.db.scalar(
            select(BibliographyReference).where(BibliographyReference.id == bibliography_reference_id)
        )
        if not ref:
            raise NotFoundError("Bibliography reference not found.")
        summary_payload = self._summarize_bibliography_reference_payload(ref)
        ref.ai_summary = json.dumps(summary_payload, ensure_ascii=False, indent=2)
        ref.ai_summary_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(ref)
        return ref

    def extract_bibliography_concepts(self, bibliography_reference_id: uuid.UUID) -> list[str]:
        ref = self.db.scalar(
            select(BibliographyReference).where(BibliographyReference.id == bibliography_reference_id)
        )
        if not ref:
            raise NotFoundError("Bibliography reference not found.")
        abstract = (ref.abstract or "").strip()
        if not abstract:
            raise ValidationError("Abstract not available for concept extraction.")
        payload = self._chat_json(
            CONCEPT_EXTRACTION_SYSTEM_PROMPT,
            (
                f"Title: {ref.title.strip()}\n\n"
                f"Abstract:\n{abstract}\n"
            ),
        )
        raw_items = payload.get("concepts")
        if not isinstance(raw_items, list):
            return []
        concepts: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            label = " ".join(str(item or "").strip().split())
            if not label:
                continue
            canonical = label.lower()
            if canonical in GENERIC_CONCEPT_TERMS:
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            concepts.append(label[:96])
        return concepts[:12]

    # ── Synthesize collection ──────────────────────────────────────────

    def synthesize_collection(self, project_id: uuid.UUID, collection_id: uuid.UUID) -> ResearchCollection:
        collection = self.db.scalar(
            select(ResearchCollection).where(
                ResearchCollection.project_id == project_id,
                ResearchCollection.id == collection_id,
            )
        )
        if not collection:
            raise NotFoundError("Collection not found.")

        # Gather all notes
        notes = self.db.scalars(
            select(ResearchNote).where(ResearchNote.collection_id == collection_id)
            .order_by(ResearchNote.created_at)
        ).all()

        # Gather all reference summaries
        refs = self.db.scalars(
            select(ResearchReference).where(ResearchReference.collection_id == collection_id)
            .order_by(ResearchReference.created_at)
        ).all()

        linked_wps = self.db.execute(
            select(WorkPackage.code, WorkPackage.title)
            .join(research_collection_wps, research_collection_wps.c.wp_id == WorkPackage.id)
            .where(research_collection_wps.c.collection_id == collection_id)
            .order_by(WorkPackage.code)
        ).all()
        linked_tasks = self.db.execute(
            select(Task.code, Task.title, Task.execution_status)
            .join(research_collection_tasks, research_collection_tasks.c.task_id == Task.id)
            .where(research_collection_tasks.c.collection_id == collection_id)
            .order_by(Task.code)
        ).all()
        linked_deliverables = self.db.execute(
            select(Deliverable.code, Deliverable.title, Deliverable.workflow_status)
            .join(research_collection_deliverables, research_collection_deliverables.c.deliverable_id == Deliverable.id)
            .where(research_collection_deliverables.c.collection_id == collection_id)
            .order_by(Deliverable.code)
        ).all()
        linked_meetings = self.db.scalars(
            select(MeetingRecord)
            .join(research_collection_meetings, research_collection_meetings.c.meeting_id == MeetingRecord.id)
            .where(research_collection_meetings.c.collection_id == collection_id)
            .order_by(MeetingRecord.starts_at.desc())
            .limit(8)
        ).all()

        payload = self._collection_synthesis_payload(
            collection=collection,
            notes=notes,
            refs=refs,
            linked_wps=linked_wps,
            linked_tasks=linked_tasks,
            linked_deliverables=linked_deliverables,
            linked_meetings=linked_meetings,
        )

        has_material = any(
            payload[key]
            for key in (
                "hypothesis",
                "open_questions",
                "notes",
                "references",
                "meetings",
                "linked_tasks",
                "linked_deliverables",
                "linked_work_packages",
            )
        )
        if not has_material:
            raise NotFoundError("No content available to synthesize.")

        synthesis = self.generate_collection_synthesis(payload)

        collection.ai_synthesis = json.dumps(synthesis, ensure_ascii=False, indent=2)
        collection.ai_synthesis_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(collection)
        return collection

    def _collection_synthesis_payload(
        self,
        *,
        collection: ResearchCollection,
        notes: list[ResearchNote],
        refs: list[ResearchReference],
        linked_wps: list[tuple[str, str]],
        linked_tasks: list[tuple[str, str, Any]],
        linked_deliverables: list[tuple[str, str, Any]],
        linked_meetings: list[MeetingRecord],
    ) -> dict[str, Any]:
        output_status = collection.output_status.value if hasattr(collection.output_status, "value") else str(collection.output_status)
        return {
            "collection_title": collection.title,
            "description": collection.description,
            "hypothesis": collection.hypothesis,
            "open_questions": collection.open_questions or [],
            "output": {
                "title": collection.target_output_title,
                "status": output_status,
                "overleaf_url": collection.overleaf_url,
            },
            "linked_work_packages": [
                {"code": code, "title": title}
                for code, title in linked_wps
            ],
            "linked_tasks": [
                {
                    "code": code,
                    "title": title,
                    "status": status.value if hasattr(status, "value") else str(status),
                }
                for code, title, status in linked_tasks
            ],
            "linked_deliverables": [
                {
                    "code": code,
                    "title": title,
                    "status": status.value if hasattr(status, "value") else str(status),
                }
                for code, title, status in linked_deliverables
            ],
            "notes": [
                {
                    "title": note.title,
                    "type": note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type),
                    "content": note.content,
                }
                for note in notes
            ],
            "references": [
                {
                    "title": ref.title,
                    "venue": ref.venue,
                    "reading_status": ref.reading_status.value if hasattr(ref.reading_status, "value") else str(ref.reading_status),
                    "summary": self._summary_payload_as_text(ref.ai_summary) if ref.ai_summary else None,
                    "abstract": ref.abstract,
                }
                for ref in refs
            ],
            "meetings": [
                {
                    "title": meeting.title,
                    "starts_at": meeting.starts_at.isoformat() if meeting.starts_at else None,
                    "summary": meeting.summary,
                    "excerpt": (meeting.content_text or "")[:1200],
                }
                for meeting in linked_meetings
            ],
        }

    # ── Extract metadata from PDF ──────────────────────────────────────

    def extract_metadata_from_pdf(self, project_id: uuid.UUID, document_key: uuid.UUID) -> dict:
        doc = self.db.scalar(
            select(ProjectDocument).where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.document_key == document_key,
            )
        )
        if not doc:
            raise NotFoundError("Document not found.")

        chunks = self.db.scalars(
            select(DocumentChunk.content)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .limit(5)
        ).all()

        if not chunks:
            raise NotFoundError("No document content available.")

        combined = "\n\n".join(c for c in chunks if c)[:6000]
        result = self._chat(
            system=(
                "You are an academic metadata extraction assistant. "
                "Extract the following from the paper text: title, authors (as a JSON array of strings), "
                "year (integer), venue/journal name, and abstract. "
                "Return ONLY valid JSON with keys: title, authors, year, venue, abstract. "
                "If a field is not found, use null."
            ),
            user=combined,
        )

        import json
        try:
            # Try to parse JSON from response (may be wrapped in markdown code block)
            cleaned = result.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            metadata = json.loads(cleaned)
        except json.JSONDecodeError:
            metadata = {"title": None, "authors": [], "year": None, "venue": None, "abstract": None}

        return {
            "title": metadata.get("title"),
            "authors": metadata.get("authors") or [],
            "year": metadata.get("year"),
            "venue": metadata.get("venue"),
            "abstract": metadata.get("abstract"),
        }

    # ── Chunk and embed research content ───────────────────────────────

    def embed_research_content(self, project_id: uuid.UUID) -> int:
        """Chunk notes and reference abstracts into ResearchChunk rows, then embed them."""
        # Delete existing chunks for this project
        self.db.execute(
            delete(ResearchChunk).where(ResearchChunk.project_id == project_id)
        )

        chunks_created = 0

        # Chunk notes
        notes = self.db.scalars(
            select(ResearchNote).where(ResearchNote.project_id == project_id)
        ).all()
        for note in notes:
            note_kind = note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type)
            collection_title = ""
            if note.collection_id:
                collection_title = (
                    self.db.scalar(
                        select(ResearchCollection.title).where(ResearchCollection.id == note.collection_id)
                    )
                    or ""
                )
            parts = []
            if collection_title:
                parts.append(f"Collection: {collection_title}")
            parts.append(f"Artifact Type: {note_kind}")
            parts.append(f"Title: {note.title}")
            parts.append(note.content)
            text = "\n".join(parts)
            for i, chunk_text in enumerate(self._split_text(text)):
                chunk = ResearchChunk(
                    source_type=f"note:{note_kind}",
                    source_id=note.id,
                    project_id=project_id,
                    chunk_index=i,
                    content=chunk_text,
                )
                self.db.add(chunk)
                chunks_created += 1

        # Chunk reference abstracts
        refs = self.db.scalars(
            select(ResearchReference).where(ResearchReference.project_id == project_id)
        ).all()
        for ref in refs:
            collection_title = ""
            if ref.collection_id:
                collection_title = (
                    self.db.scalar(
                        select(ResearchCollection.title).where(ResearchCollection.id == ref.collection_id)
                    )
                    or ""
                )
            text_parts = []
            if collection_title:
                text_parts.append(f"Collection: {collection_title}")
            text_parts.append("Artifact Type: reference")
            text_parts.append(f"Title: {ref.title}")
            if ref.venue:
                text_parts.append(f"Venue: {ref.venue}")
            if ref.year:
                text_parts.append(f"Year: {ref.year}")
            if ref.abstract:
                text_parts.append(ref.abstract)
            if ref.ai_summary:
                text_parts.append(self._summary_payload_as_text(ref.ai_summary))
            text = "\n\n".join(text_parts)
            for i, chunk_text in enumerate(self._split_text(text)):
                chunk = ResearchChunk(
                    source_type="reference",
                    source_id=ref.id,
                    project_id=project_id,
                    chunk_index=i,
                    content=chunk_text,
                )
                self.db.add(chunk)
                chunks_created += 1

        linked_meetings = self.db.execute(
            select(ResearchCollection.title, MeetingRecord)
            .join(research_collection_meetings, research_collection_meetings.c.collection_id == ResearchCollection.id)
            .join(MeetingRecord, research_collection_meetings.c.meeting_id == MeetingRecord.id)
            .where(ResearchCollection.project_id == project_id)
        ).all()
        for collection_title, meeting in linked_meetings:
            parts = []
            if collection_title:
                parts.append(f"Collection: {collection_title}")
            parts.append("Artifact Type: discussion")
            parts.append(f"Meeting: {meeting.title}")
            if meeting.summary:
                parts.append(f"Summary: {meeting.summary}")
            elif meeting.content_text:
                parts.append(meeting.content_text)
            text = "\n".join(parts).strip()
            if not text:
                continue
            for i, chunk_text in enumerate(self._split_text(text)):
                chunk = ResearchChunk(
                    source_type="meeting_discussion",
                    source_id=meeting.id,
                    project_id=project_id,
                    chunk_index=i,
                    content=chunk_text,
                )
                self.db.add(chunk)
                chunks_created += 1

        self.db.flush()

        # Embed the chunks
        from app.services.embedding_service import EmbeddingService
        embed_svc = EmbeddingService(self.db)
        unembedded = self.db.scalars(
            select(ResearchChunk).where(
                ResearchChunk.project_id == project_id,
            )
        ).all()
        if unembedded:
            embed_svc._embed_chunk_batch(unembedded)

        self.db.commit()
        return chunks_created

    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks of roughly CHUNK_SIZE characters."""
        if len(text) <= CHUNK_SIZE:
            return [text]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            if end < len(text):
                # Try to break at sentence boundary
                for sep in [". ", "\n", " "]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start:
                        end = last_sep + len(sep)
                        break
            chunks.append(text[start:end].strip())
            start = end
        return [c for c in chunks if c]

    def _summarize_reference_payload(self, project_id: uuid.UUID, ref: ResearchReference) -> dict[str, Any]:
        doc = None
        if ref.document_key:
            doc = self.db.scalar(
                select(ProjectDocument).where(
                    ProjectDocument.project_id == project_id,
                    ProjectDocument.document_key == ref.document_key,
                )
            )

        if doc:
            queries = self.build_summary_queries(
                {
                    "title": ref.title,
                    "authors": ref.authors or [],
                    "abstract": ref.abstract,
                    "metadata": doc.metadata_json or {},
                }
            )
            selected_chunks = self.retrieve_summary_chunks(doc.id, queries, per_query_k=5)
            if selected_chunks:
                map_outputs = self.summarize_chunk_map(selected_chunks)
                reduced = self.reduce_summaries(map_outputs)
                final_summary = self.generate_final_summary(reduced)
                if not final_summary.get("title"):
                    final_summary["title"] = ref.title
                return final_summary

        if ref.abstract:
            return self._summarize_abstract_only(ref)

        raise NotFoundError("No content available to summarize.")

    def _summarize_bibliography_reference_payload(self, ref: BibliographyReference) -> dict[str, Any]:
        doc = None
        if ref.document_key and ref.source_project_id:
            doc = self.db.scalar(
                select(ProjectDocument).where(
                    ProjectDocument.project_id == ref.source_project_id,
                    ProjectDocument.document_key == ref.document_key,
                )
            )

        if doc:
            queries = self.build_summary_queries(
                {
                    "title": ref.title,
                    "authors": ref.authors or [],
                    "abstract": ref.abstract,
                    "metadata": doc.metadata_json or {},
                }
            )
            selected_chunks = self.retrieve_summary_chunks(doc.id, queries, per_query_k=5)
            if selected_chunks:
                map_outputs = self.summarize_chunk_map(selected_chunks)
                reduced = self.reduce_summaries(map_outputs)
                final_summary = self.generate_final_summary(reduced)
                if not final_summary.get("title"):
                    final_summary["title"] = ref.title
                return final_summary

        if ref.abstract:
            return self._summarize_abstract_only(ref)

        raise NotFoundError("No content available to summarize.")

    def _boundary_chunks(self, chunks: list[DocumentChunk]) -> list[SummaryChunk]:
        selected: list[SummaryChunk] = []
        total = len(chunks)

        def bucket_for_index(index: int) -> str:
            if total <= 1:
                return "beginning"
            ratio = index / max(1, total - 1)
            if ratio <= 0.25:
                return "beginning"
            if ratio >= 0.75:
                return "ending"
            return "middle"

        for chunk in chunks[:SUMMARY_BEGINNING_CHUNKS]:
            selected.append(
                SummaryChunk(
                    id=f"chunk_{chunk.chunk_index}",
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    role=self.classify_chunk_role(chunk),
                    score=1.0,
                    reasons={"boundary"},
                    position_bucket=bucket_for_index(chunk.chunk_index),
                )
            )

        if total > SUMMARY_BEGINNING_CHUNKS + SUMMARY_ENDING_CHUNKS:
            middle_start = max(0, total // 2 - SUMMARY_MIDDLE_CHUNKS // 2)
            middle_slice = chunks[middle_start : middle_start + SUMMARY_MIDDLE_CHUNKS]
            for chunk in middle_slice:
                selected.append(
                    SummaryChunk(
                        id=f"chunk_{chunk.chunk_index}",
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        role=self.classify_chunk_role(chunk),
                        score=0.8,
                        reasons={"boundary"},
                        position_bucket=bucket_for_index(chunk.chunk_index),
                    )
                )

        for chunk in chunks[-SUMMARY_ENDING_CHUNKS:]:
            selected.append(
                SummaryChunk(
                    id=f"chunk_{chunk.chunk_index}",
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    role=self.classify_chunk_role(chunk),
                    score=1.0,
                    reasons={"boundary"},
                    position_bucket=bucket_for_index(chunk.chunk_index),
                )
            )
        return selected

    def _heuristic_role_chunks(self, chunks: list[DocumentChunk]) -> list[SummaryChunk]:
        selected: list[SummaryChunk] = []
        seen_roles: set[str] = set()
        total = len(chunks)
        for chunk in chunks:
            role = self.classify_chunk_role(chunk)
            if role in {"other"} or role in seen_roles:
                continue
            seen_roles.add(role)
            selected.append(
                SummaryChunk(
                    id=f"chunk_{chunk.chunk_index}",
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    role=role,
                    score=0.7,
                    reasons={"heuristic_role"},
                    position_bucket=self._position_bucket(chunk.chunk_index, total),
                )
            )
        return selected

    def _semantic_query_chunks(self, doc_id: uuid.UUID, queries: list[str], per_query_k: int) -> list[SummaryChunk]:
        from app.services.embedding_service import EmbeddingService

        embed_svc = EmbeddingService(self.db)
        try:
            query_embeddings = embed_svc.embed_texts(queries)
        except Exception:
            logger.exception("Summary query embedding generation failed")
            return []

        total_chunks = int(
            self.db.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc_id)
            )
            or 0
        )
        results: list[SummaryChunk] = []
        for query, embedding in zip(queries, query_embeddings):
            cosine_distance = DocumentChunk.embedding.cosine_distance(embedding)
            rows = self.db.execute(
                select(DocumentChunk, (1 - cosine_distance).label("similarity"))
                .where(
                    DocumentChunk.document_id == doc_id,
                    DocumentChunk.embedding.isnot(None),
                )
                .order_by(cosine_distance)
                .limit(per_query_k)
            ).all()
            for chunk, similarity in rows:
                results.append(
                    SummaryChunk(
                        id=f"chunk_{chunk.chunk_index}",
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        role=self.classify_chunk_role(chunk),
                        score=float(similarity),
                        reasons={query},
                        position_bucket=self._position_bucket(chunk.chunk_index, total_chunks),
                    )
                )
        return results

    def _merge_candidate(self, candidates: dict[str, SummaryChunk], selected: SummaryChunk) -> None:
        existing = candidates.get(selected.id)
        if existing is None:
            candidates[selected.id] = selected
            return
        existing.score = max(existing.score, selected.score)
        existing.reasons.update(selected.reasons)
        if existing.role == "other" and selected.role != "other":
            existing.role = selected.role

    def _group_summary_chunks(self, chunks: list[SummaryChunk]) -> list[list[SummaryChunk]]:
        groups: list[list[SummaryChunk]] = []
        current: list[SummaryChunk] = []
        for chunk in chunks:
            if not current:
                current = [chunk]
                continue
            previous = current[-1]
            if len(current) < SUMMARY_MAP_GROUP_SIZE and chunk.chunk_index - previous.chunk_index <= 1:
                current.append(chunk)
                continue
            groups.append(current)
            current = [chunk]
        if current:
            groups.append(current)
        return groups

    def _position_bucket(self, chunk_index: int, total_chunks: int) -> str:
        if total_chunks <= 1:
            return "beginning"
        ratio = chunk_index / max(1, total_chunks - 1)
        if ratio <= 0.25:
            return "beginning"
        if ratio >= 0.75:
            return "ending"
        return "middle"

    def _summarize_abstract_only(self, ref: ResearchReference) -> dict[str, Any]:
        abstract_text = ref.abstract or ""
        payload = self._chat_json(
            FINAL_SYNTHESIS_SYSTEM_PROMPT,
            (
                "Generate the final academic-paper summary JSON using only the grounded abstract evidence.\n"
                f"Evidence:\n{json.dumps([{'claim': abstract_text, 'chunk_ids': ['abstract']}], ensure_ascii=False)}"
            ),
        )
        if not payload.get("title"):
            payload["title"] = ref.title
        return payload
