from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.organization import TeamMember
from app.models.project import Project
from app.models.proposal import ProjectProposalSection, ProposalCallBrief
from app.models.review import (
    ProposalReviewKind,
    ProposalReviewFinding,
    ProposalReviewScope,
    ReviewFindingSource,
    ReviewFindingStatus,
    ReviewFindingType,
)
from app.schemas.proposal import ProposalReviewFindingCreate, ProposalReviewFindingUpdate
from app.services.onboarding_service import NotFoundError, ValidationError

PROPOSAL_REVIEW_SYSTEM_PROMPT = """
You are a proposal review agent for collaborative proposal writing.

Return ONLY valid JSON with this shape:
{
  "findings": [
    {
      "finding_type": "issue|warning|strength",
      "scope": "anchor|section|proposal",
      "summary": "",
      "details": "",
      "proposal_section_key": "",
      "anchor_text": "",
      "anchor_prefix": "",
      "anchor_suffix": "",
      "start_offset": null,
      "end_offset": null
    }
  ]
}

Rules:
- Use `scope=anchor` only when the issue applies to a specific sentence or short passage.
- Use `scope=section` for broader section-level concerns.
- Use `scope=proposal` for cross-section or whole-proposal concerns.
- Keep findings concrete and actionable.
- Do not invent missing proposal facts.
- Prefer a small number of high-value findings over noisy coverage.
- For anchor findings, copy the exact anchor_text from the section text when possible.
- If offsets are uncertain, use null and rely on anchor_text/prefix/suffix.
""".strip()

CALL_COMPLIANCE_SYSTEM_PROMPT = """
You are a proposal call-compliance reviewer.

Return ONLY valid JSON with this shape:
{
  "findings": [
    {
      "finding_type": "issue|warning|strength",
      "scope": "anchor|section|proposal",
      "summary": "",
      "details": "",
      "proposal_section_key": "",
      "anchor_text": "",
      "anchor_prefix": "",
      "anchor_suffix": "",
      "start_offset": null,
      "end_offset": null
    }
  ]
}

Rules:
- Judge the proposal only against the provided call brief.
- Prefer concrete coverage gaps, partial coverage, and strong alignments that matter to evaluators.
- In `details`, mention the specific call element being assessed, such as eligibility, scoring, budget, or requirement text.
- Do not invent call constraints that are not present in the call brief.
- If the call brief lacks enough information, return a small number of warnings explaining what is missing.
- For anchor findings, use exact text copied from the proposal section when possible.
""".strip()


class ProposalReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model

    def list_findings(
        self,
        project_id: uuid.UUID,
        proposal_section_id: uuid.UUID | None,
        review_kind: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        self._get_project(project_id)
        normalized_kind = self._review_kind(review_kind or "general")
        stmt = (
            select(ProposalReviewFinding, TeamMember.full_name.label("member_name"))
            .outerjoin(TeamMember, ProposalReviewFinding.created_by_member_id == TeamMember.id)
            .where(ProposalReviewFinding.project_id == project_id)
            .where(ProposalReviewFinding.review_kind == normalized_kind)
            .where(ProposalReviewFinding.parent_finding_id.is_(None))
        )
        if proposal_section_id:
            stmt = stmt.where(
                (ProposalReviewFinding.proposal_section_id == proposal_section_id)
                | (ProposalReviewFinding.scope == ProposalReviewScope.proposal)
            )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(self.db.scalar(count_stmt) or 0)
        rows = self.db.execute(
            stmt.order_by(ProposalReviewFinding.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()

        parent_ids = [row[0].id for row in rows]
        replies_by_parent: dict[uuid.UUID, list[tuple]] = {}
        if parent_ids:
            reply_stmt = (
                select(ProposalReviewFinding, TeamMember.full_name.label("member_name"))
                .outerjoin(TeamMember, ProposalReviewFinding.created_by_member_id == TeamMember.id)
                .where(ProposalReviewFinding.parent_finding_id.in_(parent_ids))
                .order_by(ProposalReviewFinding.created_at.asc())
            )
            for reply_row in self.db.execute(reply_stmt).all():
                replies_by_parent.setdefault(reply_row[0].parent_finding_id, []).append(reply_row)

        items: list[dict] = []
        for row in rows:
            finding = row[0]
            member_name = row[1]
            child_rows = replies_by_parent.get(finding.id, [])
            items.append({
                "finding": finding,
                "member_name": member_name,
                "replies": [{"finding": r[0], "member_name": r[1]} for r in child_rows],
            })
        return items, total

    def create_finding(self, project_id: uuid.UUID, payload: ProposalReviewFindingCreate) -> ProposalReviewFinding:
        self._get_project(project_id)
        self._validate_member(project_id, payload.created_by_member_id)
        self._validate_section(project_id, payload.proposal_section_id)
        if payload.parent_finding_id:
            parent = self.db.scalar(
                select(ProposalReviewFinding).where(
                    ProposalReviewFinding.id == payload.parent_finding_id,
                    ProposalReviewFinding.project_id == project_id,
                )
            )
            if not parent:
                raise NotFoundError("Parent finding not found.")
        item = ProposalReviewFinding(
            project_id=project_id,
            proposal_section_id=payload.proposal_section_id,
            review_kind=self._review_kind(payload.review_kind),
            finding_type=self._finding_type(payload.finding_type),
            status=self._status(payload.status),
            source=self._source(payload.source),
            scope=self._scope(payload.scope),
            summary=payload.summary.strip(),
            details=(payload.details or "").strip() or None,
            anchor_text=(payload.anchor_text or "").strip() or None,
            anchor_prefix=(payload.anchor_prefix or "").strip() or None,
            anchor_suffix=(payload.anchor_suffix or "").strip() or None,
            start_offset=payload.start_offset,
            end_offset=payload.end_offset,
            created_by_member_id=payload.created_by_member_id,
            parent_finding_id=payload.parent_finding_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_finding(
        self,
        project_id: uuid.UUID,
        finding_id: uuid.UUID,
        payload: ProposalReviewFindingUpdate,
    ) -> ProposalReviewFinding:
        item = self.db.scalar(
            select(ProposalReviewFinding).where(
                ProposalReviewFinding.project_id == project_id,
                ProposalReviewFinding.id == finding_id,
            )
        )
        if not item:
            raise NotFoundError("Proposal review finding not found.")
        item.finding_type = self._finding_type(payload.finding_type)
        item.review_kind = self._review_kind(payload.review_kind)
        item.status = self._status(payload.status)
        item.source = self._source(payload.source)
        item.scope = self._scope(payload.scope)
        item.summary = payload.summary.strip()
        item.details = (payload.details or "").strip() or None
        item.anchor_text = (payload.anchor_text or "").strip() or None
        item.anchor_prefix = (payload.anchor_prefix or "").strip() or None
        item.anchor_suffix = (payload.anchor_suffix or "").strip() or None
        item.start_offset = payload.start_offset
        item.end_offset = payload.end_offset
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_finding(self, project_id: uuid.UUID, finding_id: uuid.UUID) -> None:
        item = self.db.scalar(
            select(ProposalReviewFinding).where(
                ProposalReviewFinding.project_id == project_id,
                ProposalReviewFinding.id == finding_id,
            )
        )
        if not item:
            raise NotFoundError("Proposal review finding not found.")
        self.db.delete(item)
        self.db.commit()

    def run_review(self, project_id: uuid.UUID, proposal_section_id: uuid.UUID | None) -> list[ProposalReviewFinding]:
        project = self._get_project(project_id)
        target_section = self._validate_section(project_id, proposal_section_id)
        sections = list(
            self.db.scalars(
                select(ProjectProposalSection)
                .where(ProjectProposalSection.project_id == project_id)
                .order_by(ProjectProposalSection.position.asc())
            ).all()
        )
        if not sections:
            raise NotFoundError("No proposal sections available.")

        payload = self._review_payload(project, sections, target_section)
        raw = self._chat_json(
            PROPOSAL_REVIEW_SYSTEM_PROMPT,
            "Review the proposal content and return structured findings.\n"
            f"Proposal payload:\n{json.dumps(payload, ensure_ascii=False)}",
        )
        findings = raw.get("findings", [])
        if not isinstance(findings, list):
            findings = []

        delete_stmt = delete(ProposalReviewFinding).where(
            ProposalReviewFinding.project_id == project_id,
            ProposalReviewFinding.source == ReviewFindingSource.assistant,
        )
        if target_section:
            delete_stmt = delete_stmt.where(
                (ProposalReviewFinding.proposal_section_id == target_section.id)
                | (ProposalReviewFinding.scope == ProposalReviewScope.proposal)
            )
        delete_stmt = delete_stmt.where(ProposalReviewFinding.review_kind == ProposalReviewKind.general)
        self.db.execute(delete_stmt)

        created: list[ProposalReviewFinding] = []
        for entry in findings:
            if not isinstance(entry, dict):
                continue
            section_key = str(entry.get("proposal_section_key") or "").strip()
            linked_section_id = None
            if section_key:
                linked_section = next((item for item in sections if item.key == section_key), None)
                linked_section_id = linked_section.id if linked_section else None
            elif target_section and str(entry.get("scope") or "").strip().lower() != "proposal":
                linked_section_id = target_section.id

            item = ProposalReviewFinding(
                project_id=project_id,
                proposal_section_id=linked_section_id,
                review_kind=ProposalReviewKind.general,
                finding_type=self._finding_type(str(entry.get("finding_type") or "warning")),
                status=ReviewFindingStatus.open,
                source=ReviewFindingSource.assistant,
                scope=self._scope(str(entry.get("scope") or "section")),
                summary=str(entry.get("summary") or "").strip()[:255],
                details=str(entry.get("details") or "").strip() or None,
                anchor_text=str(entry.get("anchor_text") or "").strip() or None,
                anchor_prefix=str(entry.get("anchor_prefix") or "").strip() or None,
                anchor_suffix=str(entry.get("anchor_suffix") or "").strip() or None,
                start_offset=entry.get("start_offset") if isinstance(entry.get("start_offset"), int) else None,
                end_offset=entry.get("end_offset") if isinstance(entry.get("end_offset"), int) else None,
            )
            if not item.summary:
                continue
            self.db.add(item)
            created.append(item)

        self.db.commit()
        for item in created:
            self.db.refresh(item)
        return created

    def run_call_compliance_review(
        self,
        project_id: uuid.UUID,
        proposal_section_id: uuid.UUID | None,
    ) -> list[ProposalReviewFinding]:
        project = self._get_project(project_id)
        target_section = self._validate_section(project_id, proposal_section_id)
        call_brief = self.db.scalar(select(ProposalCallBrief).where(ProposalCallBrief.project_id == project_id))
        if not call_brief or not self._call_brief_has_content(call_brief):
            raise ValidationError("Call brief is empty.")

        sections = list(
            self.db.scalars(
                select(ProjectProposalSection)
                .where(ProjectProposalSection.project_id == project_id)
                .order_by(ProjectProposalSection.position.asc())
            ).all()
        )
        if not sections:
            raise NotFoundError("No proposal sections available.")

        payload = self._call_compliance_payload(project, call_brief, sections, target_section)
        raw = self._chat_json(
            CALL_COMPLIANCE_SYSTEM_PROMPT,
            "Review proposal adherence to the target call and return structured findings.\n"
            f"Compliance payload:\n{json.dumps(payload, ensure_ascii=False)}",
        )
        findings = raw.get("findings", [])
        if not isinstance(findings, list):
            findings = []

        delete_stmt = delete(ProposalReviewFinding).where(
            ProposalReviewFinding.project_id == project_id,
            ProposalReviewFinding.source == ReviewFindingSource.assistant,
            ProposalReviewFinding.review_kind == ProposalReviewKind.call_compliance,
        )
        if target_section:
            delete_stmt = delete_stmt.where(
                (ProposalReviewFinding.proposal_section_id == target_section.id)
                | (ProposalReviewFinding.scope == ProposalReviewScope.proposal)
            )
        self.db.execute(delete_stmt)

        created: list[ProposalReviewFinding] = []
        for entry in findings:
            if not isinstance(entry, dict):
                continue
            section_key = str(entry.get("proposal_section_key") or "").strip()
            linked_section_id = None
            if section_key:
                linked_section = next((item for item in sections if item.key == section_key), None)
                linked_section_id = linked_section.id if linked_section else None
            elif target_section and str(entry.get("scope") or "").strip().lower() != "proposal":
                linked_section_id = target_section.id

            item = ProposalReviewFinding(
                project_id=project_id,
                proposal_section_id=linked_section_id,
                review_kind=ProposalReviewKind.call_compliance,
                finding_type=self._finding_type(str(entry.get("finding_type") or "warning")),
                status=ReviewFindingStatus.open,
                source=ReviewFindingSource.assistant,
                scope=self._scope(str(entry.get("scope") or "section")),
                summary=str(entry.get("summary") or "").strip()[:255],
                details=str(entry.get("details") or "").strip() or None,
                anchor_text=str(entry.get("anchor_text") or "").strip() or None,
                anchor_prefix=str(entry.get("anchor_prefix") or "").strip() or None,
                anchor_suffix=str(entry.get("anchor_suffix") or "").strip() or None,
                start_offset=entry.get("start_offset") if isinstance(entry.get("start_offset"), int) else None,
                end_offset=entry.get("end_offset") if isinstance(entry.get("end_offset"), int) else None,
            )
            if not item.summary:
                continue
            self.db.add(item)
            created.append(item)

        self.db.commit()
        for item in created:
            self.db.refresh(item)
        return created

    def _review_payload(
        self,
        project: Project,
        sections: list[ProjectProposalSection],
        target_section: ProjectProposalSection | None,
    ) -> dict[str, Any]:
        overview = [
            {
                "key": item.key,
                "title": item.title,
                "status": item.status,
                "required": item.required,
                "scope_hint": item.scope_hint,
                "content_excerpt": (item.content or "")[:500] or None,
            }
            for item in sections
        ]
        payload: dict[str, Any] = {
            "project": {
                "code": project.code,
                "title": project.title,
                "description": project.description,
                "language": project.language,
            },
            "proposal_sections_overview": overview,
        }
        if target_section:
            related = self._related_sections(sections, target_section)
            payload["mode"] = "section"
            payload["focus_section"] = {
                "key": target_section.key,
                "title": target_section.title,
                "guidance": target_section.guidance,
                "notes": target_section.notes,
                "content": target_section.content,
            }
            payload["related_sections"] = [
                {
                    "key": item.key,
                    "title": item.title,
                    "content": item.content,
                }
                for item in related
            ]
        else:
            payload["mode"] = "proposal"
            payload["sections"] = [
                {
                    "key": item.key,
                    "title": item.title,
                    "guidance": item.guidance,
                    "notes": item.notes,
                    "content": item.content,
                }
                for item in sections
                if item.content
            ]
        return payload

    def _related_sections(
        self, sections: list[ProjectProposalSection], target: ProjectProposalSection
    ) -> list[ProjectProposalSection]:
        target_tokens = self._tokens(
            " ".join(
                [
                    target.title,
                    target.key,
                    target.guidance or "",
                    target.notes or "",
                    target.content or "",
                ]
            )
        )
        ranked: list[tuple[int, ProjectProposalSection]] = []
        for item in sections:
            if item.id == target.id or not item.content:
                continue
            item_tokens = self._tokens(" ".join([item.title, item.key, item.content or "", item.notes or ""]))
            overlap = len(target_tokens.intersection(item_tokens))
            adjacency = 2 if abs(item.position - target.position) <= 1 else 0
            abstract_bonus = 3 if item.key.lower() in {"abstract", "summary"} else 0
            ranked.append((overlap + adjacency + abstract_bonus, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _score, item in ranked[:3]]

    def _call_compliance_payload(
        self,
        project: Project,
        call_brief: ProposalCallBrief,
        sections: list[ProjectProposalSection],
        target_section: ProjectProposalSection | None,
    ) -> dict[str, Any]:
        payload = self._review_payload(project, sections, target_section)
        payload["call_brief"] = {
            "call_title": call_brief.call_title,
            "funder_name": call_brief.funder_name,
            "programme_name": call_brief.programme_name,
            "reference_code": call_brief.reference_code,
            "submission_deadline": call_brief.submission_deadline.isoformat() if call_brief.submission_deadline else None,
            "source_url": call_brief.source_url,
            "summary": call_brief.summary,
            "eligibility_notes": call_brief.eligibility_notes,
            "budget_notes": call_brief.budget_notes,
            "scoring_notes": call_brief.scoring_notes,
            "requirements_text": call_brief.requirements_text,
        }
        return payload

    def _chat_json(self, system: str, user: str) -> dict[str, Any]:
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "chat_template_kwargs": {
                        "enable_thinking": settings.ollama_enable_thinking,
                    },
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        raw = data.get("message", {}).get("content", "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        return json.loads(raw or "{}")

    def _tokens(self, value: str) -> set[str]:
        return {
            token.strip().lower()
            for token in value.split()
            if len(token.strip()) >= 4
        }

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _validate_section(
        self, project_id: uuid.UUID, proposal_section_id: uuid.UUID | None
    ) -> ProjectProposalSection | None:
        if not proposal_section_id:
            return None
        section = self.db.scalar(
            select(ProjectProposalSection).where(
                ProjectProposalSection.project_id == project_id,
                ProjectProposalSection.id == proposal_section_id,
            )
        )
        if not section:
            raise NotFoundError("Proposal section not found.")
        return section

    def _validate_member(self, project_id: uuid.UUID, member_id: uuid.UUID | None) -> None:
        if not member_id:
            return
        member = self.db.scalar(
            select(TeamMember).where(TeamMember.project_id == project_id, TeamMember.id == member_id)
        )
        if not member:
            raise ValidationError("Selected member is not part of the project.")

    def _finding_type(self, value: str) -> ReviewFindingType:
        try:
            return ReviewFindingType(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Finding type must be `issue`, `warning`, `strength`, or `comment`.") from exc

    def _status(self, value: str) -> ReviewFindingStatus:
        try:
            return ReviewFindingStatus(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Finding status must be `open` or `resolved`.") from exc

    def _source(self, value: str) -> ReviewFindingSource:
        try:
            return ReviewFindingSource(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Finding source must be `manual` or `assistant`.") from exc

    def _review_kind(self, value: str) -> ProposalReviewKind:
        try:
            return ProposalReviewKind(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Review kind must be `general` or `call_compliance`.") from exc

    def _scope(self, value: str) -> ProposalReviewScope:
        try:
            return ProposalReviewScope(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Scope must be `anchor`, `section`, or `proposal`.") from exc

    def _call_brief_has_content(self, item: ProposalCallBrief) -> bool:
        return any(
            [
                item.call_title,
                item.funder_name,
                item.programme_name,
                item.reference_code,
                item.source_url,
                item.summary,
                item.eligibility_notes,
                item.budget_notes,
                item.scoring_notes,
                item.requirements_text,
            ]
        )
