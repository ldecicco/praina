import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.proposal_image import ProposalImage
from app.schemas.proposal import (
    ProposalCallBriefImportPayload,
    ProposalCallBriefRead,
    ProposalCallBriefUpsert,
    ProposalCallComplianceRunPayload,
    ProposalCallDocumentReindexResultRead,
    ProposalCallLibraryDocumentListRead,
    ProposalCallLibraryDocumentUpdate,
    ProposalCallLibraryDocumentRead,
    ProposalCallIngestJobRead,
    ProposalCallAnswerRead,
    ProposalCallQuestionPayload,
    ProposalCallLibraryIngestRead,
    ProposalCallLibraryEntryCreate,
    ProposalCallLibraryEntryListRead,
    ProposalCallLibraryEntryRead,
    ProposalCallLibraryEntryUpdate,
    ProposalSubmissionItemRead,
    ProposalSubmissionItemUpdate,
    ProposalSubmissionRequirementCreate,
    ProposalSubmissionRequirementListRead,
    ProposalSubmissionRequirementRead,
    ProposalSubmissionRequirementUpdate,
    ProposalReviewFindingCreate,
    ProposalReviewFindingListRead,
    ProposalReviewFindingRead,
    ProposalReviewFindingUpdate,
    ProposalReviewRunPayload,
    ProposalReviewRunRead,
    ProjectProposalSectionListRead,
    ProjectProposalSectionRead,
    ProjectProposalSectionUpdate,
    ProposalTemplateCreate,
    ProposalTemplateListRead,
    ProposalTemplateRead,
    ProposalTemplateSectionCreate,
    ProposalTemplateSectionUpdate,
    ProposalTemplateUpdate,
)
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.proposal_service import ProposalService, run_call_library_ingest_job
from app.services.proposal_call_document_ingestion_service import (
    ProposalCallDocumentIngestionService,
    run_call_document_reindex_job,
)
from app.services.proposal_call_qa_service import ProposalCallQAService
from app.services.proposal_review_service import ProposalReviewService
from app.services.proposal_export_service import ProposalExportService

router = APIRouter()


