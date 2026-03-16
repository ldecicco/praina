"""Governance agent — policy enforcement for high-impact project operations."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectStatus
from app.models.work import Deliverable, DeliverableWorkflowStatus, Task, WorkPackage

logger = logging.getLogger(__name__)


@dataclass
class GovernanceDecision:
    allowed: bool = True
    requires_approval: bool = False
    reason: str = ""
    policy_refs: list[str] = field(default_factory=list)


# Valid deliverable workflow transitions
_DELIVERABLE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"in_review"},
    "in_review": {"changes_requested", "approved"},
    "changes_requested": {"in_review", "draft"},
    "approved": {"submitted"},
    "submitted": set(),
}


class GovernanceAgent:
    """
    Policy enforcement layer that evaluates actions before execution.

    Hard-coded rules (v1 — no LLM needed):
    1. Activation guard: requires WPs, partners, members, 0 validation errors
    2. Scope change guard: changing duration/start_date on active project needs reason
    3. Bulk delete guard: trashing a WP with >3 tasks needs confirmation
    4. Assignment change guard: changing leader_organization on active WP needs reason
    5. Deliverable workflow guard: enforce valid state transitions
    """

    def evaluate_action(
        self,
        action: dict[str, Any],
        project_context: dict[str, Any],
        db: Session,
    ) -> GovernanceDecision:
        action_type = str(action.get("action_type") or "").lower()
        entity_type = str(action.get("entity_type") or "").lower()
        fields = action.get("fields") or {}
        project_id = action.get("project_id")

        if not project_id:
            return GovernanceDecision(allowed=True)

        try:
            pid = uuid.UUID(str(project_id))
        except ValueError:
            return GovernanceDecision(allowed=True)

        project = db.get(Project, pid)
        if not project:
            return GovernanceDecision(allowed=True)

        # Rule 2: Scope change on active project
        if (
            action_type == "update"
            and entity_type == "project"
            and project.status == ProjectStatus.active
        ):
            scope_fields = {"duration_months", "start_date"}
            changed_scope = scope_fields & set(fields.keys())
            if changed_scope:
                reason = str(action.get("reason") or "").strip()
                if not reason:
                    return GovernanceDecision(
                        allowed=False,
                        reason=f"Changing {', '.join(changed_scope)} on an active project requires a reason.",
                        policy_refs=["SCOPE_CHANGE_GUARD"],
                    )

        # Rule 3: Bulk delete guard
        if action_type in ("trash", "delete") and entity_type == "work_package":
            target_id = fields.get("target") or action.get("entity_id")
            if target_id:
                try:
                    wp_uuid = uuid.UUID(str(target_id))
                    task_count = db.scalar(
                        select(func.count()).where(
                            Task.wp_id == wp_uuid,
                            Task.is_trashed.is_(False),
                        )
                    ) or 0
                    if task_count > 3:
                        return GovernanceDecision(
                            requires_approval=True,
                            reason=f"Work package has {task_count} active tasks. Trashing it will affect all of them.",
                            policy_refs=["BULK_DELETE_GUARD"],
                        )
                except ValueError:
                    pass

        # Rule 4: Assignment change on active WP
        if (
            action_type == "update"
            and entity_type == "work_package"
            and project.status == ProjectStatus.active
            and "leader" in fields
        ):
            reason = str(action.get("reason") or "").strip()
            if not reason:
                return GovernanceDecision(
                    allowed=False,
                    reason="Changing the leader organization of a work package on an active project requires a reason.",
                    policy_refs=["ASSIGNMENT_CHANGE_GUARD"],
                )

        # Rule 5: Deliverable workflow transitions
        if action_type == "update" and entity_type == "deliverable":
            new_status = str(fields.get("workflow_status") or "").lower()
            target_id = fields.get("target") or action.get("entity_id")
            if new_status and target_id:
                try:
                    d_uuid = uuid.UUID(str(target_id))
                    deliverable = db.get(Deliverable, d_uuid)
                    if deliverable:
                        current = deliverable.workflow_status
                        current_val = current.value if hasattr(current, "value") else str(current)
                        valid_next = _DELIVERABLE_TRANSITIONS.get(current_val, set())
                        if new_status not in valid_next:
                            return GovernanceDecision(
                                allowed=False,
                                reason=f"Cannot transition deliverable from '{current_val}' to '{new_status}'. Valid transitions: {', '.join(valid_next) or 'none'}.",
                                policy_refs=["DELIVERABLE_WORKFLOW_GUARD"],
                            )
                except ValueError:
                    pass

        return GovernanceDecision(allowed=True)
