import uuid
import urllib.parse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.calendar_integration import (
    CalendarConnectRead,
    CalendarImportBatchListRead,
    CalendarImportBatchRead,
    CalendarImportResultRead,
    CalendarIntegrationListRead,
    CalendarIntegrationRead,
    CalendarSyncResultRead,
)
from app.services.calendar_integration_service import CalendarIntegrationService
from app.services.onboarding_service import NotFoundError, ValidationError

router = APIRouter()


@router.get("/projects/{project_id}/calendar-integrations", response_model=CalendarIntegrationListRead)
def list_calendar_integrations(project_id: uuid.UUID, db: Session = Depends(get_db)) -> CalendarIntegrationListRead:
    service = CalendarIntegrationService(db)
    try:
        items = service.list_integrations(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CalendarIntegrationListRead(items=[_integration_read(item) for item in items], page=1, page_size=max(1, len(items)), total=len(items))


@router.get("/projects/{project_id}/calendar-imports", response_model=CalendarImportBatchListRead)
def list_calendar_imports(project_id: uuid.UUID, db: Session = Depends(get_db)) -> CalendarImportBatchListRead:
    service = CalendarIntegrationService(db)
    try:
        items = service.list_import_batches(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CalendarImportBatchListRead(
        items=[_import_batch_read(item) for item in items],
        page=1,
        page_size=max(1, len(items)),
        total=len(items),
    )


@router.post("/projects/{project_id}/calendar-integrations/microsoft365/connect", response_model=CalendarConnectRead)
def connect_microsoft365(project_id: uuid.UUID, db: Session = Depends(get_db)) -> CalendarConnectRead:
    service = CalendarIntegrationService(db)
    try:
        auth_url = service.start_microsoft365_connect(project_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CalendarConnectRead(auth_url=auth_url)


@router.post("/projects/{project_id}/calendar-integrations/microsoft365/sync", response_model=CalendarSyncResultRead)
def sync_microsoft365(project_id: uuid.UUID, db: Session = Depends(get_db)) -> CalendarSyncResultRead:
    service = CalendarIntegrationService(db)
    try:
        integration, imported, updated = service.sync_microsoft365(project_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CalendarSyncResultRead(integration=_integration_read(integration), imported=imported, updated=updated)


@router.post("/projects/{project_id}/calendar-integrations/ics/import", response_model=CalendarImportResultRead)
def import_ics_calendar(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> CalendarImportResultRead:
    service = CalendarIntegrationService(db)
    try:
        content = file.file.read().decode("utf-8", errors="ignore")
        imported, updated = service.import_ics_file(project_id, file.filename or "calendar.ics", content)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        file.file.close()
    return CalendarImportResultRead(imported=imported, updated=updated)


@router.delete("/projects/{project_id}/calendar-imports/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_import(project_id: uuid.UUID, batch_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    service = CalendarIntegrationService(db)
    try:
        service.delete_import_batch(project_id, batch_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/calendar-integrations/microsoft365/callback")
def microsoft365_callback(code: str, state: str, db: Session = Depends(get_db)) -> RedirectResponse:
    service = CalendarIntegrationService(db)
    try:
        integration = service.complete_microsoft365_callback(code, state)
        query = urllib.parse.urlencode(
            {
                "calendar": "connected",
                "provider": integration.provider.value,
                "project_id": str(integration.project_id),
            }
        )
    except ValidationError as exc:
        db.rollback()
        query = urllib.parse.urlencode({"calendar": "error", "detail": str(exc)})
    return RedirectResponse(url=f"{settings.frontend_app_url.rstrip('/')}/?{query}")


def _integration_read(item) -> CalendarIntegrationRead:
    return CalendarIntegrationRead(
        id=str(item.id),
        project_id=str(item.project_id),
        provider=item.provider.value if hasattr(item.provider, "value") else str(item.provider),
        connected_account_email=item.connected_account_email,
        token_expires_at=item.token_expires_at,
        last_synced_at=item.last_synced_at,
        sync_status=item.sync_status.value if hasattr(item.sync_status, "value") else str(item.sync_status),
        last_error=item.last_error,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _import_batch_read(item) -> CalendarImportBatchRead:
    return CalendarImportBatchRead(
        id=str(item.id),
        project_id=str(item.project_id),
        filename=item.filename,
        imported_count=item.imported_count,
        updated_count=item.updated_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
