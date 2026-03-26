"""Dashboard health orchestration service."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.action_item import ActionItemStatus, MeetingActionItem
from app.models.health_issue_state import ProjectHealthIssueState
from app.models.health_snapshot import ProjectHealthSnapshot
from app.models.organization import TeamMember
from app.models.project import Project
from app.models.project_inbox import ProjectInboxItem
from app.models.work import (
    Deliverable,
    Milestone,
    ProjectRisk,
    Task,
    WorkExecutionStatus,
    WorkPackage,
    deliverable_wps,
    milestone_wps,
)
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.project_inbox_service import ProjectInboxService

logger = logging.getLogger(__name__)


class DashboardHealthService:
    def __init__(self, db: Session):
        self.db = db

    def run_health(
        self,
        project_id: uuid.UUID,
        *,
        scope_type: str = "project",
        scope_ref_id: uuid.UUID | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")

        validation_errors: list[dict[str, Any]] = []
        validation_warnings: list[dict[str, Any]] = []
        coherence_issues: list[dict[str, Any]] = []

        try:
            from app.agents.validation_agent import ValidationAgent

            report = ValidationAgent().run(project_id, self.db, include_llm=False)
            validation_errors = [
                self._issue_dict(
                    source="validation",
                    severity=getattr(item, "severity", "error") or "error",
                    category=getattr(item, "code", "") or "VALIDATION_ERROR",
                    entity_type=getattr(item, "entity_type", None),
                    entity_id=getattr(item, "entity_id", None),
                    message=getattr(item, "message", "") or "",
                    suggestion=None,
                )
                for item in report.errors
            ]
            validation_warnings = [
                self._issue_dict(
                    source="validation",
                    severity=getattr(item, "severity", "warning") or "warning",
                    category=getattr(item, "code", "") or "VALIDATION_WARNING",
                    entity_type=getattr(item, "entity_type", None),
                    entity_id=getattr(item, "entity_id", None),
                    message=getattr(item, "message", "") or "",
                    suggestion=None,
                )
                for item in report.warnings
            ]
        except Exception:
            logger.warning("Validation agent failed in dashboard health", exc_info=True)
            validation_errors = []
            validation_warnings = []

        try:
            from app.agents.coherence_agent import CoherenceAgent

            report = CoherenceAgent().check_project(project_id, self.db)
            coherence_issues = [
                self._issue_dict(
                    source="coherence",
                    severity=getattr(item, "severity", "warning") or "warning",
                    category=getattr(item, "category", "") or "coherence_issue",
                    entity_type=self._infer_entity_type_from_ids(getattr(item, "entity_ids", []) or []),
                    entity_id=",".join(getattr(item, "entity_ids", []) or []) or None,
                    message=getattr(item, "message", "") or "",
                    suggestion=getattr(item, "suggestion", None),
                )
                for item in report.issues
            ]
        except Exception:
            logger.warning("Coherence agent failed in dashboard health", exc_info=True)
            coherence_issues = []

        issue_states = self._state_map(project_id)

        all_issues = validation_errors + validation_warnings + coherence_issues
        for issue in all_issues:
            state = issue_states.get(issue["issue_key"])
            issue["status"] = state.status if state else "open"
            issue["snoozed_until"] = state.snoozed_until.isoformat() if state and state.snoozed_until else None
            issue["rationale"] = state.rationale if state else None
            issue["primary_action"] = self._primary_action(issue)
            self._touch_issue_state(project_id, issue, state)

        visible_validation_errors = self._visible_issues(validation_errors, scope_type, scope_ref_id)
        visible_validation_warnings = self._visible_issues(validation_warnings, scope_type, scope_ref_id)
        visible_coherence_issues = self._visible_issues(coherence_issues, scope_type, scope_ref_id)

        result = {
            "scope_type": scope_type,
            "scope_ref_id": str(scope_ref_id) if scope_ref_id else None,
            "validation_errors": len(visible_validation_errors),
            "validation_warnings": len(visible_validation_warnings),
            "coherence_issues": len(visible_coherence_issues),
            "validation_error_details": visible_validation_errors,
            "validation_warning_details": visible_validation_warnings,
            "coherence_issue_details": visible_coherence_issues,
            "action_items_pending": self._action_items_pending(project_id, scope_type, scope_ref_id),
            "risks_open": self._risks_open(project_id, scope_type, scope_ref_id),
            "overdue_deliverables": self._overdue_deliverables(project, scope_type, scope_ref_id),
        }
        result["health_score"] = self._health_score(result)

        if persist:
            self._persist_snapshot(project_id, result)

        return result

    def list_history(self, project_id: uuid.UUID, limit: int = 12) -> list[ProjectHealthSnapshot]:
        return list(
            self.db.scalars(
                select(ProjectHealthSnapshot)
                .where(ProjectHealthSnapshot.project_id == project_id)
                .order_by(ProjectHealthSnapshot.created_at.desc())
                .limit(limit)
            ).all()
        )

    def latest_saved_health(
        self,
        project_id: uuid.UUID,
        *,
        scope_type: str = "project",
        scope_ref_id: uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        snapshots = self.list_history(project_id, limit=50)
        target_scope_ref_id = str(scope_ref_id) if scope_ref_id else None
        matched: ProjectHealthSnapshot | None = None
        for snapshot in snapshots:
            details = snapshot.details_json or {}
            if str(details.get("scope_type") or "project") != scope_type:
                continue
            if str(details.get("scope_ref_id") or "") != str(target_scope_ref_id or ""):
                continue
            matched = snapshot
            break
        if not matched:
            return None

        details = matched.details_json or {}
        issue_states = self._state_map(project_id)
        validation_errors = self._restore_snapshot_issues(
            project_id, details.get("validation_error_details", []), issue_states
        )
        validation_warnings = self._restore_snapshot_issues(
            project_id, details.get("validation_warning_details", []), issue_states
        )
        coherence_issues = self._restore_snapshot_issues(
            project_id, details.get("coherence_issue_details", []), issue_states
        )
        visible_validation_errors = self._visible_issues(validation_errors, scope_type, scope_ref_id)
        visible_validation_warnings = self._visible_issues(validation_warnings, scope_type, scope_ref_id)
        visible_coherence_issues = self._visible_issues(coherence_issues, scope_type, scope_ref_id)
        return {
            "scope_type": scope_type,
            "scope_ref_id": target_scope_ref_id,
            "validation_errors": len(visible_validation_errors),
            "validation_warnings": len(visible_validation_warnings),
            "coherence_issues": len(visible_coherence_issues),
            "validation_error_details": visible_validation_errors,
            "validation_warning_details": visible_validation_warnings,
            "coherence_issue_details": visible_coherence_issues,
            "action_items_pending": matched.action_items_pending,
            "risks_open": matched.risks_open,
            "overdue_deliverables": matched.overdue_deliverables,
            "health_score": matched.health_score,
        }

    def recurring_analytics(self, project_id: uuid.UUID, limit: int = 6) -> list[dict[str, Any]]:
        snapshots = self.list_history(project_id, limit=20)
        counter: Counter[tuple[str, str]] = Counter()
        latest_message: dict[tuple[str, str], str] = {}
        for snapshot in snapshots:
            details = snapshot.details_json or {}
            all_issue_rows = (
                details.get("validation_error_details", [])
                + details.get("validation_warning_details", [])
                + details.get("coherence_issue_details", [])
            )
            seen_in_snapshot: set[tuple[str, str]] = set()
            for issue in all_issue_rows:
                if not isinstance(issue, dict):
                    continue
                issue_key = str(issue.get("issue_key") or "")
                category = str(issue.get("category") or "issue")
                key = (issue_key or category, category)
                if key in seen_in_snapshot:
                    continue
                seen_in_snapshot.add(key)
                counter[key] += 1
                latest_message[key] = str(issue.get("message") or "")
        rows = [
            {"issue_key": key[0], "category": key[1], "count": count, "message": latest_message.get(key, "")}
            for key, count in counter.most_common(limit)
        ]
        return rows

    def scope_options(self, project_id: uuid.UUID) -> dict[str, list[dict[str, str]]]:
        return {
            "work_packages": [
                {"id": str(item.id), "label": f"{item.code} {item.title}".strip()}
                for item in self.db.scalars(
                    select(WorkPackage)
                    .where(WorkPackage.project_id == project_id, WorkPackage.is_trashed.is_(False))
                    .order_by(WorkPackage.code.asc())
                ).all()
            ],
            "tasks": [
                {"id": str(item.id), "label": f"{item.code} {item.title}".strip()}
                for item in self.db.scalars(
                    select(Task)
                    .where(Task.project_id == project_id, Task.is_trashed.is_(False))
                    .order_by(Task.code.asc())
                ).all()
            ],
            "deliverables": [
                {"id": str(item.id), "label": f"{item.code} {item.title}".strip()}
                for item in self.db.scalars(
                    select(Deliverable)
                    .where(Deliverable.project_id == project_id, Deliverable.is_trashed.is_(False))
                    .order_by(Deliverable.code.asc())
                ).all()
            ],
            "milestones": [
                {"id": str(item.id), "label": f"{item.code} {item.title}".strip()}
                for item in self.db.scalars(
                    select(Milestone)
                    .where(Milestone.project_id == project_id, Milestone.is_trashed.is_(False))
                    .order_by(Milestone.code.asc())
                ).all()
            ],
        }

    def set_issue_state(
        self,
        project_id: uuid.UUID,
        *,
        issue_key: str,
        source: str,
        category: str,
        entity_type: str | None,
        entity_id: str | None,
        status: str,
        rationale: str | None = None,
        snoozed_until: datetime | None = None,
    ) -> ProjectHealthIssueState:
        normalized_status = (status or "open").strip().lower()
        if normalized_status not in {"open", "dismissed", "accepted", "snoozed", "inboxed"}:
            raise ValidationError("Issue status must be open, dismissed, accepted, snoozed, or inboxed.")
        state = self.db.scalar(
            select(ProjectHealthIssueState).where(
                ProjectHealthIssueState.project_id == project_id,
                ProjectHealthIssueState.issue_key == issue_key,
            )
        )
        if not state:
            state = ProjectHealthIssueState(
                project_id=project_id,
                issue_key=issue_key,
                source=source,
                category=category,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            self.db.add(state)
        state.status = normalized_status
        state.rationale = (rationale or "").strip() or None
        state.snoozed_until = snoozed_until if normalized_status == "snoozed" else None
        state.last_seen_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(state)
        return state

    def create_inbox_item_from_issue(self, project_id: uuid.UUID, issue: dict[str, Any]) -> ProjectInboxItem:
        return ProjectInboxService(self.db).create_item(
            project_id,
            title=self._task_title(issue),
            details=self._task_description(issue),
            priority="high" if str(issue.get("severity") or "").lower() == "error" else "normal",
            source_type="health_issue",
            source_key=str(issue.get("issue_key") or ""),
        )

    def auto_refresh(self, project_id: uuid.UUID) -> None:
        try:
            self.run_health(project_id, persist=True)
        except Exception:
            self.db.rollback()

    def _issue_dict(
        self,
        *,
        source: str,
        severity: str,
        category: str,
        entity_type: str | None,
        entity_id: str | None,
        message: str,
        suggestion: str | None,
    ) -> dict[str, Any]:
        issue_key = self._issue_key(source, category, entity_type, entity_id, message)
        return {
            "issue_key": issue_key,
            "source": source,
            "severity": severity,
            "category": category,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "message": message,
            "suggestion": suggestion,
        }

    def _issue_key(self, source: str, category: str, entity_type: str | None, entity_id: str | None, message: str) -> str:
        token = "|".join([source or "", category or "", entity_type or "", entity_id or "", message or ""])
        return hashlib.sha1(token.encode("utf-8")).hexdigest()[:24]

    def _infer_entity_type_from_ids(self, entity_ids: list[str]) -> str | None:
        if not entity_ids:
            return None
        first = str(entity_ids[0])
        if not self._is_uuid(first):
            return None
        entity_id = uuid.UUID(first)
        if self.db.get(WorkPackage, entity_id):
            return "work_package"
        if self.db.get(Task, entity_id):
            return "task"
        if self.db.get(Deliverable, entity_id):
            return "deliverable"
        if self.db.get(Milestone, entity_id):
            return "milestone"
        if self.db.get(ProjectRisk, entity_id):
            return "risk"
        return None

    def _state_map(self, project_id: uuid.UUID) -> dict[str, ProjectHealthIssueState]:
        rows = self.db.scalars(select(ProjectHealthIssueState).where(ProjectHealthIssueState.project_id == project_id)).all()
        return {row.issue_key: row for row in rows}

    def _restore_snapshot_issues(
        self,
        project_id: uuid.UUID,
        items: list[dict[str, Any]],
        issue_states: dict[str, ProjectHealthIssueState],
    ) -> list[dict[str, Any]]:
        restored: list[dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            issue = dict(raw)
            issue_key = str(issue.get("issue_key") or self._issue_key(
                str(issue.get("source") or ""),
                str(issue.get("category") or ""),
                issue.get("entity_type"),
                issue.get("entity_id"),
                str(issue.get("message") or ""),
            ))
            issue["issue_key"] = issue_key
            state = issue_states.get(issue_key)
            issue["status"] = state.status if state else str(issue.get("status") or "open")
            issue["snoozed_until"] = state.snoozed_until.isoformat() if state and state.snoozed_until else issue.get("snoozed_until")
            issue["rationale"] = state.rationale if state else issue.get("rationale")
            issue["primary_action"] = self._primary_action(issue)
            restored.append(issue)
        return restored

    def _touch_issue_state(self, project_id: uuid.UUID, issue: dict[str, Any], state: ProjectHealthIssueState | None) -> None:
        if state:
            state.last_seen_at = datetime.now(timezone.utc)
            return
        state = ProjectHealthIssueState(
            project_id=project_id,
            issue_key=issue["issue_key"],
            source=issue["source"],
            category=issue["category"],
            entity_type=issue.get("entity_type"),
            entity_id=issue.get("entity_id"),
            status="open",
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(state)
        self.db.flush()

    def _visible_issues(
        self,
        items: list[dict[str, Any]],
        scope_type: str,
        scope_ref_id: uuid.UUID | None,
    ) -> list[dict[str, Any]]:
        visible: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for item in items:
            status = (item.get("status") or "open").lower()
            if status in {"dismissed", "accepted", "inboxed"}:
                continue
            snoozed_until = item.get("snoozed_until")
            if status == "snoozed" and snoozed_until:
                try:
                    if datetime.fromisoformat(str(snoozed_until)) > now:
                        continue
                except ValueError:
                    pass
            if self._matches_scope(item, scope_type, scope_ref_id):
                visible.append(item)
        return visible

    def _matches_scope(self, item: dict[str, Any], scope_type: str, scope_ref_id: uuid.UUID | None) -> bool:
        if scope_type == "project" or not scope_ref_id:
            return True
        entity_type = str(item.get("entity_type") or "").lower()
        entity_id = str(item.get("entity_id") or "")
        if entity_type == scope_type and (entity_id == str(scope_ref_id) or str(scope_ref_id) in entity_id.split(",")):
            return True
        if scope_type == "work_package" and entity_type == "task":
            task = self.db.get(Task, uuid.UUID(entity_id)) if self._is_uuid(entity_id) else None
            return bool(task and task.wp_id == scope_ref_id)
        if scope_type == "work_package" and entity_type == "deliverable":
            linked = self.db.execute(
                select(deliverable_wps.c.wp_id).where(deliverable_wps.c.deliverable_id == uuid.UUID(entity_id))
            ).all() if self._is_uuid(entity_id) else []
            return any(row[0] == scope_ref_id for row in linked)
        if scope_type == "work_package" and entity_type == "milestone":
            linked = self.db.execute(
                select(milestone_wps.c.wp_id).where(milestone_wps.c.milestone_id == uuid.UUID(entity_id))
            ).all() if self._is_uuid(entity_id) else []
            return any(row[0] == scope_ref_id for row in linked)
        if scope_type == "task" and entity_type == "task":
            return entity_id == str(scope_ref_id)
        if scope_type == "deliverable" and entity_type == "deliverable":
            return entity_id == str(scope_ref_id)
        if scope_type == "milestone" and entity_type == "milestone":
            return entity_id == str(scope_ref_id)
        return False

    def _action_items_pending(self, project_id: uuid.UUID, scope_type: str, scope_ref_id: uuid.UUID | None) -> int:
        if scope_type != "project":
            return 0
        return int(
            self.db.scalar(
                select(func.count()).select_from(MeetingActionItem).where(
                    MeetingActionItem.project_id == project_id,
                    MeetingActionItem.status == ActionItemStatus.pending,
                )
            )
            or 0
        )

    def _risks_open(self, project_id: uuid.UUID, scope_type: str, scope_ref_id: uuid.UUID | None) -> int:
        if scope_type != "project":
            return 0
        return int(
            self.db.scalar(
                select(func.count()).select_from(ProjectRisk).where(
                    ProjectRisk.project_id == project_id,
                    ProjectRisk.status != "closed",
                )
            )
            or 0
        )

    def _overdue_deliverables(self, project: Project, scope_type: str, scope_ref_id: uuid.UUID | None) -> int:
        if not project.start_date:
            return 0
        months_elapsed = (date.today().year - project.start_date.year) * 12 + (date.today().month - project.start_date.month) + 1
        stmt = select(func.count()).select_from(Deliverable).where(
            Deliverable.project_id == project.id,
            Deliverable.is_trashed.is_(False),
            Deliverable.due_month.isnot(None),
            Deliverable.due_month < months_elapsed,
            Deliverable.workflow_status.in_(["draft", "in_review", "changes_requested"]),
        )
        if scope_type == "deliverable" and scope_ref_id:
            stmt = stmt.where(Deliverable.id == scope_ref_id)
        elif scope_type != "project":
            return 0
        return int(self.db.scalar(stmt) or 0)

    def _health_score(self, payload: dict[str, Any]) -> str:
        if payload["validation_errors"] > 0 or payload["overdue_deliverables"] > 2:
            return "red"
        if payload["validation_warnings"] > 2 or payload["coherence_issues"] > 3 or payload["overdue_deliverables"] > 0:
            return "yellow"
        return "green"

    def _persist_snapshot(self, project_id: uuid.UUID, payload: dict[str, Any]) -> None:
        snapshot = ProjectHealthSnapshot(
            project_id=project_id,
            health_score=payload["health_score"],
            validation_errors=payload["validation_errors"],
            validation_warnings=payload["validation_warnings"],
            coherence_issues=payload["coherence_issues"],
            action_items_pending=payload["action_items_pending"],
            risks_open=payload["risks_open"],
            overdue_deliverables=payload["overdue_deliverables"],
            details_json={
                "scope_type": payload["scope_type"],
                "scope_ref_id": payload["scope_ref_id"],
                "validation_error_details": payload["validation_error_details"],
                "validation_warning_details": payload["validation_warning_details"],
                "coherence_issue_details": payload["coherence_issue_details"],
            },
        )
        self.db.add(snapshot)
        self.db.commit()

    def _primary_action(self, issue: dict[str, Any]) -> dict[str, Any]:
        entity_type = str(issue.get("entity_type") or "").lower()
        category = str(issue.get("category") or "").lower()
        if entity_type in {"deliverable", "milestone"} or category in {"deliverable_bunching", "reporting_alignment", "milestone_clustering"}:
            return {"type": "navigate", "label": "Open Delivery", "view": "delivery"}
        if entity_type in {"partner", "member"}:
            return {"type": "navigate", "label": "Open Matrix", "view": "matrix"}
        if category.startswith("document"):
            return {"type": "navigate", "label": "Open Documents", "view": "documents"}
        return {"type": "send_to_inbox", "label": "Send to Inbox"}

    def _task_title(self, issue: dict[str, Any]) -> str:
        message = " ".join(str(issue.get("message") or "").split())
        return (message[:255] or "Health follow-up").strip()

    def _task_description(self, issue: dict[str, Any]) -> str:
        suggestion = str(issue.get("suggestion") or "").strip()
        lines = [str(issue.get("message") or "").strip()]
        if suggestion:
            lines.append("")
            lines.append(f"Suggested action: {suggestion}")
        return "\n".join(lines).strip()

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
        except ValueError:
            return False
        return True
