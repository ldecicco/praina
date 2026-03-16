from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.organization import TeamMember
from app.schemas.todo import TodoCreate, TodoListRead, TodoRead, TodoUpdate
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.todo_service import TodoService

router = APIRouter()


def _resolve_creator_member(db: Session, user: UserAccount, project_id: uuid.UUID) -> uuid.UUID | None:
    row = db.scalar(
        select(TeamMember.id).where(
            TeamMember.user_account_id == user.id,
            TeamMember.project_id == project_id,
            TeamMember.is_active.is_(True),
        )
    )
    return row


@router.get("/{project_id}/todos", response_model=TodoListRead)
def list_todos(
    project_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    assignee_member_id: str | None = Query(default=None),
    wp_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TodoListRead:
    service = TodoService(db)
    try:
        items, total = service.list_items(
            project_id,
            status_filter=status_filter,
            assignee_member_id=uuid.UUID(assignee_member_id) if assignee_member_id else None,
            wp_id=uuid.UUID(wp_id) if wp_id else None,
            task_id=uuid.UUID(task_id) if task_id else None,
            page=page,
            page_size=page_size,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TodoListRead(items=[_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/todos", response_model=TodoRead)
def create_todo(
    project_id: uuid.UUID,
    payload: TodoCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> TodoRead:
    creator_member_id = _resolve_creator_member(db, current_user, project_id)
    service = TodoService(db)
    try:
        item = service.create_item(
            project_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            creator_member_id=creator_member_id,
            assignee_member_id=uuid.UUID(payload.assignee_member_id) if payload.assignee_member_id else None,
            wp_id=uuid.UUID(payload.wp_id) if payload.wp_id else None,
            task_id=uuid.UUID(payload.task_id) if payload.task_id else None,
            due_date=payload.due_date,
            sort_order=payload.sort_order,
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _read(item)


@router.patch("/{project_id}/todos/{todo_id}", response_model=TodoRead)
def update_todo(
    project_id: uuid.UUID,
    todo_id: uuid.UUID,
    payload: TodoUpdate,
    db: Session = Depends(get_db),
) -> TodoRead:
    service = TodoService(db)
    try:
        item = service.update_item(
            project_id,
            todo_id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            priority=payload.priority,
            assignee_member_id=payload.assignee_member_id,
            wp_id=payload.wp_id,
            task_id=payload.task_id,
            due_date=payload.due_date,
            sort_order=payload.sort_order,
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _read(item)


@router.delete("/{project_id}/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    project_id: uuid.UUID,
    todo_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    service = TodoService(db)
    try:
        service.delete_item(project_id, todo_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _read(item) -> TodoRead:
    return TodoRead(
        id=str(item.id),
        project_id=str(item.project_id),
        title=item.title,
        description=item.description,
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        priority=item.priority.value if hasattr(item.priority, "value") else str(item.priority),
        creator_member_id=str(item.creator_member_id) if item.creator_member_id else None,
        assignee_member_id=str(item.assignee_member_id) if item.assignee_member_id else None,
        wp_id=str(item.wp_id) if item.wp_id else None,
        task_id=str(item.task_id) if item.task_id else None,
        due_date=item.due_date,
        sort_order=item.sort_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
