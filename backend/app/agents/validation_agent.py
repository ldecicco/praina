"""Validation agent — structural checks + LLM-powered advisory warnings."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agents.chat_action_extraction_agent import ChatActionExtractionAgent
from app.services.assignment_validation_service import AssignmentValidationService, ValidationIssue
from app.services.onboarding_service import OnboardingService

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    project_id: str
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    is_valid: bool = True


class ValidationAgent:
    """
    Combines structural validation (OnboardingService + AssignmentValidationService)
    with LLM-powered advisory warnings for semantic issues.
    """

    def __init__(self) -> None:
        self._llm = ChatActionExtractionAgent()

    def run(self, project_id: uuid.UUID, db: Session) -> ValidationReport:
        pid = str(project_id)
        report = ValidationReport(project_id=pid)

        # --- Structural checks from OnboardingService ---
        onboarding_errors = OnboardingService(db).validate_project(project_id)
        for err in onboarding_errors:
            report.errors.append(ValidationIssue(
                entity_type=err.get("entity_type", ""),
                entity_id=err.get("entity_id", ""),
                code=err.get("code", ""),
                field="",
                message=err.get("message", ""),
                severity="error",
            ))

        # --- Extended structural checks ---
        extended_issues = AssignmentValidationService(db).validate(project_id)
        for issue in extended_issues:
            if issue.severity == "error":
                # Avoid duplicating issues already found by OnboardingService
                if not any(
                    e.entity_id == issue.entity_id and e.code == issue.code
                    for e in report.errors
                ):
                    report.errors.append(issue)
            else:
                report.warnings.append(issue)

        # --- LLM advisory warnings (best-effort) ---
        try:
            llm_warnings = self._llm_review(project_id, db, report)
            report.warnings.extend(llm_warnings)
        except Exception as exc:
            logger.warning("LLM validation review failed for project %s: %s", project_id, exc)

        report.is_valid = len(report.errors) == 0
        return report

    def _llm_review(
        self, project_id: uuid.UUID, db: Session, current_report: ValidationReport
    ) -> list[ValidationIssue]:
        from app.services.project_chat_service import ProjectChatService

        context = ProjectChatService(db).project_context_for_agent(project_id)
        existing_issues = [
            {"code": i.code, "message": i.message, "entity_type": i.entity_type}
            for i in current_report.errors + current_report.warnings
        ]

        prompt = self._build_review_prompt(context, existing_issues)
        raw = self._llm._generate_with_ollama_chat(prompt, allow_compaction=True)
        if not raw:
            return []
        payload = self._llm._parse_json(raw)
        if not payload or not isinstance(payload.get("warnings"), list):
            return []

        warnings: list[ValidationIssue] = []
        for item in payload["warnings"]:
            if not isinstance(item, dict):
                continue
            message = str(item.get("message") or "").strip()
            if not message:
                continue
            warnings.append(ValidationIssue(
                entity_type=str(item.get("entity_type") or "project"),
                entity_id=str(item.get("entity_id") or str(project_id)),
                code=str(item.get("code") or "LLM_ADVISORY"),
                field=str(item.get("field") or ""),
                message=message,
                severity="warning",
            ))
        return warnings

    def _build_review_prompt(
        self, context: dict[str, Any], existing_issues: list[dict]
    ) -> str:
        schema = {
            "warnings": [
                {
                    "entity_type": "work_package|task|deliverable|milestone|project",
                    "entity_id": "optional id",
                    "code": "short code e.g. NAMING_INCONSISTENCY",
                    "field": "optional field name",
                    "message": "human-readable warning",
                }
            ]
        }
        from app.agents.language_utils import language_instruction

        return (
            "You are a project validation reviewer.\n"
            "Given the project structure below, identify potential issues that are NOT "
            "already listed in the existing issues.\n"
            "Focus on:\n"
            "- Naming inconsistencies (WP/task codes that don't follow a pattern)\n"
            "- Suspiciously short task windows (1 month for complex work)\n"
            "- Deliverables or milestones with no meaningful description\n"
            "- Work packages with very broad or vague titles\n"
            "- Risks without mitigation plans\n\n"
            "Return a JSON object with a `warnings` array. Each warning has: "
            "entity_type, entity_id (optional), code, field (optional), message.\n"
            "If there are no issues, return {\"warnings\": []}.\n"
            "Return JSON only, no markdown, no commentary.\n\n"
            f"PROJECT CONTEXT:\n{json.dumps(context, default=str, ensure_ascii=False)}\n\n"
            f"ALREADY IDENTIFIED ISSUES:\n{json.dumps(existing_issues, ensure_ascii=False)}\n\n"
            f"OUTPUT SCHEMA:\n{json.dumps(schema)}\n"
            + language_instruction(context.get("language"))
        )
