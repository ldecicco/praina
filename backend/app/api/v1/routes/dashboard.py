"""Dashboard health endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.dashboard_health_service import DashboardHealthService
from app.services.onboarding_service import NotFoundError, ValidationError


router = APIRouter()


class DashboardIssueActionRead(BaseModel):
    type: str
    label: str
    view: str | None = None


class DashboardIssueRead(BaseModel):
    issue_key: str
    source: str
    severity: str
    category: str
    entity_type: str | None = None
    entity_id: str | None = None
    message: str
    suggestion: str | None = None
    status: str = "open"
    snoozed_until: str | None = None
    rationale: str | None = None
    primary_action: DashboardIssueActionRead | None = None


class DashboardHealthResponse(BaseModel):
    scope_type: str = "project"
    scope_ref_id: str | None = None
    validation_errors: int = 0
    validation_warnings: int = 0
    coherence_issues: int = 0
    action_items_pending: int = 0
    risks_open: int = 0
    overdue_deliverables: int = 0
    health_score: str = "green"
    validation_error_details: list[DashboardIssueRead] = Field(default_factory=list)
    validation_warning_details: list[DashboardIssueRead] = Field(default_factory=list)
    coherence_issue_details: list[DashboardIssueRead] = Field(default_factory=list)


class DashboardHealthSnapshotRead(BaseModel):
    id: str
    health_score: str
    validation_errors: int
    validation_warnings: int
    coherence_issues: int
    action_items_pending: int
    risks_open: int
    overdue_deliverables: int
    created_at: str


class DashboardRecurringIssueRead(BaseModel):
    issue_key: str
    category: str
    count: int
    message: str


class DashboardScopeOptionRead(BaseModel):
    id: str
    label: str


class DashboardScopeOptionsResponse(BaseModel):
    work_packages: list[DashboardScopeOptionRead] = Field(default_factory=list)
    tasks: list[DashboardScopeOptionRead] = Field(default_factory=list)
    deliverables: list[DashboardScopeOptionRead] = Field(default_factory=list)
    milestones: list[DashboardScopeOptionRead] = Field(default_factory=list)


class DashboardIssueStateUpdateRequest(BaseModel):
    issue_key: str
    source: str
    category: str
    entity_type: str | None = None
    entity_id: str | None = None
    status: str
    rationale: str | None = None
    snooze_days: int | None = Field(default=None, ge=1, le=90)


class DashboardIssueStateRead(BaseModel):
    issue_key: str
    status: str
    rationale: str | None = None
    snoozed_until: str | None = None


class DashboardIssueInboxCreateRequest(BaseModel):
    issue_key: str
    source: str
    severity: str
    category: str
    entity_type: str | None = None
    entity_id: str | None = None
    message: str
    suggestion: str | None = None


class DashboardIssueInboxCreateResponse(BaseModel):
    id: str
    title: str
    status: str


@router.get("/{project_id}/dashboard/health", response_model=DashboardHealthResponse)
def dashboard_health(
    project_id: uuid.UUID,
    scope_type: str = Query(default="project"),
    scope_ref_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DashboardHealthResponse:
    service = DashboardHealthService(db)
    try:
        return DashboardHealthResponse(**service.run_health(project_id, scope_type=scope_type, scope_ref_id=scope_ref_id))
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{project_id}/dashboard/health-latest", response_model=DashboardHealthResponse | None)
def dashboard_health_latest(
    project_id: uuid.UUID,
    scope_type: str = Query(default="project"),
    scope_ref_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> DashboardHealthResponse | None:
    service = DashboardHealthService(db)
    try:
        payload = service.latest_saved_health(project_id, scope_type=scope_type, scope_ref_id=scope_ref_id)
        return DashboardHealthResponse(**payload) if payload else None
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{project_id}/dashboard/health-history", response_model=list[DashboardHealthSnapshotRead])
def dashboard_health_history(project_id: uuid.UUID, db: Session = Depends(get_db)) -> list[DashboardHealthSnapshotRead]:
    service = DashboardHealthService(db)
    rows = service.list_history(project_id, limit=12)
    return [
        DashboardHealthSnapshotRead(
            id=str(item.id),
            health_score=item.health_score,
            validation_errors=item.validation_errors,
            validation_warnings=item.validation_warnings,
            coherence_issues=item.coherence_issues,
            action_items_pending=item.action_items_pending,
            risks_open=item.risks_open,
            overdue_deliverables=item.overdue_deliverables,
            created_at=item.created_at.isoformat(),
        )
        for item in rows
    ]


@router.get("/{project_id}/dashboard/health-recurring", response_model=list[DashboardRecurringIssueRead])
def dashboard_health_recurring(project_id: uuid.UUID, db: Session = Depends(get_db)) -> list[DashboardRecurringIssueRead]:
    service = DashboardHealthService(db)
    return [DashboardRecurringIssueRead(**item) for item in service.recurring_analytics(project_id)]


@router.get("/{project_id}/dashboard/health-scope-options", response_model=DashboardScopeOptionsResponse)
def dashboard_health_scope_options(project_id: uuid.UUID, db: Session = Depends(get_db)) -> DashboardScopeOptionsResponse:
    service = DashboardHealthService(db)
    return DashboardScopeOptionsResponse(**service.scope_options(project_id))


@router.post("/{project_id}/dashboard/health/issues/state", response_model=DashboardIssueStateRead)
def dashboard_health_issue_state(
    project_id: uuid.UUID,
    payload: DashboardIssueStateUpdateRequest,
    db: Session = Depends(get_db),
) -> DashboardIssueStateRead:
    service = DashboardHealthService(db)
    try:
        snoozed_until = None
        if payload.status.strip().lower() == "snoozed" and payload.snooze_days:
            from datetime import datetime, timedelta, timezone

            snoozed_until = datetime.now(timezone.utc) + timedelta(days=payload.snooze_days)
        state = service.set_issue_state(
            project_id,
            issue_key=payload.issue_key,
            source=payload.source,
            category=payload.category,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            status=payload.status,
            rationale=payload.rationale,
            snoozed_until=snoozed_until,
        )
        return DashboardIssueStateRead(
            issue_key=state.issue_key,
            status=state.status,
            rationale=state.rationale,
            snoozed_until=state.snoozed_until.isoformat() if state.snoozed_until else None,
        )
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{project_id}/dashboard/health/issues/inbox", response_model=DashboardIssueInboxCreateResponse)
def dashboard_health_issue_inbox(
    project_id: uuid.UUID,
    payload: DashboardIssueInboxCreateRequest,
    db: Session = Depends(get_db),
) -> DashboardIssueInboxCreateResponse:
    service = DashboardHealthService(db)
    try:
        item = service.create_inbox_item_from_issue(project_id, payload.model_dump())
        return DashboardIssueInboxCreateResponse(id=str(item.id), title=item.title, status=str(getattr(item.status, "value", item.status)))
    except (ValidationError, NotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
