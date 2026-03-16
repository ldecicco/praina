from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_inbox import (
    ProjectInboxItem,
    ProjectInboxPriority,
    ProjectInboxSource,
    ProjectInboxStatus,
)
from app.services.onboarding_service import NotFoundError, ValidationError


class ProjectInboxService:
    def __init__(self, db: Session):
        self.db = db

    def list_items(
        self,
        project_id: uuid.UUID,
        *,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ProjectInboxItem], int]:
        self._get_project(project_id)
        stmt = select(ProjectInboxItem).where(ProjectInboxItem.project_id == project_id)
        if status_filter:
            stmt = stmt.where(ProjectInboxItem.status == status_filter)
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = list(
            self.db.scalars(
                stmt.order_by(ProjectInboxItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return items, total

    def create_item(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        details: str | None = None,
        priority: str = "normal",
        source_type: str = "manual",
        source_key: str | None = None,
        assignee_member_id: uuid.UUID | None = None,
    ) -> ProjectInboxItem:
        self._get_project(project_id)
        existing = self.db.scalar(
            select(ProjectInboxItem).where(
                ProjectInboxItem.project_id == project_id,
                ProjectInboxItem.source_type == self._source_type(source_type),
                ProjectInboxItem.source_key == source_key,
            )
        ) if source_key else None
        if existing:
            return existing
        item = ProjectInboxItem(
            project_id=project_id,
            title=title[:255].strip(),
            details=(details or "").strip() or None,
            priority=self._priority(priority),
            source_type=self._source_type(source_type),
            source_key=source_key,
            assignee_member_id=assignee_member_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_item(self, project_id: uuid.UUID, item_id: uuid.UUID, *, status: str | None = None) -> ProjectInboxItem:
        item = self.db.scalar(
            select(ProjectInboxItem).where(ProjectInboxItem.project_id == project_id, ProjectInboxItem.id == item_id)
        )
        if not item:
            raise NotFoundError("Inbox item not found.")
        if status is not None:
            item.status = self._status(status)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _status(self, value: str) -> ProjectInboxStatus:
        try:
            return ProjectInboxStatus(value)
        except ValueError as exc:
            raise ValidationError("Inbox status is invalid.") from exc

    def _priority(self, value: str) -> ProjectInboxPriority:
        try:
            return ProjectInboxPriority(value)
        except ValueError as exc:
            raise ValidationError("Inbox priority is invalid.") from exc

    def _source_type(self, value: str) -> ProjectInboxSource:
        try:
            return ProjectInboxSource(value)
        except ValueError as exc:
            raise ValidationError("Inbox source type is invalid.") from exc
