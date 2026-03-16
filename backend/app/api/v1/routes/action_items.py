import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.action_item import (
    ActionItemCreate,
    ActionItemExtractionRead,
    ActionItemListRead,
    ActionItemPromoteRequest,
    ActionItemRead,
    ActionItemUpdate,
)
from app.services.action_item_service import ActionItemService
from app.services.onboarding_service import NotFoundError, ValidationError

router = APIRouter()


@router.get("/{project_id}/meetings/{meeting_id}/action-items", response_model=ActionItemListRead)
def list_action_items(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ActionItemListRead:
    service = ActionItemService(db)
    try:
        items, total = service.list_action_items(project_id, meeting_id, status_filter, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionItemListRead(items=[_action_item_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/meetings/{meeting_id}/action-items", response_model=ActionItemRead)
def create_action_item(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    payload: ActionItemCreate,
    db: Session = Depends(get_db),
) -> ActionItemRead:
    service = ActionItemService(db)
    try:
        item = service.create_action_item(project_id, meeting_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _action_item_read(item)


@router.patch("/{project_id}/meetings/{meeting_id}/action-items/{item_id}", response_model=ActionItemRead)
def update_action_item(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ActionItemUpdate,
    db: Session = Depends(get_db),
) -> ActionItemRead:
    service = ActionItemService(db)
    try:
        item = service.update_action_item(project_id, meeting_id, item_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _action_item_read(item)


@router.post("/{project_id}/meetings/{meeting_id}/action-items/{item_id}/promote", response_model=ActionItemRead)
def promote_action_item(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ActionItemPromoteRequest,
    db: Session = Depends(get_db),
) -> ActionItemRead:
    service = ActionItemService(db)
    try:
        item = service.promote_to_task(project_id, meeting_id, item_id, payload.wp_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _action_item_read(item)


@router.post("/{project_id}/meetings/{meeting_id}/extract-actions", response_model=ActionItemExtractionRead)
def extract_action_items(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ActionItemExtractionRead:
    service = ActionItemService(db)
    try:
        meeting, items = service.extract_action_items(project_id, meeting_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ActionItemExtractionRead(summary=meeting.summary, items=[_action_item_read(item) for item in items])


def _action_item_read(item) -> ActionItemRead:
    return ActionItemRead(
        id=str(item.id),
        project_id=str(item.project_id),
        meeting_id=str(item.meeting_id),
        description=item.description,
        assignee_name=item.assignee_name,
        assignee_member_id=str(item.assignee_member_id) if item.assignee_member_id else None,
        due_date=item.due_date,
        priority=item.priority.value if hasattr(item.priority, "value") else str(item.priority),
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        source=item.source.value if hasattr(item.source, "value") else str(item.source),
        linked_task_id=str(item.linked_task_id) if item.linked_task_id else None,
        sort_order=item.sort_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
