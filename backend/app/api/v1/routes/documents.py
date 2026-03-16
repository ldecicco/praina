import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import DocumentScope
from app.schemas.document import (
    DocumentLinkPayload,
    DocumentListRead,
    DocumentReindexResultRead,
    DocumentRead,
    DocumentUploadPayload,
    DocumentVersionListRead,
    DocumentVersionRead,
    DocumentVersionUploadPayload,
)
from app.services.document_ingestion_service import DocumentIngestionService, run_document_reindex_job
from app.services.document_service import DocumentService
from app.services.onboarding_service import NotFoundError, ValidationError

router = APIRouter()


@router.post("/{project_id}/documents/upload", response_model=DocumentVersionRead)
def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    scope: DocumentScope = Form(...),
    title: str = Form(...),
    metadata_json: str | None = Form(default=None),
    wp_id: uuid.UUID | None = Form(default=None),
    task_id: uuid.UUID | None = Form(default=None),
    deliverable_id: uuid.UUID | None = Form(default=None),
    milestone_id: uuid.UUID | None = Form(default=None),
    uploaded_by_member_id: uuid.UUID | None = Form(default=None),
    proposal_section_id: uuid.UUID | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentVersionRead:
    service = DocumentService(db)
    try:
        payload = DocumentUploadPayload(
            scope=scope,
            title=title,
            metadata_json=_metadata_from_form(metadata_json),
            wp_id=wp_id,
            task_id=task_id,
            deliverable_id=deliverable_id,
            milestone_id=milestone_id,
            uploaded_by_member_id=uploaded_by_member_id,
            proposal_section_id=proposal_section_id,
        )
        created = service.create_document(
            project_id=project_id,
            payload=payload,
            file_name=file.filename or "document.bin",
            content_type=file.content_type or "application/octet-stream",
            file_stream=file.file,
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metadata_json must be valid JSON.") from exc
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        file.file.close()
    return _document_version_read(created)


@router.post("/{project_id}/documents/{document_key}/versions/upload", response_model=DocumentVersionRead)
def upload_document_version(
    project_id: uuid.UUID,
    document_key: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    metadata_json: str | None = Form(default=None),
    uploaded_by_member_id: uuid.UUID | None = Form(default=None),
    proposal_section_id: uuid.UUID | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentVersionRead:
    service = DocumentService(db)
    try:
        payload = DocumentVersionUploadPayload(
            title=title,
            metadata_json=_metadata_from_form_optional(metadata_json),
            uploaded_by_member_id=uploaded_by_member_id,
            proposal_section_id=proposal_section_id,
        )
        created = service.create_new_version(
            project_id=project_id,
            document_key=document_key,
            payload=payload,
            file_name=file.filename or "document.bin",
            content_type=file.content_type or "application/octet-stream",
            file_stream=file.file,
        )
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metadata_json must be valid JSON.") from exc
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        file.file.close()
    return _document_version_read(created)


@router.get("/{project_id}/documents", response_model=DocumentListRead)
def list_documents(
    project_id: uuid.UUID,
    scope: DocumentScope | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    wp_id: uuid.UUID | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    deliverable_id: uuid.UUID | None = Query(default=None),
    milestone_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DocumentListRead:
    service = DocumentService(db)
    try:
        items, total = service.list_documents(
            project_id=project_id,
            scope=scope,
            status=status_filter,
            wp_id=wp_id,
            task_id=task_id,
            deliverable_id=deliverable_id,
            milestone_id=milestone_id,
            search=search,
            page=page,
            page_size=page_size,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DocumentListRead(items=[_document_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.get("/{project_id}/documents/{document_id}", response_model=DocumentVersionRead)
def get_document_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentVersionRead:
    service = DocumentService(db)
    try:
        document = service.get_document_version(project_id, document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _document_version_read(document)


@router.get("/{project_id}/documents/by-key/{document_key}/versions", response_model=DocumentVersionListRead)
def get_document_versions(
    project_id: uuid.UUID,
    document_key: uuid.UUID,
    db: Session = Depends(get_db),
) -> DocumentVersionListRead:
    service = DocumentService(db)
    try:
        versions = service.get_document_versions(project_id, document_key)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DocumentVersionListRead(document_key=str(document_key), versions=[_document_version_read(item) for item in versions])


@router.post("/{project_id}/documents/{document_id}/reindex", response_model=DocumentReindexResultRead)
def reindex_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    async_job: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> DocumentReindexResultRead:
    service = DocumentIngestionService(db)
    try:
        if async_job:
            doc = service.mark_for_reindex(project_id=project_id, document_id=document_id)
            background_tasks.add_task(run_document_reindex_job, project_id, document_id)
            return DocumentReindexResultRead(
                document_id=str(doc.id),
                status="queued",
                chunks_indexed=0,
                queued=True,
                error=None,
            )
        result = service.reindex_document(project_id=project_id, document_id=document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return DocumentReindexResultRead(
        document_id=str(result.document_id),
        status=result.status,
        chunks_indexed=result.chunks_indexed,
        queued=False,
        error=result.error,
    )


@router.post("/{project_id}/documents/link", response_model=DocumentVersionRead)
def link_document(
    project_id: uuid.UUID,
    payload: DocumentLinkPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> DocumentVersionRead:
    service = DocumentService(db)
    try:
        created = service.create_document_from_url(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    background_tasks.add_task(run_document_reindex_job, project_id, created.id)
    return _document_version_read(created)


@router.post("/{project_id}/documents/{document_id}/refresh", response_model=DocumentVersionRead)
def refresh_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> DocumentVersionRead:
    service = DocumentService(db)
    try:
        created = service.refresh_from_url(project_id, document_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    background_tasks.add_task(run_document_reindex_job, project_id, created.id)
    return _document_version_read(created)


def _metadata_from_form(metadata_json: str | None) -> dict:
    if metadata_json is None or metadata_json == "":
        return {}
    parsed = json.loads(metadata_json)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("metadata_json must decode to an object.", metadata_json, 0)
    return parsed


def _metadata_from_form_optional(metadata_json: str | None) -> dict | None:
    if metadata_json is None:
        return None
    if metadata_json == "":
        return {}
    parsed = json.loads(metadata_json)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("metadata_json must decode to an object.", metadata_json, 0)
    return parsed


def _document_read(item) -> DocumentRead:
    return DocumentRead(
        latest_document_id=str(item.id),
        document_key=str(item.document_key),
        project_id=str(item.project_id),
        scope=item.scope.value if hasattr(item.scope, "value") else str(item.scope),
        title=item.title,
        status=item.status,
        latest_version=item.version,
        versions_count=_versions_count(item),
        wp_id=str(item.wp_id) if item.wp_id else None,
        task_id=str(item.task_id) if item.task_id else None,
        deliverable_id=str(item.deliverable_id) if item.deliverable_id else None,
        milestone_id=str(item.milestone_id) if item.milestone_id else None,
        uploaded_by_member_id=str(item.uploaded_by_member_id) if item.uploaded_by_member_id else None,
        indexed_at=item.indexed_at,
        ingestion_error=item.ingestion_error,
        source_url=getattr(item, "source_url", None),
        source_type=getattr(item, "source_type", None),
        proposal_section_id=str(item.proposal_section_id) if getattr(item, "proposal_section_id", None) else None,
        updated_at=item.updated_at,
    )


def _versions_count(item) -> int:
    return int(getattr(item, "versions_count", item.version))


def _document_version_read(item) -> DocumentVersionRead:
    return DocumentVersionRead(
        id=str(item.id),
        document_key=str(item.document_key),
        project_id=str(item.project_id),
        scope=item.scope.value if hasattr(item.scope, "value") else str(item.scope),
        title=item.title,
        storage_uri=item.storage_uri,
        original_filename=item.original_filename,
        file_size_bytes=item.file_size_bytes,
        mime_type=item.mime_type,
        status=item.status,
        version=item.version,
        metadata_json=item.metadata_json,
        wp_id=str(item.wp_id) if item.wp_id else None,
        task_id=str(item.task_id) if item.task_id else None,
        deliverable_id=str(item.deliverable_id) if item.deliverable_id else None,
        milestone_id=str(item.milestone_id) if item.milestone_id else None,
        uploaded_by_member_id=str(item.uploaded_by_member_id) if item.uploaded_by_member_id else None,
        indexed_at=item.indexed_at,
        ingestion_error=item.ingestion_error,
        source_url=getattr(item, "source_url", None),
        source_type=getattr(item, "source_type", None),
        proposal_section_id=str(item.proposal_section_id) if getattr(item, "proposal_section_id", None) else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
