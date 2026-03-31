"""Paper outline agent — grounded outline builder for research studies."""

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
from app.services.onboarding_service import NotFoundError
from app.services.research_service import ResearchService

logger = logging.getLogger(__name__)


@dataclass
class PaperOutlineSection:
    title: str
    question_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    note_ids: list[str] = field(default_factory=list)
    status: str = "not_started"


class PaperOutlineAgent:
    def __init__(self) -> None:
        self.last_error: str | None = None

    def build_collection_outline(self, project_id: uuid.UUID, collection_id: uuid.UUID, db: Session, *, space_id: uuid.UUID | None = None) -> list[PaperOutlineSection]:
        service = ResearchService(db)
        project = db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        collection = service.get_collection_for_space(space_id, collection_id) if space_id else service.get_collection(project_id, collection_id)
        questions = [item for item in (collection.paper_questions or []) if isinstance(item, dict) and str(item.get("text") or "").strip()]
        claims = [item for item in (collection.paper_claims or []) if isinstance(item, dict) and str(item.get("text") or "").strip()]
        existing_sections = [item for item in (collection.paper_sections or []) if isinstance(item, dict)]

        references, _ = service.list_references_for_space(space_id, collection_id=collection_id, page=1, page_size=100) if space_id else service.list_references(project_id, collection_id=collection_id, page=1, page_size=100)
        notes, _ = service.list_notes_for_space(space_id, collection_id=collection_id, page=1, page_size=100) if space_id else service.list_notes(project_id, collection_id=collection_id, page=1, page_size=100)
        if not questions and not claims and not references and not notes:
            return []

        prompt = self._build_prompt(project, collection, questions, claims, existing_sections, references, notes, service)
        raw = self._generate_text(prompt)
        payload = parse_json_object(raw) if raw else None
        if not payload or not isinstance(payload.get("sections"), list):
            if self.last_error:
                raise ValueError(self.last_error)
            raise ValueError("Agent returned invalid outline output.")

        valid_question_ids = {str(item.get("id")) for item in questions}
        valid_claim_ids = {str(item.get("id")) for item in claims}
        valid_reference_ids = {str(item.id) for item in references}
        valid_note_ids = {str(item.id) for item in notes}

        sections: list[PaperOutlineSection] = []
        for item in payload["sections"]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            status = str(item.get("status") or "not_started").strip().lower()
            if status not in {"not_started", "drafting", "ready"}:
                status = "not_started"
            sections.append(
                PaperOutlineSection(
                    title=title[:255],
                    question_ids=[str(entry) for entry in (item.get("question_ids") or []) if str(entry) in valid_question_ids],
                    claim_ids=[str(entry) for entry in (item.get("claim_ids") or []) if str(entry) in valid_claim_ids],
                    reference_ids=[str(entry) for entry in (item.get("reference_ids") or []) if str(entry) in valid_reference_ids],
                    note_ids=[str(entry) for entry in (item.get("note_ids") or []) if str(entry) in valid_note_ids],
                    status=status,
                )
            )
        return sections

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
            logger.warning("Paper outline generation failed: %s", exc)
            return ""

    def _build_prompt(
        self,
        project: Project,
        collection: ResearchCollection,
        questions: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        existing_sections: list[dict[str, Any]],
        references: list[Any],
        notes: list[Any],
        service: ResearchService,
    ) -> str:
        reference_items = []
        for item in references[:80]:
            reference_items.append({
                "id": str(item.id),
                "title": item.title,
                "authors": item.authors or [],
                "abstract": (item.abstract or "")[:1200],
                "summary": (item.ai_summary or "")[:1600],
                "reading_status": item.reading_status.value if hasattr(item.reading_status, "value") else str(item.reading_status),
            })

        note_items = []
        for item in notes[:80]:
            note_items.append({
                "id": str(item.id),
                "title": item.title,
                "type": item.note_type.value if hasattr(item.note_type, "value") else str(item.note_type),
                "content": item.content[:1200],
                "linked_reference_ids": [str(ref_id) for ref_id in service.get_note_reference_ids(item.id)],
            })

        schema = {
            "sections": [
                {
                    "title": "string",
                    "question_ids": ["question ids from input only"],
                    "claim_ids": ["claim ids from input only"],
                    "reference_ids": ["reference ids from input only"],
                    "note_ids": ["note ids from input only"],
                    "status": "not_started|drafting|ready",
                }
            ]
        }

        return (
            "You build a grounded paper outline for a research study.\n"
            "Use only the provided questions, claims, references, and notes.\n"
            "Produce a practical, editable section structure for the paper.\n"
            "Prefer a concise outline with meaningful sections rather than many tiny sections.\n"
            "Use references and notes only when they clearly belong to a section.\n"
            "Return JSON only.\n\n"
            f"PROJECT: {project.title}\n"
            f"STUDY: {collection.title}\n"
            f"FOCUS: {(collection.description or collection.hypothesis or '').strip()}\n"
            f"PAPER TITLE: {(collection.target_output_title or '').strip()}\n"
            f"PAPER VENUE: {(collection.target_venue or '').strip()}\n"
            f"QUESTIONS: {json.dumps(questions, ensure_ascii=False)}\n"
            f"CLAIMS: {json.dumps(claims, ensure_ascii=False)}\n"
            f"EXISTING SECTIONS: {json.dumps(existing_sections, ensure_ascii=False)}\n"
            f"REFERENCES: {json.dumps(reference_items, ensure_ascii=False)}\n"
            f"NOTES: {json.dumps(note_items, ensure_ascii=False)}\n"
            f"OUTPUT SCHEMA: {json.dumps(schema)}\n"
            + language_instruction(getattr(project, "language", None))
        )
