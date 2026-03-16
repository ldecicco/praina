from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.todo import ProjectTodo, TodoPriority, TodoStatus
from app.services.onboarding_service import NotFoundError, ValidationError


class TodoService:
    def __init__(self, db: Session):
        self.db = db

    def list_items(
        self,
        project_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        assignee_member_id: uuid.UUID | None = None,
        wp_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ProjectTodo], int]:
        self._get_project(project_id)
        stmt = select(ProjectTodo).where(ProjectTodo.project_id == project_id)
        if status_filter:
            stmt = stmt.where(ProjectTodo.status == status_filter)
        if assignee_member_id:
            stmt = stmt.where(ProjectTodo.assignee_member_id == assignee_member_id)
        if wp_id:
            stmt = stmt.where(ProjectTodo.wp_id == wp_id)
        if task_id:
            stmt = stmt.where(ProjectTodo.task_id == task_id)
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ProjectTodo.sort_order, ProjectTodo.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return items, total

    def create_item(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        description: str | None = None,
        priority: str = "normal",
        creator_member_id: uuid.UUID | None = None,
        assignee_member_id: uuid.UUID | None = None,
        wp_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        due_date=None,
        sort_order: int = 0,
    ) -> ProjectTodo:
        self._get_project(project_id)
        item = ProjectTodo(
            project_id=project_id,
            title=title[:255].strip(),
            description=(description or "").strip() or None,
            priority=self._priority(priority),
            creator_member_id=creator_member_id,
            assignee_member_id=assignee_member_id,
            wp_id=wp_id,
            task_id=task_id,
            due_date=due_date,
            sort_order=sort_order,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_item(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assignee_member_id: str | None = None,
        wp_id: str | None = None,
        task_id: str | None = None,
        due_date=None,
        sort_order: int | None = None,
        _unset_due_date: bool = False,
    ) -> ProjectTodo:
        item = self.db.scalar(
            select(ProjectTodo).where(ProjectTodo.project_id == project_id, ProjectTodo.id == item_id)
        )
        if not item:
            raise NotFoundError("Todo not found.")
        if title is not None:
            item.title = title[:255].strip()
        if description is not None:
            item.description = description.strip() or None
        if status is not None:
            item.status = self._status(status)
        if priority is not None:
            item.priority = self._priority(priority)
        if assignee_member_id is not None:
            item.assignee_member_id = uuid.UUID(assignee_member_id) if assignee_member_id else None
        if wp_id is not None:
            item.wp_id = uuid.UUID(wp_id) if wp_id else None
        if task_id is not None:
            item.task_id = uuid.UUID(task_id) if task_id else None
        if due_date is not None or _unset_due_date:
            item.due_date = due_date
        if sort_order is not None:
            item.sort_order = sort_order
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_item(self, project_id: uuid.UUID, item_id: uuid.UUID) -> None:
        item = self.db.scalar(
            select(ProjectTodo).where(ProjectTodo.project_id == project_id, ProjectTodo.id == item_id)
        )
        if not item:
            raise NotFoundError("Todo not found.")
        self.db.delete(item)
        self.db.commit()

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _status(self, value: str) -> TodoStatus:
        try:
            return TodoStatus(value)
        except ValueError as exc:
            raise ValidationError("Todo status is invalid.") from exc

    def _priority(self, value: str) -> TodoPriority:
        try:
            return TodoPriority(value)
        except ValueError as exc:
            raise ValidationError("Todo priority is invalid.") from exc
