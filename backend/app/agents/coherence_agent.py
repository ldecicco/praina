"""Coherence agent — cross-entity consistency checks for projects."""

from __future__ import annotations

import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.chat_action_extraction_agent import ChatActionExtractionAgent
from app.models.project import Project
from app.models.work import (
    Deliverable,
    Milestone,
    ProjectRisk,
    RiskStatus,
    Task,
    WorkPackage,
    deliverable_wps,
    milestone_wps,
)

logger = logging.getLogger(__name__)


@dataclass
class CoherenceIssue:
    category: str
    entity_ids: list[str] = field(default_factory=list)
    message: str = ""
    suggestion: str = ""
    severity: str = "warning"  # "warning" or "info"


@dataclass
class CoherenceReport:
    project_id: str
    issues: list[CoherenceIssue] = field(default_factory=list)
    checked_at: str = ""


class CoherenceAgent:
    """
    Cross-entity coherence checker.

    Rule-based checks: timeline gaps, milestone clustering, deliverable bunching,
    unbalanced WPs, risk coverage, reporting alignment.

    LLM-based checks (optional): description coherence, timeline narrative.
    """

    def __init__(self) -> None:
        self._llm = ChatActionExtractionAgent()

    def check_project(self, project_id: uuid.UUID, db: Session) -> CoherenceReport:
        report = CoherenceReport(
            project_id=str(project_id),
            checked_at=datetime.utcnow().isoformat(),
        )

        project = db.get(Project, project_id)
        if not project:
            report.issues.append(CoherenceIssue("error", [], "Project not found.", "", "warning"))
            return report

        wps = list(db.scalars(
            select(WorkPackage).where(WorkPackage.project_id == project_id, WorkPackage.is_trashed.is_(False))
        ).all())
        tasks = list(db.scalars(
            select(Task).where(Task.project_id == project_id, Task.is_trashed.is_(False))
        ).all())
        milestones = list(db.scalars(
            select(Milestone).where(Milestone.project_id == project_id, Milestone.is_trashed.is_(False))
        ).all())
        deliverables = list(db.scalars(
            select(Deliverable).where(Deliverable.project_id == project_id, Deliverable.is_trashed.is_(False))
        ).all())
        risks = list(db.scalars(
            select(ProjectRisk).where(ProjectRisk.project_id == project_id)
        ).all())

        report.issues.extend(self._check_timeline_gaps(project, wps))
        report.issues.extend(self._check_milestone_clustering(milestones))
        report.issues.extend(self._check_deliverable_bunching(deliverables))
        report.issues.extend(self._check_unbalanced_wps(wps, tasks))
        report.issues.extend(self._check_risk_coverage(risks, wps, tasks))
        report.issues.extend(self._check_reporting_alignment(project, deliverables))

        # LLM coherence check (best-effort)
        try:
            llm_issues = self._llm_coherence_check(project_id, db, project, wps, deliverables, milestones)
            report.issues.extend(llm_issues)
        except Exception as exc:
            logger.warning("LLM coherence check failed for project %s: %s", project_id, exc)

        return report

    # ------------------------------------------------------------------
    # Rule-based checks
    # ------------------------------------------------------------------

    def _check_timeline_gaps(self, project: Project, wps: list[WorkPackage]) -> list[CoherenceIssue]:
        if not wps or project.duration_months < 2:
            return []
        covered = set()
        for wp in wps:
            for m in range(wp.start_month, wp.end_month + 1):
                covered.add(m)
        gaps = []
        for m in range(1, project.duration_months + 1):
            if m not in covered:
                gaps.append(m)
        if not gaps:
            return []
        # Group consecutive gaps
        ranges = []
        start = gaps[0]
        end = gaps[0]
        for g in gaps[1:]:
            if g == end + 1:
                end = g
            else:
                ranges.append((start, end))
                start = g
                end = g
        ranges.append((start, end))

        issues: list[CoherenceIssue] = []
        for s, e in ranges:
            span = e - s + 1
            if span >= 3:
                issues.append(CoherenceIssue(
                    category="timeline_gap",
                    message=f"No work packages cover months M{s}-M{e} ({span} months uncovered).",
                    suggestion="Consider extending existing WPs or adding a new WP to fill the gap.",
                    severity="warning",
                ))
            else:
                issues.append(CoherenceIssue(
                    category="timeline_gap",
                    message=f"Months M{s}-M{e} not covered by any work package.",
                    severity="info",
                ))
        return issues

    def _check_milestone_clustering(self, milestones: list[Milestone]) -> list[CoherenceIssue]:
        if len(milestones) < 2:
            return []
        month_counts = Counter(ms.due_month for ms in milestones)
        issues: list[CoherenceIssue] = []
        for month, count in month_counts.items():
            if count >= 3:
                ids = [str(ms.id) for ms in milestones if ms.due_month == month]
                issues.append(CoherenceIssue(
                    category="milestone_clustering",
                    entity_ids=ids,
                    message=f"{count} milestones are due in month M{month}.",
                    suggestion="Spread milestones across different months to reduce review bottlenecks.",
                    severity="warning",
                ))
            elif count == 2:
                ids = [str(ms.id) for ms in milestones if ms.due_month == month]
                issues.append(CoherenceIssue(
                    category="milestone_clustering",
                    entity_ids=ids,
                    message=f"2 milestones share the same due month M{month}.",
                    severity="info",
                ))
        return issues

    def _check_deliverable_bunching(self, deliverables: list[Deliverable]) -> list[CoherenceIssue]:
        if len(deliverables) < 3:
            return []
        month_counts = Counter(d.due_month for d in deliverables)
        issues: list[CoherenceIssue] = []
        for month, count in month_counts.items():
            if count > 3:
                ids = [str(d.id) for d in deliverables if d.due_month == month]
                issues.append(CoherenceIssue(
                    category="deliverable_bunching",
                    entity_ids=ids,
                    message=f"{count} deliverables are due in month M{month}.",
                    suggestion="Consider staggering deliverable deadlines to reduce workload peaks.",
                    severity="warning",
                ))
        return issues

    def _check_unbalanced_wps(self, wps: list[WorkPackage], tasks: list[Task]) -> list[CoherenceIssue]:
        if len(wps) < 2:
            return []
        task_counts: dict[uuid.UUID, int] = {}
        for t in tasks:
            task_counts[t.wp_id] = task_counts.get(t.wp_id, 0) + 1
        counts = [task_counts.get(wp.id, 0) for wp in wps]
        if not counts:
            return []
        avg = sum(counts) / len(counts)
        if avg < 2:
            return []
        issues: list[CoherenceIssue] = []
        for wp in wps:
            count = task_counts.get(wp.id, 0)
            if count == 0 and avg >= 3:
                issues.append(CoherenceIssue(
                    category="unbalanced_wp",
                    entity_ids=[str(wp.id)],
                    message=f"Work package '{wp.code}' has no tasks (average is {avg:.0f} per WP).",
                    suggestion="Add tasks or reconsider whether this WP is needed.",
                    severity="warning",
                ))
        return issues

    def _check_risk_coverage(
        self, risks: list[ProjectRisk], wps: list[WorkPackage], tasks: list[Task]
    ) -> list[CoherenceIssue]:
        open_risks = [r for r in risks if r.status in (RiskStatus.open, RiskStatus.monitoring)]
        if not open_risks:
            return []
        wp_codes = {wp.code.lower() for wp in wps}
        task_codes = {t.code.lower() for t in tasks}
        all_codes = wp_codes | task_codes

        issues: list[CoherenceIssue] = []
        for risk in open_risks:
            risk_code_prefix = risk.code.lower().split("-")[0] if "-" in risk.code else ""
            has_link = False
            if risk_code_prefix:
                has_link = any(risk_code_prefix in code for code in all_codes)
            # Also check if risk title words overlap with any WP/task title
            if not has_link:
                risk_words = {w for w in risk.title.lower().split() if len(w) > 3}
                for wp in wps:
                    wp_words = {w for w in wp.title.lower().split() if len(w) > 3}
                    if risk_words & wp_words:
                        has_link = True
                        break
            if not has_link:
                issues.append(CoherenceIssue(
                    category="risk_coverage",
                    entity_ids=[str(risk.id)],
                    message=f"Open risk '{risk.code}: {risk.title}' appears unlinked to any WP or task.",
                    suggestion="Ensure there is a task or WP addressing this risk.",
                    severity="info",
                ))
        return issues

    def _check_reporting_alignment(
        self, project: Project, deliverables: list[Deliverable]
    ) -> list[CoherenceIssue]:
        reporting_dates = getattr(project, "reporting_dates", None) or []
        if not reporting_dates or not deliverables:
            return []
        # Convert reporting dates to months
        try:
            start = project.start_date
            reporting_months = set()
            for rd in reporting_dates:
                if hasattr(rd, "year"):
                    delta = (rd.year - start.year) * 12 + (rd.month - start.month) + 1
                    reporting_months.add(delta)
        except (AttributeError, TypeError):
            return []

        if not reporting_months:
            return []

        issues: list[CoherenceIssue] = []
        for d in deliverables:
            if d.due_month not in reporting_months:
                closest = min(reporting_months, key=lambda m: abs(m - d.due_month))
                if abs(closest - d.due_month) > 2:
                    issues.append(CoherenceIssue(
                        category="reporting_alignment",
                        entity_ids=[str(d.id)],
                        message=f"Deliverable '{d.code}' is due in M{d.due_month} but no reporting period is near.",
                        suggestion=f"Closest reporting period is M{closest}. Consider aligning.",
                        severity="info",
                    ))
        return issues

    # ------------------------------------------------------------------
    # LLM coherence check
    # ------------------------------------------------------------------

    def _llm_coherence_check(
        self,
        project_id: uuid.UUID,
        db: Session,
        project: Project,
        wps: list[WorkPackage],
        deliverables: list[Deliverable],
        milestones: list[Milestone],
    ) -> list[CoherenceIssue]:
        context = {
            "project_code": project.code,
            "project_title": project.title,
            "project_description": project.description or "",
            "duration_months": project.duration_months,
            "work_packages": [
                {"code": wp.code, "title": wp.title, "description": wp.description or "", "M_start": wp.start_month, "M_end": wp.end_month}
                for wp in wps
            ],
            "deliverables": [
                {"code": d.code, "title": d.title, "description": d.description or "", "M_due": d.due_month}
                for d in deliverables
            ],
            "milestones": [
                {"code": ms.code, "title": ms.title, "description": ms.description or "", "M_due": ms.due_month}
                for ms in milestones
            ],
        }

        from app.agents.language_utils import language_instruction

        prompt = (
            "You are a project coherence reviewer.\n"
            "Given the project structure below, identify coherence issues:\n"
            "- Do WP/deliverable/milestone descriptions contradict each other?\n"
            "- Does the milestone and deliverable ordering make logical sense?\n"
            "- Are there deliverables that seem unrelated to any WP description?\n\n"
            "Return a JSON object with an `issues` array. Each issue has:\n"
            "category (string), entity_ids (list of codes), message (string), suggestion (string), severity (warning|info).\n"
            "If no issues found, return {\"issues\": []}.\n"
            "Return JSON only.\n\n"
            f"PROJECT:\n{json.dumps(context, default=str, ensure_ascii=False)}\n"
            + language_instruction(project.language)
        )

        raw = self._llm._generate_with_ollama_chat(prompt, allow_compaction=True)
        if not raw:
            return []
        payload = self._llm._parse_json(raw)
        if not payload or not isinstance(payload.get("issues"), list):
            return []

        issues: list[CoherenceIssue] = []
        for item in payload["issues"]:
            if not isinstance(item, dict):
                continue
            message = str(item.get("message") or "").strip()
            if not message:
                continue
            severity = str(item.get("severity") or "info").lower()
            if severity not in ("warning", "info"):
                severity = "info"
            entity_ids = item.get("entity_ids") or []
            if not isinstance(entity_ids, list):
                entity_ids = [str(entity_ids)]
            else:
                entity_ids = [str(e) for e in entity_ids]
            issues.append(CoherenceIssue(
                category=str(item.get("category") or "llm_coherence"),
                entity_ids=entity_ids,
                message=message,
                suggestion=str(item.get("suggestion") or ""),
                severity=severity,
            ))
        return issues
