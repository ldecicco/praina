import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.meeting import MeetingRecord, MeetingSourceType
from app.schemas.meeting import MeetingRecordCreate, MeetingRecordListRead, MeetingRecordRead, MeetingRecordUpdate
from app.services.meeting_ingestion_service import MeetingIngestionService
from app.services.meeting_service import MeetingService
from app.services.onboarding_service import NotFoundError, ValidationError

router = APIRouter()


@router.get("/{project_id}/meetings", response_model=MeetingRecordListRead)
def list_meetings(
    project_id: uuid.UUID,
    search: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MeetingRecordListRead:
    service = MeetingService(db)
    try:
        items, total = service.list_meetings(project_id, search, source_type, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MeetingRecordListRead(items=[_meeting_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/meetings", response_model=MeetingRecordRead)
def create_meeting(project_id: uuid.UUID, payload: MeetingRecordCreate, db: Session = Depends(get_db)) -> MeetingRecordRead:
    service = MeetingService(db)
    try:
        record = service.create_meeting(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _meeting_read(record)


@router.patch("/{project_id}/meetings/{meeting_id}", response_model=MeetingRecordRead)
def update_meeting(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    payload: MeetingRecordUpdate,
    db: Session = Depends(get_db),
) -> MeetingRecordRead:
    service = MeetingService(db)
    try:
        record = service.update_meeting(project_id, meeting_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _meeting_read(record)


@router.post("/{project_id}/meetings/upload", response_model=MeetingRecordRead)
def upload_meeting_transcript(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str = Form(...),
    starts_at: str = Form(...),
    source_type: str = Form(default="transcript"),
    participants: str = Form(default=""),
    created_by_member_id: uuid.UUID | None = Form(default=None),
    db: Session = Depends(get_db),
) -> MeetingRecordRead:
    from datetime import datetime as dt

    service = MeetingService(db)
    try:
        service._get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Parse starts_at
    try:
        parsed_starts_at = dt.fromisoformat(starts_at)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid starts_at datetime.") from exc

    # Save uploaded file
    safe_name = Path(file.filename or "transcript.bin").name
    root = Path(settings.documents_storage_path)
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    target_dir = root / "meetings" / str(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{uuid.uuid4()}_{safe_name}"
    with open(file_path, "wb") as f:
        content = file.file.read()
        f.write(content)
    file.file.close()

    # Parse participants
    participant_list = [p.strip() for p in participants.split(",") if p.strip()] if participants else []

    # Normalize source_type
    try:
        src_type = MeetingSourceType(source_type.strip().lower())
    except ValueError:
        src_type = MeetingSourceType.transcript

    # Create meeting record
    record = MeetingRecord(
        project_id=project_id,
        title=title.strip(),
        starts_at=parsed_starts_at,
        source_type=src_type,
        participants_json=participant_list,
        content_text="",
        original_filename=safe_name,
        created_by_member_id=created_by_member_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Extract text and index
    try:
        mime = file.content_type or "application/octet-stream"
        MeetingIngestionService(db).extract_and_index_from_file(record, file_path, mime)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _meeting_read(record)


@router.delete("/{project_id}/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    service = MeetingService(db)
    try:
        service.delete_meeting(project_id, meeting_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{project_id}/meetings/{meeting_id}/reindex", response_model=MeetingRecordRead)
def reindex_meeting(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> MeetingRecordRead:
    record = db.scalar(
        select(MeetingRecord).where(MeetingRecord.project_id == project_id, MeetingRecord.id == meeting_id)
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found in project.")
    MeetingIngestionService(db).index_meeting(record)
    return _meeting_read(record)


def _meeting_read(item) -> MeetingRecordRead:
    return MeetingRecordRead(
        id=str(item.id),
        project_id=str(item.project_id),
        title=item.title,
        starts_at=item.starts_at,
        source_type=item.source_type.value if hasattr(item.source_type, "value") else str(item.source_type),
        source_url=item.source_url,
        participants=list(item.participants_json or []),
        content_text=item.content_text,
        summary=getattr(item, "summary", None),
        external_calendar_event_id=str(getattr(item, "external_calendar_event_id", None) or "") or None,
        import_batch_id=str(getattr(item, "import_batch_id", None) or "") or None,
        indexing_status=getattr(item, "indexing_status", "pending"),
        original_filename=getattr(item, "original_filename", None),
        linked_document_id=str(item.linked_document_id) if item.linked_document_id else None,
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
