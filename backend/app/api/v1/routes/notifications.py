"""Notification CRUD endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.schemas.notification import NotificationListRead, NotificationRead, UnreadCountRead
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("/notifications", response_model=NotificationListRead)
def list_notifications(
    project_id: uuid.UUID | None = Query(None),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = NotificationService(db)
    items, total = svc.list_notifications(current_user.id, project_id=project_id, unread_only=unread_only, page=page, page_size=page_size)
    return NotificationListRead(
        items=[_to_read(n) for n in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountRead)
def unread_count(
    project_id: uuid.UUID | None = Query(None),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = NotificationService(db)
    count = svc.unread_count(current_user.id, project_id=project_id)
    return UnreadCountRead(count=count)


@router.post("/notifications/{notification_id}/read", response_model=dict)
def mark_read(
    notification_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = NotificationService(db)
    ok = svc.mark_read(current_user.id, notification_id)
    return {"ok": ok}


@router.post("/notifications/read-all", response_model=dict)
def mark_all_read(
    project_id: uuid.UUID | None = Query(None),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = NotificationService(db)
    count = svc.mark_all_read(current_user.id, project_id=project_id)
    return {"marked_read": count}


def _to_read(n) -> NotificationRead:
    return NotificationRead(
        id=str(n.id),
        user_id=str(n.user_id),
        project_id=str(n.project_id) if n.project_id else None,
        channel=n.channel,
        status=n.status,
        title=n.title,
        body=n.body,
        link_type=n.link_type,
        link_id=str(n.link_id) if n.link_id else None,
        created_at=n.created_at.isoformat() if n.created_at else "",
        updated_at=n.updated_at.isoformat() if n.updated_at else "",
    )
