from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.project_inbox import ProjectInboxCreate, ProjectInboxListRead, ProjectInboxRead, ProjectInboxUpdate
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.project_inbox_service import ProjectInboxService

router = APIRouter()


@router.get("/{project_id}/inbox", response_model=ProjectInboxListRead)
def list_project_inbox(
    project_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ProjectInboxListRead:
    service = ProjectInboxService(db)
    try:
        items, total = service.list_items(project_id, status_filter=status_filter, page=page, page_size=page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProjectInboxListRead(items=[_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/inbox", response_model=ProjectInboxRead)
def create_project_inbox(
    project_id: uuid.UUID,
    payload: ProjectInboxCreate,
    db: Session = Depends(get_db),
) -> ProjectInboxRead:
    service = ProjectInboxService(db)
    try:
        item = service.create_item(
            project_id,
            title=payload.title,
            details=payload.details,
            priority=payload.priority,
            source_type=payload.source_type,
            source_key=payload.source_key,
            assignee_member_id=uuid.UUID(payload.assignee_member_id) if payload.assignee_member_id else None,
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _read(item)


@router.patch("/{project_id}/inbox/{item_id}", response_model=ProjectInboxRead)
def update_project_inbox(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ProjectInboxUpdate,
    db: Session = Depends(get_db),
) -> ProjectInboxRead:
    service = ProjectInboxService(db)
    try:
        item = service.update_item(project_id, item_id, status=payload.status)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _read(item)


def _read(item) -> ProjectInboxRead:
    return ProjectInboxRead(
        id=str(item.id),
        project_id=str(item.project_id),
        title=item.title,
        details=item.details,
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        priority=item.priority.value if hasattr(item.priority, "value") else str(item.priority),
        source_type=item.source_type.value if hasattr(item.source_type, "value") else str(item.source_type),
        source_key=item.source_key,
        assignee_member_id=str(item.assignee_member_id) if item.assignee_member_id else None,
        due_date=item.due_date,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
