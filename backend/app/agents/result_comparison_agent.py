"""Result comparison agent — grounded comparison across recent study results."""

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
from app.services.onboarding_service import NotFoundError
from app.services.research_service import ResearchService

logger = logging.getLogger(__name__)


@dataclass
class ResultComparisonReport:
    summary: str = ""
    likely_improvements: list[str] = field(default_factory=list)
    likely_regressions: list[str] = field(default_factory=list)
    likely_causes: list[str] = field(default_factory=list)
    next_experiment_changes: list[str] = field(default_factory=list)
    compared_result_ids: list[str] = field(default_factory=list)


class ResultComparisonAgent:
    def __init__(self) -> None:
        self.last_error: str | None = None

    def compare_recent_results(
        self,
        project_id: uuid.UUID,
        collection_id: uuid.UUID,
        db: Session,
        limit: int = 3,
        *,
        space_id: uuid.UUID | None = None,
    ) -> ResultComparisonReport:
        service = ResearchService(db)
        project = db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        collection = service.get_collection_for_space(space_id, collection_id) if space_id else service.get_collection(project_id, collection_id)
        raw_results = [item for item in (collection.study_results or []) if isinstance(item, dict)]
        if len(raw_results) < 2:
            raise ValueError("At least two results are required.")

        def _result_ts(item: dict[str, Any]) -> str:
            return str(item.get("updated_at") or item.get("created_at") or "")

        recent_results = sorted(raw_results, key=_result_ts, reverse=True)[: max(2, min(limit, 5))]
        prompt = self._build_prompt(
            project.title,
            collection.title,
            collection.description or collection.hypothesis or "",
            recent_results,
            getattr(project, "language", None),
        )
        raw = self._generate_text(prompt)
        payload = parse_json_object(raw) if raw else None
        if not payload:
            if self.last_error:
                raise ValueError(self.last_error)
            raise ValueError("Agent returned invalid comparison output.")

        valid_result_ids = {str(item.get("id") or "") for item in recent_results}
        return ResultComparisonReport(
            summary=str(payload.get("summary") or "").strip()[:4000],
            likely_improvements=[str(item).strip()[:400] for item in (payload.get("likely_improvements") or []) if str(item).strip()],
            likely_regressions=[str(item).strip()[:400] for item in (payload.get("likely_regressions") or []) if str(item).strip()],
            likely_causes=[str(item).strip()[:400] for item in (payload.get("likely_causes") or []) if str(item).strip()],
            next_experiment_changes=[str(item).strip()[:400] for item in (payload.get("next_experiment_changes") or []) if str(item).strip()],
            compared_result_ids=[str(item) for item in (payload.get("compared_result_ids") or []) if str(item) in valid_result_ids],
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
            logger.warning("Result comparison failed: %s", exc)
            return ""

    def _build_prompt(
        self,
        project_title: str,
        study_title: str,
        focus: str,
        results: list[dict[str, Any]],
        language: str | None,
    ) -> str:
        schema = {
            "summary": "string",
            "likely_improvements": ["short items"],
            "likely_regressions": ["short items"],
            "likely_causes": ["short items"],
            "next_experiment_changes": ["short items"],
            "compared_result_ids": ["result ids from input only"],
        }
        return (
            "You compare recent research results critically.\n"
            "Use only the provided results.\n"
            "Identify what likely improved, what likely regressed, what may have caused the shifts, and what the next experiment should change.\n"
            "Be practical and concise. Return JSON only.\n\n"
            f"PROJECT: {project_title}\n"
            f"STUDY: {study_title}\n"
            f"FOCUS: {focus.strip()}\n"
            f"RESULTS: {json.dumps(results, ensure_ascii=False)}\n"
            f"OUTPUT SCHEMA: {json.dumps(schema)}\n"
            + language_instruction(language)
        )
