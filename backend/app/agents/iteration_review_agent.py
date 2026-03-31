"""Iteration review agent — grounded review over a study time span."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.language_utils import language_instruction
from app.llm.factory import get_text_provider
from app.llm.json_utils import parse_json_object
from app.models.project import Project
from app.models.research import ResearchCollection
from app.services.onboarding_service import NotFoundError
from app.services.research_service import ResearchService

logger = logging.getLogger(__name__)


@dataclass
class IterationReview:
    summary: str = ""
    what_changed: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    unclear_points: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    reviewed_at: str = ""


class IterationReviewAgent:
    def __init__(self) -> None:
        self.last_error: str | None = None

    def review_iteration(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        iteration: dict[str, Any],
        db: Session,
        *,
        space_id: uuid.UUID | None = None,
    ) -> IterationReview:
        service = ResearchService(db)
        project = db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        collection = service.get_collection_for_space(space_id, collection_id) if space_id else service.get_collection(project_id, collection_id)
        references, _ = service.list_references_for_space(space_id, collection_id=collection_id, page=1, page_size=100) if space_id else service.list_references(project_id, collection_id=collection_id, page=1, page_size=100)
        notes, _ = service.list_notes_for_space(space_id, collection_id=collection_id, page=1, page_size=100) if space_id else service.list_notes(project_id, collection_id=collection_id, page=1, page_size=100)

        start_date = str(iteration.get("start_date") or "").strip()
        end_date = str(iteration.get("end_date") or "").strip()
        filtered_references = [
            item for item in references
            if (not start_date or str(item.created_at.date()) >= start_date) and (not end_date or str(item.created_at.date()) <= end_date)
        ]
        filtered_notes = [
            item for item in notes
            if (not start_date or str(item.created_at.date()) >= start_date) and (not end_date or str(item.created_at.date()) <= end_date)
        ]

        prompt = self._build_prompt(project, collection, iteration, filtered_references, filtered_notes, service)
        raw = self._generate_text(prompt)
        payload = parse_json_object(raw) if raw else None
        if not payload:
            if self.last_error:
                raise ValueError(self.last_error)
            raise ValueError("Agent returned invalid iteration review output.")

        now = datetime.now(timezone.utc).isoformat()
        return IterationReview(
            summary=str(payload.get("summary") or "").strip()[:4000],
            what_changed=[str(item).strip()[:400] for item in (payload.get("what_changed") or []) if str(item).strip()],
            improvements=[str(item).strip()[:400] for item in (payload.get("improvements") or []) if str(item).strip()],
            regressions=[str(item).strip()[:400] for item in (payload.get("regressions") or []) if str(item).strip()],
            unclear_points=[str(item).strip()[:400] for item in (payload.get("unclear_points") or []) if str(item).strip()],
            next_actions=[str(item).strip()[:400] for item in (payload.get("next_actions") or []) if str(item).strip()],
            reviewed_at=now,
        )

    def _generate_text(self, prompt: str) -> str:
        self.last_error = None
        try:
            return get_text_provider().generate(
                [{"role": "user", "content": prompt}],
                temperature=0,
                timeout=180,
            )
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Iteration review failed: %s", exc)
            return ""

    def _build_prompt(
        self,
        project: Project,
        collection: ResearchCollection,
        iteration: dict[str, Any],
        references: list[Any],
        notes: list[Any],
        service: ResearchService,
    ) -> str:
        reference_items = []
        for item in references[:80]:
            reference_items.append({
                "id": str(item.id),
                "title": item.title,
                "abstract": (item.abstract or "")[:1200],
                "summary": (item.ai_summary or "")[:1600],
                "reading_status": item.reading_status.value if hasattr(item.reading_status, "value") else str(item.reading_status),
            })

        note_items = []
        for item in notes[:120]:
            note_items.append({
                "id": str(item.id),
                "title": item.title,
                "type": item.note_type.value if hasattr(item.note_type, "value") else str(item.note_type),
                "content": item.content[:1600],
                "linked_reference_ids": [str(ref_id) for ref_id in service.get_note_reference_ids(item.id)],
            })

        schema = {
            "summary": "string",
            "what_changed": ["short items"],
            "improvements": ["short items"],
            "regressions": ["short items"],
            "unclear_points": ["short items"],
            "next_actions": ["short items"],
        }

        return (
            "You review a research iteration critically.\n"
            "Use only the provided notes and references from the iteration date range.\n"
            "Summarize what changed, what improved, what regressed, what remains unclear, and what should happen next.\n"
            "Be precise and practical. Return JSON only.\n\n"
            f"PROJECT: {project.title}\n"
            f"STUDY: {collection.title}\n"
            f"FOCUS: {(collection.description or collection.hypothesis or '').strip()}\n"
            f"ITERATION: {json.dumps(iteration, ensure_ascii=False)}\n"
            f"NOTES: {json.dumps(note_items, ensure_ascii=False)}\n"
            f"REFERENCES: {json.dumps(reference_items, ensure_ascii=False)}\n"
            f"OUTPUT SCHEMA: {json.dumps(schema)}\n"
            + language_instruction(getattr(project, "language", None))
        )
