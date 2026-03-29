"""Paper claim audit agent — grounded audit of claim support."""

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
class PaperClaimAudit:
    claim_id: str
    audit_status: str
    audit_summary: str
    supporting_reference_ids: list[str] = field(default_factory=list)
    supporting_note_ids: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    audit_confidence: float | None = None
    audited_at: str = ""


class PaperClaimAuditAgent:
    def __init__(self) -> None:
        self.last_error: str | None = None

    def audit_collection_claims(self, project_id: uuid.UUID, collection_id: uuid.UUID, db: Session) -> list[PaperClaimAudit]:
        service = ResearchService(db)
        project = db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        collection = service.get_collection(project_id, collection_id)
        raw_claims = collection.paper_claims or []
        claims = [item for item in raw_claims if isinstance(item, dict) and str(item.get("text") or "").strip()]
        if not claims:
            return []

        references, _ = service.list_references(project_id, collection_id=collection_id, page=1, page_size=100)
        notes, _ = service.list_notes(project_id, collection_id=collection_id, page=1, page_size=100)

        prompt = self._build_prompt(project, collection, claims, references, notes, service)
        raw = self._generate_text(prompt)
        payload = parse_json_object(raw) if raw else None
        if not payload or not isinstance(payload.get("claim_audits"), list):
            if self.last_error:
                raise ValueError(self.last_error)
            raise ValueError("Agent returned invalid audit output.")

        valid_reference_ids = {str(item.id) for item in references}
        valid_note_ids = {str(item.id) for item in notes}
        audits: list[PaperClaimAudit] = []
        now = datetime.now(timezone.utc).isoformat()
        for item in payload["claim_audits"]:
            if not isinstance(item, dict):
                continue
            claim_id = str(item.get("claim_id") or "").strip()
            if not claim_id:
                continue
            audit_status = str(item.get("audit_status") or "").strip().lower()
            if audit_status not in {"supported", "partially_supported", "unsupported"}:
                audit_status = "unsupported"
            summary = str(item.get("audit_summary") or "").strip()
            supporting_reference_ids = [
                str(ref_id) for ref_id in (item.get("supporting_reference_ids") or []) if str(ref_id) in valid_reference_ids
            ]
            supporting_note_ids = [
                str(note_id) for note_id in (item.get("supporting_note_ids") or []) if str(note_id) in valid_note_ids
            ]
            missing_evidence = [
                str(entry).strip()[:255]
                for entry in (item.get("missing_evidence") or [])
                if str(entry).strip()
            ]
            confidence_raw = item.get("audit_confidence")
            try:
                confidence = max(0.0, min(1.0, float(confidence_raw))) if confidence_raw is not None else None
            except (TypeError, ValueError):
                confidence = None
            audits.append(
                PaperClaimAudit(
                    claim_id=claim_id,
                    audit_status=audit_status,
                    audit_summary=summary[:4000],
                    supporting_reference_ids=supporting_reference_ids,
                    supporting_note_ids=supporting_note_ids,
                    missing_evidence=missing_evidence[:8],
                    audit_confidence=confidence,
                    audited_at=now,
                )
            )
        return audits

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
            logger.warning("Paper claim audit failed: %s", exc)
            return ""

    def _build_prompt(
        self,
        project: Project,
        collection: ResearchCollection,
        claims: list[dict[str, Any]],
        references: list[Any],
        notes: list[Any],
        service: ResearchService,
    ) -> str:
        evidence_references = []
        for item in references[:100]:
            evidence_references.append({
                "id": str(item.id),
                "title": item.title,
                "authors": item.authors or [],
                "abstract": (item.abstract or "")[:1800],
                "ai_summary": (item.ai_summary or "")[:2500],
                "reading_status": item.reading_status.value if hasattr(item.reading_status, "value") else str(item.reading_status),
            })

        evidence_notes = []
        for item in notes[:100]:
            evidence_notes.append({
                "id": str(item.id),
                "title": item.title,
                "type": item.note_type.value if hasattr(item.note_type, "value") else str(item.note_type),
                "content": item.content[:1800],
                "linked_reference_ids": [str(ref_id) for ref_id in service.get_note_reference_ids(item.id)],
            })

        schema = {
            "claim_audits": [
                {
                    "claim_id": "string",
                    "audit_status": "supported|partially_supported|unsupported",
                    "audit_summary": "short explanation",
                    "supporting_reference_ids": ["reference ids from provided evidence only"],
                    "supporting_note_ids": ["note ids from provided evidence only"],
                    "missing_evidence": ["short missing evidence items"],
                    "audit_confidence": 0.0,
                }
            ]
        }

        return (
            "You audit research-paper claims against grounded collection evidence.\n"
            "For each claim, decide whether it is supported, partially supported, or unsupported.\n"
            "Use only the provided references and notes. Do not invent evidence.\n"
            "If a claim is not directly supported, identify the missing evidence briefly.\n"
            "Return JSON only.\n\n"
            f"PROJECT: {project.title}\n"
            f"COLLECTION: {collection.title}\n"
            f"WORKING HYPOTHESIS: {(collection.hypothesis or '').strip()}\n"
            f"PAPER QUESTIONS: {json.dumps(collection.paper_questions or [], ensure_ascii=False)}\n"
            f"CLAIMS: {json.dumps(claims, ensure_ascii=False)}\n"
            f"REFERENCES: {json.dumps(evidence_references, ensure_ascii=False)}\n"
            f"NOTES: {json.dumps(evidence_notes, ensure_ascii=False)}\n"
            f"OUTPUT SCHEMA: {json.dumps(schema)}\n"
            + language_instruction(getattr(project, "language", None))
        )
