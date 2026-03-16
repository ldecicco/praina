from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.action_item import ActionItemStatus, MeetingActionItem
from app.models.organization import TeamMember
from app.models.project import Project
from app.models.project_inbox import ProjectInboxItem, ProjectInboxStatus
from app.models.todo import ProjectTodo, TodoStatus
from app.models.proposal import ProjectProposalSection
from app.models.work import Deliverable, Milestone, Task, WorkExecutionStatus, WorkPackage
from app.schemas.my_work import MyWorkItem, MyWorkProjectGroup, MyWorkResponse


def _month_to_date(start_date: date, month: int) -> str:
    """Convert a project-relative month number to a YYYY-MM-DD string."""
    total_months = (start_date.year * 12 + start_date.month - 1) + (month - 1)
    year = total_months // 12
    m = total_months % 12 + 1
    day = min(start_date.day, 28)  # safe for all months
    return date(year, m, day).isoformat()


class MyWorkService:
    def __init__(self, db: Session, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def get_my_work(self, include_closed: bool = False) -> MyWorkResponse:
        # 1. Find all active TeamMember rows for this user
        members = self.db.execute(
            select(TeamMember).where(
                TeamMember.user_account_id == self.user_id,
                TeamMember.is_active.is_(True),
            )
        ).scalars().all()

        if not members:
            return MyWorkResponse(groups=[], total_items=0)

        member_ids = {m.id for m in members}
        member_to_project: dict[uuid.UUID, uuid.UUID] = {m.id: m.project_id for m in members}
        project_ids = set(member_to_project.values())

        # 2. Load project metadata
        projects = self.db.execute(
            select(Project).where(Project.id.in_(project_ids))
        ).scalars().all()
        project_map: dict[uuid.UUID, Project] = {p.id: p for p in projects}

        items_by_project: dict[uuid.UUID, list[MyWorkItem]] = defaultdict(list)

        # 3a. Work entities — responsible person
        work_models: list[tuple[type, str]] = [
            (WorkPackage, "work_package"),
            (Task, "task"),
            (Milestone, "milestone"),
            (Deliverable, "deliverable"),
        ]
        for model, item_type in work_models:
            stmt = select(model).where(
                model.responsible_person_id.in_(member_ids),
                model.is_trashed.is_(False),
            )
            if not include_closed and hasattr(model, "execution_status"):
                stmt = stmt.where(model.execution_status != WorkExecutionStatus.closed)
            rows = self.db.execute(stmt).scalars().all()
            for row in rows:
                proj = project_map.get(row.project_id)
                if not proj:
                    continue
                due_month = getattr(row, "due_month", None) or getattr(row, "end_month", None)
                due_date = _month_to_date(proj.start_date, due_month) if due_month and proj.start_date else None
                raw_status = getattr(row, "execution_status", None) or getattr(row, "workflow_status", None) or ""
                status = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
                items_by_project[row.project_id].append(MyWorkItem(
                    item_type=item_type,
                    entity_id=str(row.id),
                    project_id=str(row.project_id),
                    project_code=proj.code,
                    project_title=proj.title,
                    code=getattr(row, "code", None),
                    title=row.title,
                    status=status,
                    role="responsible",
                    due_date=due_date,
                    due_month=due_month,
                ))

        # 3b. Review duties — deliverables
        review_deliverables = self.db.execute(
            select(Deliverable).where(
                Deliverable.review_owner_member_id.in_(member_ids),
                Deliverable.is_trashed.is_(False),
            )
        ).scalars().all()
        for row in review_deliverables:
            proj = project_map.get(row.project_id)
            if not proj:
                continue
            due_month = row.review_due_month or row.due_month
            due_date = _month_to_date(proj.start_date, due_month) if due_month and proj.start_date else None
            raw_status = row.workflow_status or ""
            status = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
            items_by_project[row.project_id].append(MyWorkItem(
                item_type="review_deliverable",
                entity_id=str(row.id),
                project_id=str(row.project_id),
                project_code=proj.code,
                project_title=proj.title,
                code=row.code,
                title=row.title,
                status=status,
                role="reviewer",
                due_date=due_date,
                due_month=due_month,
            ))

        # 3b cont. Review duties — proposal sections
        review_sections = self.db.execute(
            select(ProjectProposalSection).where(
                ProjectProposalSection.reviewer_member_id.in_(member_ids),
            )
        ).scalars().all()
        for row in review_sections:
            proj = project_map.get(row.project_id)
            if not proj:
                continue
            items_by_project[row.project_id].append(MyWorkItem(
                item_type="review_proposal_section",
                entity_id=str(row.id),
                project_id=str(row.project_id),
                project_code=proj.code,
                project_title=proj.title,
                code=row.key,
                title=row.title,
                status=row.status or "not_started",
                role="reviewer",
                due_date=row.due_date.isoformat() if row.due_date else None,
            ))

        # 3c. Action items
        action_items = self.db.execute(
            select(MeetingActionItem).where(
                MeetingActionItem.assignee_member_id.in_(member_ids),
                MeetingActionItem.status.notin_([ActionItemStatus.done, ActionItemStatus.dismissed]),
            )
        ).scalars().all()
        for row in action_items:
            proj = project_map.get(row.project_id)
            if not proj:
                continue
            items_by_project[row.project_id].append(MyWorkItem(
                item_type="action_item",
                entity_id=str(row.id),
                project_id=str(row.project_id),
                project_code=proj.code,
                project_title=proj.title,
                title=row.description,
                status=str(row.status.value) if row.status else "",
                role="assignee",
                priority=str(row.priority.value) if row.priority else None,
                due_date=row.due_date.isoformat() if row.due_date else None,
            ))

        # 3d. Project inbox items
        inbox_items = self.db.execute(
            select(ProjectInboxItem).where(
                ProjectInboxItem.assignee_member_id.in_(member_ids),
                ProjectInboxItem.status.notin_([ProjectInboxStatus.done, ProjectInboxStatus.dismissed]),
            )
        ).scalars().all()
        for row in inbox_items:
            proj = project_map.get(row.project_id)
            if not proj:
                continue
            items_by_project[row.project_id].append(MyWorkItem(
                item_type="inbox_item",
                entity_id=str(row.id),
                project_id=str(row.project_id),
                project_code=proj.code,
                project_title=proj.title,
                title=row.title,
                status=str(row.status.value) if row.status else "",
                role="assignee",
                priority=str(row.priority.value) if row.priority else None,
                due_date=row.due_date.isoformat() if row.due_date else None,
            ))

        # 3e. Project todos
        todo_items = self.db.execute(
            select(ProjectTodo).where(
                ProjectTodo.assignee_member_id.in_(member_ids),
                ProjectTodo.status.notin_([TodoStatus.done, TodoStatus.dismissed]),
            )
        ).scalars().all()
        for row in todo_items:
            proj = project_map.get(row.project_id)
            if not proj:
                continue
            items_by_project[row.project_id].append(MyWorkItem(
                item_type="todo",
                entity_id=str(row.id),
                project_id=str(row.project_id),
                project_code=proj.code,
                project_title=proj.title,
                title=row.title,
                status=str(row.status.value) if row.status else "",
                role="assignee",
                priority=str(row.priority.value) if row.priority else None,
                due_date=row.due_date.isoformat() if row.due_date else None,
            ))

        # 5. Build groups sorted by project code, items sorted by due_date (nulls last)
        groups: list[MyWorkProjectGroup] = []
        total = 0
        for pid in sorted(items_by_project.keys(), key=lambda p: project_map[p].code):
            proj = project_map[pid]
            items = sorted(
                items_by_project[pid],
                key=lambda i: (i.due_date or "9999-12-31"),
            )
            total += len(items)
            groups.append(MyWorkProjectGroup(
                project_id=str(pid),
                project_code=proj.code,
                project_title=proj.title,
                project_mode=proj.project_mode,
                items=items,
            ))

        return MyWorkResponse(groups=groups, total_items=total)
