"""Notification service — create, list, and manage notifications."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.auth import ProjectMembership
from app.models.notification import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def notify(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        *,
        title: str,
        body: str = "",
        link_type: str | None = None,
        link_id: uuid.UUID | None = None,
        channel: str = NotificationChannel.in_app.value,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            project_id=project_id,
            title=title,
            body=body,
            link_type=link_type,
            link_id=link_id,
            channel=channel,
            status=NotificationStatus.unread.value,
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def notify_project_members(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        body: str = "",
        link_type: str | None = None,
        link_id: uuid.UUID | None = None,
        exclude_user_id: uuid.UUID | None = None,
    ) -> list[Notification]:
        member_user_ids = list(
            self.db.scalars(
                select(ProjectMembership.user_id).where(
                    ProjectMembership.project_id == project_id,
                )
            ).all()
        )
        notifications: list[Notification] = []
        for uid in member_user_ids:
            if exclude_user_id and uid == exclude_user_id:
                continue
            n = Notification(
                user_id=uid,
                project_id=project_id,
                title=title,
                body=body,
                link_type=link_type,
                link_id=link_id,
                channel=NotificationChannel.in_app.value,
                status=NotificationStatus.unread.value,
            )
            self.db.add(n)
            notifications.append(n)
        self.db.commit()
        for n in notifications:
            self.db.refresh(n)
        return notifications

    def list_notifications(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        count_stmt = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        if project_id:
            stmt = stmt.where(Notification.project_id == project_id)
            count_stmt = count_stmt.where(Notification.project_id == project_id)
        if unread_only:
            stmt = stmt.where(Notification.status == NotificationStatus.unread.value)
            count_stmt = count_stmt.where(Notification.status == NotificationStatus.unread.value)
        total = self.db.scalar(count_stmt) or 0
        stmt = stmt.order_by(Notification.created_at.desc())
        rows = list(self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all())
        return rows, total

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        result = self.db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(status=NotificationStatus.read.value)
        )
        self.db.commit()
        return (result.rowcount or 0) > 0

    def mark_all_read(self, user_id: uuid.UUID, project_id: uuid.UUID | None = None) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.status == NotificationStatus.unread.value,
            )
            .values(status=NotificationStatus.read.value)
        )
        if project_id:
            stmt = stmt.where(Notification.project_id == project_id)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount or 0

    def unread_count(self, user_id: uuid.UUID, project_id: uuid.UUID | None = None) -> int:
        stmt = select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.status == NotificationStatus.unread.value,
        )
        if project_id:
            stmt = stmt.where(Notification.project_id == project_id)
        return self.db.scalar(stmt) or 0