@router.get("/proposal-call-library", response_model=ProposalCallLibraryEntryListRead)
def list_proposal_call_library(
    search: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallLibraryEntryListRead:
    _ = current_user
    service = ProposalService(db)
    items, total = service.list_call_library_entries(page=page, page_size=page_size, search=search, active_only=active_only)
    return ProposalCallLibraryEntryListRead(
        items=[_proposal_call_library_entry_read(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/proposal-call-library", response_model=ProposalCallLibraryEntryRead)
def create_proposal_call_library_entry(
    payload: ProposalCallLibraryEntryCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallLibraryEntryRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    item = service.create_call_library_entry(payload)
    return _proposal_call_library_entry_read(item)


@router.patch("/proposal-call-library/{library_entry_id}", response_model=ProposalCallLibraryEntryRead)
def update_proposal_call_library_entry(
    library_entry_id: uuid.UUID,
    payload: ProposalCallLibraryEntryUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallLibraryEntryRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.update_call_library_entry(library_entry_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _proposal_call_library_entry_read(item)


@router.delete("/proposal-call-library/{library_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal_call_library_entry(
    library_entry_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        service.delete_call_library_entry(library_entry_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/proposal-call-library/ingest-pdf", response_model=ProposalCallLibraryIngestRead)
async def ingest_proposal_call_library_pdf(
    file: UploadFile = File(...),
    library_entry_id: uuid.UUID | None = Form(default=None),
    source_url: str | None = Form(default=None),
    category: str | None = Form(default=None),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallLibraryIngestRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        contents = await file.read()
        entry, document = service.ingest_call_library_pdf(
            file_name=file.filename or "call.pdf",
            content_type=file.content_type or "application/pdf",
            file_bytes=contents,
            library_entry_id=library_entry_id,
            source_url=source_url,
            category=category,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    finally:
        file.file.close()
    return ProposalCallLibraryIngestRead(
        entry=_proposal_call_library_entry_read(entry),
        document=_proposal_call_library_document_read(document),
    )


@router.post("/proposal-call-library/ingest-pdf-jobs", response_model=ProposalCallIngestJobRead)
async def start_proposal_call_library_ingest_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    library_entry_id: uuid.UUID | None = Form(default=None),
    source_url: str | None = Form(default=None),
    category: str | None = Form(default=None),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallIngestJobRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        contents = await file.read()
        job = service.start_call_library_ingest_job(
            file_name=file.filename or "call.pdf",
            content_type=file.content_type or "application/pdf",
            file_bytes=contents,
            created_by_user_id=current_user.id,
            library_entry_id=library_entry_id,
            source_url=source_url,
            category=category,
        )
        background_tasks.add_task(run_call_library_ingest_job, job.id)
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    finally:
        file.file.close()
    return _proposal_call_ingest_job_read(job)


@router.get("/proposal-call-library/ingest-pdf-jobs/{job_id}", response_model=ProposalCallIngestJobRead)
def get_proposal_call_library_ingest_job(
    job_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallIngestJobRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        job = service.get_call_library_ingest_job(job_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _proposal_call_ingest_job_read(job)


@router.get("/proposal-call-library/{library_entry_id}/documents", response_model=ProposalCallLibraryDocumentListRead)
def list_proposal_call_library_documents(
    library_entry_id: uuid.UUID,
    include_superseded: bool = Query(default=True),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallLibraryDocumentListRead:
    _ = current_user
    service = ProposalService(db)
    try:
        items = service.list_call_library_documents(library_entry_id, include_superseded=include_superseded)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProposalCallLibraryDocumentListRead(items=[_proposal_call_library_document_read(item) for item in items])


@router.patch("/proposal-call-library/{library_entry_id}/documents/{document_id}", response_model=ProposalCallLibraryDocumentRead)
def update_proposal_call_library_document(
    library_entry_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: ProposalCallLibraryDocumentUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallLibraryDocumentRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.update_call_library_document(
            library_entry_id,
            document_id,
            category=payload.category,
            status=payload.status,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _proposal_call_library_document_read(item)


@router.delete("/proposal-call-library/{library_entry_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal_call_library_document(
    library_entry_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        service.delete_call_library_document(library_entry_id, document_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/proposal-call-library/{library_entry_id}/documents/{document_id}/reindex",
    response_model=ProposalCallDocumentReindexResultRead,
)
def reindex_proposal_call_library_document(
    library_entry_id: uuid.UUID,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    async_job: bool = Query(default=True),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallDocumentReindexResultRead:
    _require_template_admin(current_user)
    service = ProposalCallDocumentIngestionService(db)
    try:
        if async_job:
            document = service.mark_for_reindex(library_entry_id, document_id)
            background_tasks.add_task(run_call_document_reindex_job, library_entry_id, document_id)
            return ProposalCallDocumentReindexResultRead(
                document_id=str(document.id),
                status="queued",
                chunks_indexed=0,
                queued=True,
                error=None,
            )
        result = service.reindex_document(library_entry_id, document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProposalCallDocumentReindexResultRead(
        document_id=str(result.document_id),
        status=result.status,
        chunks_indexed=result.chunks_indexed,
        queued=False,
        error=result.error,
    )


@router.post("/projects/{project_id}/proposal-call/ask", response_model=ProposalCallAnswerRead)
def ask_proposal_call_question(
    project_id: uuid.UUID,
    payload: ProposalCallQuestionPayload,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallAnswerRead:
    _ = current_user
    service = ProposalCallQAService(db)
    try:
        answer, citations = service.answer_question(project_id, payload.question)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProposalCallAnswerRead(
        answer=answer["answer"],
        grounded=bool(answer.get("grounded")),
        insufficient_reason=answer.get("insufficient_reason"),
        citations=[
            {
                "library_entry_id": citation.library_entry_id,
                "document_id": citation.document_id,
                "document_title": citation.document_title,
                "chunk_index": citation.chunk_index,
                "snippet": citation.snippet,
                "score": citation.score,
            }
            for index, citation in enumerate(citations)
            if index in set(answer.get("used_citation_indexes", []))
        ],
        retrieval_debug=[
            {
                "library_entry_id": citation.library_entry_id,
                "document_id": citation.document_id,
                "document_title": citation.document_title,
                "chunk_index": citation.chunk_index,
                "snippet": citation.snippet,
                "score": citation.score,
                "lexical_score": citation.lexical_score,
                "vector_score": citation.vector_score,
                "combined_score": citation.combined_score,
            }
            for citation in citations
        ],
    )


@router.get("/proposal-templates", response_model=ProposalTemplateListRead)
def list_templates(
    search: str | None = Query(default=None),
    active_only: bool = Query(default=False),
    call_library_entry_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateListRead:
    _ = current_user
    service = ProposalService(db)
    items, total = service.list_templates(
        page=page,
        page_size=page_size,
        search=search,
        active_only=active_only,
        call_library_entry_id=call_library_entry_id,
    )
    return ProposalTemplateListRead(items=[_template_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/proposal-templates", response_model=ProposalTemplateRead)
def create_template(
    payload: ProposalTemplateCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.create_template(payload)
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _template_read(item)


@router.get("/proposal-templates/{template_id}", response_model=ProposalTemplateRead)
def get_template(
    template_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateRead:
    _ = current_user
    service = ProposalService(db)
    try:
        item = service.get_template(template_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _template_read(item)


@router.patch("/proposal-templates/{template_id}", response_model=ProposalTemplateRead)
def update_template(
    template_id: uuid.UUID,
    payload: ProposalTemplateUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.update_template(template_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _template_read(item)


@router.delete("/proposal-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        service.delete_template(template_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/proposal-templates/{template_id}/sections", response_model=ProposalTemplateRead)
def create_template_section(
    template_id: uuid.UUID,
    payload: ProposalTemplateSectionCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.create_template_section(template_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _template_read(item)


@router.patch("/proposal-templates/{template_id}/sections/{section_id}", response_model=ProposalTemplateRead)
def update_template_section(
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: ProposalTemplateSectionUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.update_template_section(template_id, section_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _template_read(item)


@router.delete("/proposal-templates/{template_id}/sections/{section_id}", response_model=ProposalTemplateRead)
def delete_template_section(
    template_id: uuid.UUID,
    section_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalTemplateRead:
    _require_template_admin(current_user)
    service = ProposalService(db)
    try:
        item = service.delete_template_section(template_id, section_id)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _template_read(item)


@router.get("/projects/{project_id}/proposal-sections", response_model=ProjectProposalSectionListRead)
def list_project_sections(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectProposalSectionListRead:
    _ = current_user
    service = ProposalService(db)
    try:
        items = service.list_project_sections(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ProjectProposalSectionListRead(items=[_project_section_read(item) for item in items])


@router.patch("/projects/{project_id}/proposal-sections/{section_id}", response_model=ProjectProposalSectionRead)
def update_project_section(
    project_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: ProjectProposalSectionUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectProposalSectionRead:
    _ = current_user
    service = ProposalService(db)
    try:
        item = service.update_project_section(project_id, section_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _project_section_read(item)


@router.get("/projects/{project_id}/proposal-call-brief", response_model=ProposalCallBriefRead)
def get_proposal_call_brief(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallBriefRead:
    _ = current_user
    service = ProposalService(db)
    try:
        item = service.get_call_brief(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _proposal_call_brief_read(project_id, item)


@router.put("/projects/{project_id}/proposal-call-brief", response_model=ProposalCallBriefRead)
def upsert_proposal_call_brief(
    project_id: uuid.UUID,
    payload: ProposalCallBriefUpsert,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallBriefRead:
    _ = current_user
    service = ProposalService(db)
    try:
        item = service.upsert_call_brief(project_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _proposal_call_brief_read(project_id, item)


@router.post("/projects/{project_id}/proposal-call-brief/import", response_model=ProposalCallBriefRead)
def import_proposal_call_brief(
    project_id: uuid.UUID,
    payload: ProposalCallBriefImportPayload,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalCallBriefRead:
    service = ProposalService(db)
    try:
        item = service.import_call_brief_from_library(project_id, payload.library_entry_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _proposal_call_brief_read(project_id, item)


@router.get("/projects/{project_id}/proposal-submission-requirements", response_model=ProposalSubmissionRequirementListRead)
def list_project_submission_requirements(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalSubmissionRequirementListRead:
    service = ProposalService(db)
    try:
        items = service.list_submission_requirements_for_actor(
            project_id,
            actor_user_id=current_user.id,
            actor_platform_role=current_user.platform_role,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ProposalSubmissionRequirementListRead(items=[_proposal_submission_requirement_read(item) for item in items])


@router.post("/projects/{project_id}/proposal-submission-requirements", response_model=ProposalSubmissionRequirementRead)
def create_project_submission_requirement(
    project_id: uuid.UUID,
    payload: ProposalSubmissionRequirementCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalSubmissionRequirementRead:
    service = ProposalService(db)
    try:
        item = service.create_submission_requirement_for_actor(
            project_id,
            payload,
            actor_user_id=current_user.id,
            actor_platform_role=current_user.platform_role,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=404 if isinstance(exc, NotFoundError) else _proposal_validation_status(exc),
            detail=str(exc),
        ) from exc
    return _proposal_submission_requirement_read(item)


@router.patch(
    "/projects/{project_id}/proposal-submission-requirements/{requirement_id}",
    response_model=ProposalSubmissionRequirementRead,
)
def update_project_submission_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: ProposalSubmissionRequirementUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalSubmissionRequirementRead:
    service = ProposalService(db)
    try:
        item = service.update_submission_requirement_for_actor(
            project_id,
            requirement_id,
            payload,
            actor_user_id=current_user.id,
            actor_platform_role=current_user.platform_role,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=404 if isinstance(exc, NotFoundError) else _proposal_validation_status(exc),
            detail=str(exc),
        ) from exc
    return _proposal_submission_requirement_read(item)


@router.patch("/projects/{project_id}/proposal-submission-items/{item_id}", response_model=ProposalSubmissionItemRead)
def update_project_submission_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ProposalSubmissionItemUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalSubmissionItemRead:
    service = ProposalService(db)
    try:
        item = service.update_submission_item_for_actor(
            project_id,
            item_id,
            payload,
            actor_user_id=current_user.id,
            actor_platform_role=current_user.platform_role,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=404 if isinstance(exc, NotFoundError) else _proposal_validation_status(exc),
            detail=str(exc),
        ) from exc
    return _proposal_submission_item_read(item)


@router.get("/projects/{project_id}/proposal-review-findings", response_model=ProposalReviewFindingListRead)
def list_proposal_review_findings(
    project_id: uuid.UUID,
    proposal_section_id: uuid.UUID | None = Query(default=None),
    review_kind: str = Query(default="general"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalReviewFindingListRead:
    _ = current_user
    service = ProposalReviewService(db)
    rows, total = service.list_findings(project_id, proposal_section_id, review_kind, page, page_size)
    return ProposalReviewFindingListRead(
        items=[
            _proposal_review_finding_read(row["finding"], row["member_name"], row["replies"])
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/projects/{project_id}/proposal-review-findings", response_model=ProposalReviewFindingRead)
def create_proposal_review_finding(
    project_id: uuid.UUID,
    payload: ProposalReviewFindingCreate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalReviewFindingRead:
    _ = current_user
    service = ProposalReviewService(db)
    try:
        item = service.create_finding(project_id, payload)
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _proposal_review_finding_read(item)


@router.patch("/projects/{project_id}/proposal-review-findings/{finding_id}", response_model=ProposalReviewFindingRead)
def update_proposal_review_finding(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: ProposalReviewFindingUpdate,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalReviewFindingRead:
    _ = current_user
    service = ProposalReviewService(db)
    try:
        item = service.update_finding(project_id, finding_id, payload)
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _proposal_review_finding_read(item)


@router.delete("/projects/{project_id}/proposal-review-findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal_review_finding(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _ = current_user
    service = ProposalReviewService(db)
    try:
        service.delete_finding(project_id, finding_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/projects/{project_id}/proposal-review/run", response_model=ProposalReviewRunRead)
def run_proposal_review(
    project_id: uuid.UUID,
    payload: ProposalReviewRunPayload,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalReviewRunRead:
    _ = current_user
    service = ProposalReviewService(db)
    try:
        items = service.run_review(project_id, payload.proposal_section_id)
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Proposal review failed: {exc}") from exc
    return ProposalReviewRunRead(created=[_proposal_review_finding_read(item) for item in items])


@router.post("/projects/{project_id}/proposal-call-compliance/run", response_model=ProposalReviewRunRead)
def run_proposal_call_compliance_review(
    project_id: uuid.UUID,
    payload: ProposalCallComplianceRunPayload,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProposalReviewRunRead:
    _ = current_user
    service = ProposalReviewService(db)
    try:
        items = service.run_call_compliance_review(project_id, payload.proposal_section_id)
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Call compliance review failed: {exc}") from exc
    return ProposalReviewRunRead(created=[_proposal_review_finding_read(item) for item in items])


@router.get("/projects/{project_id}/proposal/export-pdf")
def export_proposal_pdf(
    project_id: uuid.UUID,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    _ = current_user
    service = ProposalExportService(db)
    try:
        pdf_bytes = service.generate_pdf(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # Fetch project code for filename
    from app.models.project import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    filename = f"{project.code}-proposal.pdf" if project and project.code else "proposal.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))


@router.post("/projects/{project_id}/proposal-images/upload")
async def upload_proposal_image(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _ = current_user
    if not file.content_type or file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {file.content_type}")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit.")

    image_id = uuid.uuid4()
    safe_filename = (file.filename or "image").replace("/", "_").replace("\\", "_")
    relative_path = f"proposal-images/{project_id}/{image_id}/{safe_filename}"
    full_path = STORAGE_ROOT / relative_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(contents)

    row = ProposalImage(
        id=image_id,
        project_id=project_id,
        original_filename=safe_filename,
        mime_type=file.content_type,
        file_size_bytes=len(contents),
        storage_path=relative_path,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    url = f"/api/v1/projects/{project_id}/proposal-images/{image_id}/content"
    return {"id": str(row.id), "url": url}


@router.get("/projects/{project_id}/proposal-images/{image_id}/content")
def serve_proposal_image(
    project_id: uuid.UUID,
    image_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    row = db.query(ProposalImage).filter(
        ProposalImage.id == image_id,
        ProposalImage.project_id == project_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found.")

    full_path = STORAGE_ROOT / row.storage_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing from storage.")

    return FileResponse(
        path=str(full_path),
        media_type=row.mime_type,
        filename=row.original_filename,
    )


@router.get("/proposal-call-library/{library_entry_id}/documents/{document_id}/content")
def serve_proposal_call_library_document(
    library_entry_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    from app.models.proposal import ProposalCallLibraryDocument

    row = db.query(ProposalCallLibraryDocument).filter(
        ProposalCallLibraryDocument.id == document_id,
        ProposalCallLibraryDocument.library_entry_id == library_entry_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Call document not found.")
    full_path = STORAGE_ROOT / row.storage_path
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Call document file missing from storage.")
    return FileResponse(
        path=str(full_path),
        media_type=row.mime_type,
        filename=row.original_filename,
    )


def _require_template_admin(current_user: UserAccount) -> None:
    if current_user.platform_role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super_admin can edit proposal templates.")


def _template_read(item) -> ProposalTemplateRead:
    sections = getattr(item, "sections", [])
    return ProposalTemplateRead(
        id=str(item.id),
        call_library_entry_id=str(item.call_library_entry_id) if item.call_library_entry_id else None,
        name=item.name,
        funding_program=item.funding_program,
        description=item.description,
        is_active=item.is_active,
        sections=[
            {
                "id": str(section.id),
                "template_id": str(section.template_id),
                "key": section.key,
                "title": section.title,
                "guidance": section.guidance,
                "position": section.position,
                "required": section.required,
                "scope_hint": section.scope_hint,
                "created_at": section.created_at,
                "updated_at": section.updated_at,
            }
            for section in sections
        ],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _project_section_read(item) -> ProjectProposalSectionRead:
    return ProjectProposalSectionRead(
        id=str(item.id),
        project_id=str(item.project_id),
        template_section_id=str(item.template_section_id) if item.template_section_id else None,
        key=item.key,
        title=item.title,
        guidance=item.guidance,
        position=item.position,
        required=item.required,
        scope_hint=item.scope_hint,
        status=item.status,
        owner_member_id=str(item.owner_member_id) if item.owner_member_id else None,
        reviewer_member_id=str(item.reviewer_member_id) if item.reviewer_member_id else None,
        due_date=item.due_date,
        notes=item.notes,
        content=item.content,
        has_collab_state=bool(item.yjs_state),
        linked_documents_count=int(getattr(item, "linked_documents_count", 0)),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_call_brief_read(project_id: uuid.UUID, item) -> ProposalCallBriefRead:
    if not item:
        return ProposalCallBriefRead(project_id=str(project_id))
    return ProposalCallBriefRead(
        id=str(item.id),
        project_id=str(item.project_id),
        source_call_id=str(item.source_call_id) if item.source_call_id else None,
        source_version=item.source_version,
        copied_by_user_id=str(item.copied_by_user_id) if item.copied_by_user_id else None,
        copied_at=item.copied_at,
        call_title=item.call_title,
        funder_name=item.funder_name,
        programme_name=item.programme_name,
        reference_code=item.reference_code,
        submission_deadline=item.submission_deadline,
        source_url=item.source_url,
        summary=item.summary,
        eligibility_notes=item.eligibility_notes,
        budget_notes=item.budget_notes,
        scoring_notes=item.scoring_notes,
        requirements_text=item.requirements_text,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_call_library_entry_read(item) -> ProposalCallLibraryEntryRead:
    return ProposalCallLibraryEntryRead(
        id=str(item.id),
        call_title=item.call_title,
        funder_name=item.funder_name,
        programme_name=item.programme_name,
        reference_code=item.reference_code,
        submission_deadline=item.submission_deadline,
        source_url=item.source_url,
        summary=item.summary,
        eligibility_notes=item.eligibility_notes,
        budget_notes=item.budget_notes,
        scoring_notes=item.scoring_notes,
        requirements_text=item.requirements_text,
        version=item.version,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_call_library_document_read(item) -> ProposalCallLibraryDocumentRead:
    return ProposalCallLibraryDocumentRead(
        id=str(item.id),
        library_entry_id=str(item.library_entry_id),
        original_filename=item.original_filename,
        category=item.category,
        status=item.status,
        indexing_status=item.indexing_status,
        mime_type=item.mime_type,
        file_size_bytes=item.file_size_bytes,
        storage_path=item.storage_path,
        extracted_text=item.extracted_text,
        indexed_at=item.indexed_at,
        ingestion_error=item.ingestion_error,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_call_ingest_job_read(item) -> ProposalCallIngestJobRead:
    return ProposalCallIngestJobRead(
        id=str(item.id),
        library_entry_id=str(item.library_entry_id),
        document_id=str(item.document_id),
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        status=item.status,
        stage=item.stage,
        progress_current=item.progress_current,
        progress_total=item.progress_total,
        started_at=item.started_at,
        completed_at=item.completed_at,
        error=item.error,
        stream_text=item.stream_text,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_submission_item_read(item) -> ProposalSubmissionItemRead:
    return ProposalSubmissionItemRead(
        id=str(item.id),
        project_id=str(item.project_id),
        requirement_id=str(item.requirement_id),
        partner_id=str(item.partner_id) if item.partner_id else None,
        assignee_member_id=str(item.assignee_member_id) if item.assignee_member_id else None,
        status=item.status,
        latest_uploaded_document_id=str(item.latest_uploaded_document_id) if item.latest_uploaded_document_id else None,
        submitted_at=item.submitted_at,
        notes=item.notes,
        partner_name=getattr(item, "partner_name", None),
        assignee_name=getattr(item, "assignee_name", None),
        latest_uploaded_document_title=getattr(item, "latest_uploaded_document_title", None),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_submission_requirement_read(item) -> ProposalSubmissionRequirementRead:
    return ProposalSubmissionRequirementRead(
        id=str(item.id),
        project_id=str(item.project_id),
        template_id=str(item.template_id) if item.template_id else None,
        title=item.title,
        description=item.description,
        document_type=item.document_type,
        format_hint=item.format_hint,
        required=item.required,
        position=item.position,
        items=[_proposal_submission_item_read(child) for child in getattr(item, "items", [])],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_review_finding_read(
    item,
    member_name: str | None = None,
    replies: list | None = None,
) -> ProposalReviewFindingRead:
    return ProposalReviewFindingRead(
        id=str(item.id),
        project_id=str(item.project_id),
        proposal_section_id=str(item.proposal_section_id) if item.proposal_section_id else None,
        review_kind=item.review_kind.value if hasattr(item.review_kind, "value") else str(item.review_kind),
        finding_type=item.finding_type.value if hasattr(item.finding_type, "value") else str(item.finding_type),
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        source=item.source.value if hasattr(item.source, "value") else str(item.source),
        scope=item.scope.value if hasattr(item.scope, "value") else str(item.scope),
        summary=item.summary,
        details=item.details,
        anchor_text=item.anchor_text,
        anchor_prefix=item.anchor_prefix,
        anchor_suffix=item.anchor_suffix,
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        parent_finding_id=str(item.parent_finding_id) if item.parent_finding_id else None,
        created_by_display_name=member_name,
        replies=[
            _proposal_review_finding_read(r["finding"], r["member_name"])
            for r in (replies or [])
        ],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _proposal_validation_status(exc: ValidationError) -> int:
    message = str(exc).lower()
    if "insufficient access" in message or "only coordinators" in message or "only update submission items for your partner" in message:
        return status.HTTP_403_FORBIDDEN
    return status.HTTP_400_BAD_REQUEST
