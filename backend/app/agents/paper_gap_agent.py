"""Paper gap agent — draft motivation and research questions from gap logs."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agents.language_utils import language_instruction
from app.llm.factory import get_text_provider
from app.llm.json_utils import parse_json_object
from app.models.project import Project
from app.models.research import ResearchCollection
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.research_service import ResearchService

logger = logging.getLogger(__name__)


@dataclass
class PaperGapDraft:
    motivation: str
    questions: list[str] = field(default_factory=list)


class PaperGapAgent:
    def __init__(self) -> None:
        self.last_error: str | None = None

    def build_gap_draft(self, project_id: uuid.UUID, collection_id: uuid.UUID, db: Session, *, space_id: uuid.UUID | None = None) -> PaperGapDraft:
        service = ResearchService(db)
        project = db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        collection = service.get_collection_for_space(space_id, collection_id) if space_id else service.get_collection(project_id, collection_id)
        notes, _ = service.list_notes_for_space(space_id, collection_id=collection_id, page=1, page_size=100) if space_id else service.list_notes(project_id, collection_id=collection_id, page=1, page_size=100)
        gap_notes = [item for item in notes if (item.lane or "").strip() == "gap"]
        if not gap_notes:
            raise ValidationError("No gap logs available.")

        references, _ = service.list_references_for_space(space_id, collection_id=collection_id, page=1, page_size=100) if space_id else service.list_references(project_id, collection_id=collection_id, page=1, page_size=100)
        prompt = self._build_prompt(project, collection, gap_notes, references, service)
        raw = self._generate_text(prompt)
        payload = parse_json_object(raw) if raw else None
        if not payload:
            if self.last_error:
                raise ValueError(self.last_error)
            raise ValueError("Agent returned invalid output.")

        motivation = str(payload.get("motivation") or "").strip()
        questions = [
            " ".join(str(item or "").strip().split())[:1000]
            for item in (payload.get("questions") or [])
            if " ".join(str(item or "").strip().split())
        ]
        if not motivation and not questions:
            raise ValueError("Agent returned an empty draft.")
        return PaperGapDraft(
            motivation=motivation[:4000],
            questions=questions[:7],
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
            logger.warning("Paper gap draft failed: %s", exc)
            return ""

    def _build_prompt(
        self,
        project: Project,
        collection: ResearchCollection,
        gap_notes: list[Any],
        references: list[Any],
        service: ResearchService,
    ) -> str:
        note_items = []
        linked_reference_ids: set[str] = set()
        for item in gap_notes[:100]:
            refs = [str(ref_id) for ref_id in service.get_note_reference_ids(item.id)]
            linked_reference_ids.update(refs)
            note_items.append({
                "id": str(item.id),
                "title": item.title,
                "type": item.note_type.value if hasattr(item.note_type, "value") else str(item.note_type),
                "content": item.content[:2000],
                "linked_reference_ids": refs,
            })

        reference_items = []
        for item in references[:100]:
            item_id = str(item.id)
            if linked_reference_ids and item_id not in linked_reference_ids:
                continue
            reference_items.append({
                "id": item_id,
                "title": item.title,
                "authors": item.authors or [],
                "abstract": (item.abstract or "")[:1800],
                "ai_summary": (item.ai_summary or "")[:3000],
            })

        schema = {
            "motivation": "short grounded paragraph",
            "questions": ["clear research questions phrased as questions"],
        }

        return (
            "You draft a paper motivation and research questions from study gap logs.\n"
            "Use only the provided gap logs and linked literature.\n"
            "Do not force a workflow. Synthesize what the material already suggests.\n"
            "The motivation should explain the gap, why it matters, and what direction the study can take.\n"
            "Questions should be concrete, research-oriented, and phrased as actual questions.\n"
            "Return JSON only.\n\n"
            f"PROJECT: {project.title}\n"
            f"STUDY: {collection.title}\n"
            f"STUDY FOCUS: {(collection.description or collection.hypothesis or '').strip()}\n"
            f"EXISTING MOTIVATION: {(collection.paper_motivation or '').strip()}\n"
            f"EXISTING QUESTIONS: {json.dumps(collection.paper_questions or [], ensure_ascii=False)}\n"
            f"GAP LOGS: {json.dumps(note_items, ensure_ascii=False)}\n"
            f"LINKED REFERENCES: {json.dumps(reference_items, ensure_ascii=False)}\n"
            f"OUTPUT SCHEMA: {json.dumps(schema, ensure_ascii=False)}\n"
            + language_instruction(getattr(project, "language", None))
        )
