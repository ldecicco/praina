"""Extended validation service — checks beyond OnboardingService.validate_project()."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.organization import PartnerOrganization, TeamMember
from app.models.project import Project
from app.models.work import (
    Deliverable,
    Milestone,
    Task,
    WorkPackage,
    deliverable_wps,
    milestone_wps,
)


@dataclass
class ValidationIssue:
    entity_type: str
    entity_id: str
    code: str
    field: str
    message: str
    severity: str  # "error" or "warning"


class AssignmentValidationService:
    """
    Extended structural validation that supplements OnboardingService.validate_project().

    OnboardingService already checks: assignment completeness, assignment consistency,
    timeline bounds, task-WP window, deliverable-WP link, duration overflow.

    This service adds: duplicate codes, empty project, orphaned tasks, unbalanced WPs,
    milestone-WP links, and other structural warnings.
    """

    def __init__(self, db: Session):
        self.db = db

    def validate(self, project_id: uuid.UUID) -> list[ValidationIssue]:
        project = self.db.get(Project, project_id)
        if not project:
            return [ValidationIssue("project", str(project_id), "NOT_FOUND", "", "Project not found.", "error")]

        issues: list[ValidationIssue] = []
        wps = self._active_wps(project_id)
        tasks = self._active_tasks(project_id)
        milestones = self._active_milestones(project_id)
        deliverables = self._active_deliverables(project_id)

        issues.extend(self._check_empty_project(project_id, wps))
        issues.extend(self._check_duplicate_codes(project_id, wps, tasks, milestones, deliverables))
        issues.extend(self._check_orphaned_tasks(project_id, tasks, wps))
        issues.extend(self._check_milestone_wp_links(project_id, milestones))
        issues.extend(self._check_unbalanced_wps(project_id, wps, tasks))
        issues.extend(self._check_no_partners(project_id))
        issues.extend(self._check_no_members(project_id))

        return issues

    def _active_wps(self, project_id: uuid.UUID) -> list[WorkPackage]:
        return list(self.db.scalars(
            select(WorkPackage).where(WorkPackage.project_id == project_id, WorkPackage.is_trashed.is_(False))
        ).all())

    def _active_tasks(self, project_id: uuid.UUID) -> list[Task]:
        return list(self.db.scalars(
            select(Task).where(Task.project_id == project_id, Task.is_trashed.is_(False))
        ).all())

    def _active_milestones(self, project_id: uuid.UUID) -> list[Milestone]:
        return list(self.db.scalars(
            select(Milestone).where(Milestone.project_id == project_id, Milestone.is_trashed.is_(False))
        ).all())

    def _active_deliverables(self, project_id: uuid.UUID) -> list[Deliverable]:
        return list(self.db.scalars(
            select(Deliverable).where(Deliverable.project_id == project_id, Deliverable.is_trashed.is_(False))
        ).all())

    def _check_empty_project(self, project_id: uuid.UUID, wps: list[WorkPackage]) -> list[ValidationIssue]:
        if not wps:
            return [ValidationIssue("project", str(project_id), "EMPTY_PROJECT", "", "Project has no work packages.", "error")]
        return []

    def _check_duplicate_codes(
        self,
        project_id: uuid.UUID,
        wps: list[WorkPackage],
        tasks: list[Task],
        milestones: list[Milestone],
        deliverables: list[Deliverable],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for entity_type, entities in [
            ("work_package", wps),
            ("task", tasks),
            ("milestone", milestones),
            ("deliverable", deliverables),
        ]:
            seen: dict[str, str] = {}
            for entity in entities:
                code_lower = entity.code.lower()
                if code_lower in seen:
                    issues.append(ValidationIssue(
                        entity_type, str(entity.id), "DUPLICATE_CODE", "code",
                        f"Duplicate code '{entity.code}' (also used by {seen[code_lower]}).",
                        "error",
                    ))
                else:
                    seen[code_lower] = str(entity.id)
        return issues

    def _check_orphaned_tasks(
        self, project_id: uuid.UUID, tasks: list[Task], wps: list[WorkPackage]
    ) -> list[ValidationIssue]:
        wp_ids = {wp.id for wp in wps}
        issues: list[ValidationIssue] = []
        for task in tasks:
            if task.wp_id not in wp_ids:
                issues.append(ValidationIssue(
                    "task", str(task.id), "ORPHANED_TASK", "wp_id",
                    f"Task '{task.code}' references a missing or trashed work package.",
                    "error",
                ))
        return issues

    def _check_milestone_wp_links(self, project_id: uuid.UUID, milestones: list[Milestone]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for ms in milestones:
            linked = self.db.execute(
                select(milestone_wps.c.wp_id).where(milestone_wps.c.milestone_id == ms.id)
            ).all()
            if not linked:
                issues.append(ValidationIssue(
                    "milestone", str(ms.id), "MILESTONE_MISSING_WP", "wp_ids",
                    f"Milestone '{ms.code}' is not linked to any work package.",
                    "warning",
                ))
        return issues

    def _check_unbalanced_wps(
        self, project_id: uuid.UUID, wps: list[WorkPackage], tasks: list[Task]
    ) -> list[ValidationIssue]:
        if len(wps) < 2:
            return []
        task_counts: dict[uuid.UUID, int] = {}
        for task in tasks:
            task_counts[task.wp_id] = task_counts.get(task.wp_id, 0) + 1

        issues: list[ValidationIssue] = []
        has_loaded = any(count >= 5 for count in task_counts.values())
        for wp in wps:
            count = task_counts.get(wp.id, 0)
            if count == 0 and has_loaded:
                issues.append(ValidationIssue(
                    "work_package", str(wp.id), "WP_NO_TASKS", "",
                    f"Work package '{wp.code}' has no tasks while other WPs have 5+.",
                    "warning",
                ))
        return issues

    def _check_no_partners(self, project_id: uuid.UUID) -> list[ValidationIssue]:
        count = self.db.scalar(
            select(func.count()).where(PartnerOrganization.project_id == project_id)
        ) or 0
        if count == 0:
            return [ValidationIssue("project", str(project_id), "NO_PARTNERS", "", "Project has no partner organizations.", "error")]
        return []

    def _check_no_members(self, project_id: uuid.UUID) -> list[ValidationIssue]:
        count = self.db.scalar(
            select(func.count()).where(TeamMember.project_id == project_id, TeamMember.is_active.is_(True))
        ) or 0
        if count == 0:
            return [ValidationIssue("project", str(project_id), "NO_MEMBERS", "", "Project has no active team members.", "error")]
        return []
