"""Reporting & export endpoints."""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.report_service import ReportService

router = APIRouter()


@router.get("/{project_id}/reports/status")
def status_report(project_id: uuid.UUID, db: Session = Depends(get_db)):
    svc = ReportService(db)
    markdown = svc.generate_status_report(project_id)
    return PlainTextResponse(content=markdown, media_type="text/markdown")


@router.get("/{project_id}/reports/meeting/{meeting_id}")
def meeting_report(project_id: uuid.UUID, meeting_id: uuid.UUID, db: Session = Depends(get_db)):
    svc = ReportService(db)
    markdown = svc.generate_meeting_report(project_id, meeting_id)
    return PlainTextResponse(content=markdown, media_type="text/markdown")


@router.get("/{project_id}/reports/audit-log")
def audit_log_csv(
    project_id: uuid.UUID,
    event_type: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
):
    svc = ReportService(db)
    rows = svc.export_audit_log(project_id, event_type=event_type, start_date=start_date, end_date=end_date)

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        writer = csv.writer(output)
        writer.writerow(["id", "event_type", "entity_type", "entity_id", "actor_name", "reason", "created_at"])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-log-{project_id}.csv"},
    )
