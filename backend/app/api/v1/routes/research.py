"""Research workspace API routes."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.research import BibliographyReference
from app.models.organization import TeamMember
from app.schemas.research import (
    AISummaryRead,
    AISynthesisRead,
    BibliographyBibtexImportRead,
    BibliographyDuplicateCheckPayload,
    BibliographyDuplicateCheckRead,
    BibliographyDuplicateMatchRead,
    BibliographyCollectionBulkResearchLinkPayload,
    BibliographyCollectionBulkTeachingLinkPayload,
    BibliographyCollectionCreate,
    BibliographyCollectionListRead,
    BibliographyCollectionRead,
    BibliographyCollectionReferenceUpsert,
    BibliographyCollectionUpdate,
    BibliographyLinkPayload,
    BibliographyNoteCreate,
    BibliographyNoteListRead,
    BibliographyNoteRead,
    BibliographyNoteUpdate,
    BibliographyReadingStatusRead,
    BibliographyReadingStatusUpdate,
    BibliographyReferenceCreate,
    BibliographyReferenceListRead,
    BibliographyReferenceRead,
    BibliographyReferenceUpdate,
    BibliographyTagListRead,
    BibliographyTagRead,
    BibtexImportPayload,
    BibtexImportRead,
    CollectionCreate,
    CollectionDetailRead,
    CollectionMeetingPayload,
    CollectionMeetingRead,
    CollectionListRead,
    CollectionMemberCreate,
    CollectionMemberRead,
    CollectionMemberUpdate,
    CollectionRead,
    CollectionUpdate,
    NoteCreate,
    NoteListRead,
    NoteRead,
    NoteReferencesPayload,
    NoteUpdate,
    ReferenceCreate,
    ReferenceListRead,
    ReferenceMetadataRead,
    ReferenceMovePayload,
    ReferenceRead,
    ReferenceStatusPayload,
    ReferenceUpdate,
    WbsLinksPayload,
    WbsLinksRead,
)
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.research_service import DuplicateBibliographyError, ResearchService


def require_research_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not current_user.can_access_research:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Research.")


def require_bibliography_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not (current_user.can_access_research or current_user.can_access_teaching):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Bibliography.")


router = APIRouter(dependencies=[Depends(require_research_access)])
bibliography_router = APIRouter(prefix="/bibliography", dependencies=[Depends(require_bibliography_access)])


def _resolve_member_id(db: Session, user: UserAccount, project_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(TeamMember.id).where(
            TeamMember.user_account_id == user.id,
            TeamMember.project_id == project_id,
            TeamMember.is_active.is_(True),
        )
    )


# ══════════════════════════════════════════════════════════════════════
# Collections
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/collections", response_model=CollectionListRead)
def list_collections(
    project_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    member_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CollectionListRead:
    svc = ResearchService(db)
    try:
        items, total = svc.list_collections(
            project_id,
            status_filter=status_filter,
            member_id=uuid.UUID(member_id) if member_id else None,
            page=page,
            page_size=page_size,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CollectionListRead(
        items=[_collection_read(svc, c) for c in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/collections", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    project_id: uuid.UUID,
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> CollectionRead:
    svc = ResearchService(db)
    member_id = _resolve_member_id(db, current_user, project_id)
    try:
        item = svc.create_collection(
            project_id,
            title=payload.title,
            description=payload.description,
            hypothesis=payload.hypothesis,
            open_questions=payload.open_questions,
            status=payload.status,
            tags=payload.tags,
            overleaf_url=payload.overleaf_url,
            target_output_title=payload.target_output_title,
            output_status=payload.output_status,
            created_by_member_id=member_id,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _collection_read(svc, item)


@router.get("/{project_id}/research/collections/{collection_id}", response_model=CollectionDetailRead)
def get_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> CollectionDetailRead:
    svc = ResearchService(db)
    try:
        item = svc.get_collection(project_id, collection_id)
        members_data = svc.list_collection_members(project_id, collection_id)
        wbs = svc.get_wbs_links(project_id, collection_id)
        meetings = svc.list_collection_meetings(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    read = _collection_read(svc, item)
    return CollectionDetailRead(
        **read.model_dump(),
        members=[_member_read(d) for d in members_data],
        wp_ids=wbs["wp_ids"],
        task_ids=wbs["task_ids"],
        deliverable_ids=wbs["deliverable_ids"],
        meetings=[_meeting_read(item) for item in meetings],
    )


@router.put("/{project_id}/research/collections/{collection_id}", response_model=CollectionRead)
def update_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: CollectionUpdate,
    db: Session = Depends(get_db),
) -> CollectionRead:
    svc = ResearchService(db)
    try:
        item = svc.update_collection(
            project_id,
            collection_id,
            title=payload.title,
            description=payload.description,
            hypothesis=payload.hypothesis,
            open_questions=payload.open_questions,
            status=payload.status,
            tags=payload.tags,
            overleaf_url=payload.overleaf_url,
            target_output_title=payload.target_output_title,
            output_status=payload.output_status,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _collection_read(svc, item)


@router.delete("/{project_id}/research/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_collection(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Collection members ────────────────────────────────────────────────


@router.get("/{project_id}/research/collections/{collection_id}/members", response_model=list[CollectionMemberRead])
def list_collection_members(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[CollectionMemberRead]:
    svc = ResearchService(db)
    try:
        members_data = svc.list_collection_members(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_member_read(d) for d in members_data]


@router.post("/{project_id}/research/collections/{collection_id}/members", response_model=CollectionMemberRead, status_code=status.HTTP_201_CREATED)
def add_collection_member(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: CollectionMemberCreate,
    db: Session = Depends(get_db),
) -> CollectionMemberRead:
    svc = ResearchService(db)
    try:
        data = svc.add_collection_member(
            project_id,
            collection_id,
            member_id=uuid.UUID(payload.member_id),
            role=payload.role,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _member_read(data)


@router.put("/{project_id}/research/collections/{collection_id}/members/{member_record_id}", response_model=CollectionMemberRead)
def update_collection_member(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    member_record_id: uuid.UUID,
    payload: CollectionMemberUpdate,
    db: Session = Depends(get_db),
) -> CollectionMemberRead:
    svc = ResearchService(db)
    try:
        data = svc.update_collection_member_role(
            project_id,
            collection_id,
            member_record_id,
            role=payload.role,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _member_read(data)


@router.delete("/{project_id}/research/collections/{collection_id}/members/{member_record_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_collection_member(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    member_record_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc.remove_collection_member(project_id, collection_id, member_record_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── WBS links ─────────────────────────────────────────────────────────


@router.put("/{project_id}/research/collections/{collection_id}/wbs-links", response_model=WbsLinksRead)
def set_wbs_links(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: WbsLinksPayload,
    db: Session = Depends(get_db),
) -> WbsLinksRead:
    svc = ResearchService(db)
    try:
        result = svc.set_wbs_links(
            project_id,
            collection_id,
            wp_ids=payload.wp_ids,
            task_ids=payload.task_ids,
            deliverable_ids=payload.deliverable_ids,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WbsLinksRead(**result)


@router.put("/{project_id}/research/collections/{collection_id}/meetings", response_model=list[CollectionMeetingRead])
def set_collection_meetings(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    payload: CollectionMeetingPayload,
    db: Session = Depends(get_db),
) -> list[CollectionMeetingRead]:
    svc = ResearchService(db)
    try:
        items = svc.set_collection_meetings(
            project_id,
            collection_id,
            meeting_ids=payload.meeting_ids,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return [_meeting_read(item) for item in items]


# ══════════════════════════════════════════════════════════════════════
# References
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/references", response_model=ReferenceListRead)
def list_references(
    project_id: uuid.UUID,
    collection_id: str | None = Query(default=None),
    reading_status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None, alias="q"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ReferenceListRead:
    svc = ResearchService(db)
    try:
        items, total = svc.list_references(
            project_id,
            collection_id=uuid.UUID(collection_id) if collection_id else None,
            reading_status=reading_status,
            tag=tag,
            search=search,
            page=page,
            page_size=page_size,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReferenceListRead(
        items=[_reference_read(svc, r) for r in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/references", response_model=ReferenceRead, status_code=status.HTTP_201_CREATED)
def create_reference(
    project_id: uuid.UUID,
    payload: ReferenceCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ReferenceRead:
    svc = ResearchService(db)
    member_id = _resolve_member_id(db, current_user, project_id)
    try:
        item = svc.create_reference(
            project_id,
            title=payload.title,
            collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            document_key=uuid.UUID(payload.document_key) if payload.document_key else None,
            tags=payload.tags,
            reading_status=payload.reading_status,
            bibliography_visibility=payload.bibliography_visibility,
            added_by_member_id=member_id,
            created_by_user_id=current_user.id,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.post("/{project_id}/research/references/import-bibtex", response_model=BibtexImportRead)
def import_bibtex(
    project_id: uuid.UUID,
    payload: BibtexImportPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibtexImportRead:
    from app.services.bibtex_parser import parse_bibtex

    member_id = _resolve_member_id(db, current_user, project_id)
    entries = parse_bibtex(payload.bibtex)
    if not entries:
        raise HTTPException(status_code=400, detail="No valid BibTeX entries found")

    svc = ResearchService(db)
    created: list[ReferenceRead] = []
    errors: list[str] = []
    collection_id = uuid.UUID(payload.collection_id) if payload.collection_id else None
    for entry in entries:
        try:
            item = svc.create_reference(
                project_id,
                title=entry["title"],
                collection_id=collection_id,
                authors=entry["authors"],
                year=entry["year"],
                venue=entry["venue"],
                doi=entry["doi"],
                url=entry["url"],
                abstract=entry["abstract"],
                bibliography_visibility=payload.visibility,
                added_by_member_id=member_id,
                created_by_user_id=current_user.id,
            )
            created.append(_reference_read(svc, item))
        except Exception as exc:
            errors.append(f"{entry.get('cite_key', '?')}: {exc}")
    return BibtexImportRead(created=created, errors=errors)


@router.get("/{project_id}/research/references/{reference_id}", response_model=ReferenceRead)
def get_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.get_reference(project_id, reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.put("/{project_id}/research/references/{reference_id}", response_model=ReferenceRead)
def update_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    payload: ReferenceUpdate,
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.update_reference(
            project_id,
            reference_id,
            title=payload.title,
            collection_id=payload.collection_id,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            document_key=payload.document_key,
            tags=payload.tags,
            reading_status=payload.reading_status,
            bibliography_visibility=payload.bibliography_visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


# ══════════════════════════════════════════════════════════════════════
# Bibliography
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/bibliography", response_model=BibliographyReferenceListRead)
def list_bibliography(
    project_id: uuid.UUID,
    bibliography_collection_id: str | None = Query(default=None),
    search: str | None = Query(default=None, alias="q"),
    visibility: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceListRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        items, total = svc.list_bibliography(
            current_user.id,
            bibliography_collection_id=uuid.UUID(bibliography_collection_id) if bibliography_collection_id else None,
            search=search,
            visibility=visibility,
            page=page,
            page_size=page_size,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return BibliographyReferenceListRead(
        items=[_bibliography_read(svc, project_id, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/bibliography", response_model=BibliographyReferenceRead, status_code=status.HTTP_201_CREATED)
def create_bibliography_reference(
    project_id: uuid.UUID,
    payload: BibliographyReferenceCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.create_bibliography_reference(
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
            created_by_user_id=current_user.id,
            allow_duplicate=payload.allow_duplicate,
            reuse_existing_id=uuid.UUID(payload.reuse_existing_id) if payload.reuse_existing_id else None,
        )
    except (NotFoundError, ValidationError, DuplicateBibliographyError) as exc:
        if isinstance(exc, DuplicateBibliographyError):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": str(exc),
                    "matches": [
                        {
                            "match_reason": reason,
                            "reference": _bibliography_read_global(svc, item),
                        }
                        for reason, item in exc.matches
                    ],
                },
            ) from exc
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read(svc, project_id, item)


@router.put("/{project_id}/research/bibliography/{bibliography_reference_id}", response_model=BibliographyReferenceRead)
def update_bibliography_reference(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyReferenceUpdate,
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.update_bibliography_reference(
            bibliography_reference_id,
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read(svc, project_id, item)


@router.delete("/{project_id}/research/bibliography/{bibliography_reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bibliography_reference(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        svc.delete_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/research/bibliography/import-bibtex", response_model=BibliographyBibtexImportRead)
def import_bibliography_bibtex(
    project_id: uuid.UUID,
    payload: BibtexImportPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyBibtexImportRead:
    from app.services.bibtex_parser import parse_bibtex

    entries = parse_bibtex(payload.bibtex)
    if not entries:
        raise HTTPException(status_code=400, detail="No valid BibTeX entries found")

    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    created: list[BibliographyReferenceRead] = []
    errors: list[str] = []
    for entry in entries:
        try:
            item = svc.create_bibliography_reference(
                title=entry["title"],
                authors=entry["authors"],
                year=entry["year"],
                venue=entry["venue"],
                doi=entry["doi"],
                url=entry["url"],
                abstract=entry["abstract"],
                bibtex_raw=entry.get("raw") or None,
                visibility=payload.visibility,
                created_by_user_id=current_user.id,
            )
            created.append(_bibliography_read(svc, project_id, item))
        except DuplicateBibliographyError as exc:
            duplicate_titles = ", ".join(item.title for _, item in exc.matches[:2])
            errors.append(f"{entry.get('cite_key', '?')}: duplicate ({duplicate_titles})")
        except Exception as exc:
            errors.append(f"{entry.get('cite_key', '?')}: {exc}")
    return BibliographyBibtexImportRead(created=created, errors=errors)


@router.post("/{project_id}/research/bibliography/link", response_model=ReferenceRead, status_code=status.HTTP_201_CREATED)
def link_bibliography_reference(
    project_id: uuid.UUID,
    payload: BibliographyLinkPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ReferenceRead:
    svc = ResearchService(db)
    member_id = _resolve_member_id(db, current_user, project_id)
    try:
        item = svc.link_bibliography_reference(
            project_id,
            bibliography_reference_id=uuid.UUID(payload.bibliography_reference_id),
            collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
            reading_status=payload.reading_status,
            added_by_member_id=member_id,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.post("/{project_id}/research/bibliography/{bibliography_reference_id}/attachment", response_model=BibliographyReferenceRead)
async def upload_bibliography_attachment(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.attach_bibliography_file(
            project_id,
            bibliography_reference_id,
            file_name=file.filename or "reference.pdf",
            content_type=file.content_type or "application/pdf",
            file_stream=file.file,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await file.close()
    return _bibliography_read(svc, project_id, item)


@router.get("/{project_id}/research/bibliography/{bibliography_reference_id}/file")
def download_bibliography_attachment(
    project_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    svc = ResearchService(db)
    try:
        svc._get_project(project_id)
        item = svc.get_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if item.document_key and item.source_project_id:
        from app.models.document import ProjectDocument

        document = db.scalar(
            select(ProjectDocument)
            .where(
                ProjectDocument.project_id == item.source_project_id,
                ProjectDocument.document_key == item.document_key,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if document and Path(document.storage_uri).exists():
            return FileResponse(
                str(Path(document.storage_uri)),
                media_type=document.mime_type or "application/pdf",
                filename=document.original_filename or item.attachment_filename or "reference.pdf",
            )
    if not item.attachment_path:
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    path = Path(item.attachment_path)
    if not path.is_absolute():
        base = Path(settings.documents_storage_path)
        if not base.is_absolute():
            base = (Path.cwd() / base).resolve()
        path = (base / path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    return FileResponse(
        path,
        media_type=item.attachment_mime_type or "application/pdf",
        filename=item.attachment_filename or path.name,
    )


@bibliography_router.get("/collections", response_model=BibliographyCollectionListRead)
def list_bibliography_collections(
    visibility: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyCollectionListRead:
    svc = ResearchService(db)
    items, total = svc.list_bibliography_collections(current_user.id, visibility=visibility, page=page, page_size=page_size)
    return BibliographyCollectionListRead(
        items=[_bibliography_collection_read(svc, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@bibliography_router.post("/collections", response_model=BibliographyCollectionRead, status_code=status.HTTP_201_CREATED)
def create_bibliography_collection(
    payload: BibliographyCollectionCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyCollectionRead:
    svc = ResearchService(db)
    item = svc.create_bibliography_collection(
        current_user.id,
        title=payload.title,
        description=payload.description,
        visibility=payload.visibility,
    )
    return _bibliography_collection_read(svc, item)


@bibliography_router.put("/collections/{bibliography_collection_id}", response_model=BibliographyCollectionRead)
def update_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyCollectionRead:
    svc = ResearchService(db)
    try:
        item = svc.update_bibliography_collection(
            bibliography_collection_id,
            current_user.id,
            title=payload.title,
            description=payload.description,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _bibliography_collection_read(svc, item)


@bibliography_router.delete("/collections/{bibliography_collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_bibliography_collection(bibliography_collection_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc


@bibliography_router.post("/collections/{bibliography_collection_id}/papers", status_code=status.HTTP_204_NO_CONTENT)
def add_paper_to_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionReferenceUpsert,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.add_reference_to_bibliography_collection(
            bibliography_collection_id,
            uuid.UUID(payload.bibliography_reference_id),
            current_user.id,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc


@bibliography_router.delete("/collections/{bibliography_collection_id}/papers/{bibliography_reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_paper_from_bibliography_collection(
    bibliography_collection_id: uuid.UUID,
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.remove_reference_from_bibliography_collection(
            bibliography_collection_id,
            bibliography_reference_id,
            current_user.id,
        )
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc


@bibliography_router.get("/collections/{bibliography_collection_id}/paper-ids", response_model=list[str])
def list_bibliography_collection_paper_ids(
    bibliography_collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> list[str]:
    svc = ResearchService(db)
    try:
        ids = svc.bibliography_reference_ids_for_collection(bibliography_collection_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return [str(item) for item in ids]


@bibliography_router.post("/collections/{bibliography_collection_id}/link/research")
def bulk_link_bibliography_collection_to_research(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionBulkResearchLinkPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> dict[str, int]:
    svc = ResearchService(db)
    member_id = _resolve_member_id(db, current_user, uuid.UUID(payload.project_id))
    try:
        count = svc.bulk_link_bibliography_collection_to_research(
            bibliography_collection_id,
            project_id=uuid.UUID(payload.project_id),
            collection_id=uuid.UUID(payload.collection_id),
            actor_user_id=current_user.id,
            added_by_member_id=member_id,
            reading_status=payload.reading_status,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return {"linked": count}


@bibliography_router.post("/collections/{bibliography_collection_id}/link/teaching")
def bulk_link_bibliography_collection_to_teaching(
    bibliography_collection_id: uuid.UUID,
    payload: BibliographyCollectionBulkTeachingLinkPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> dict[str, int]:
    svc = ResearchService(db)
    try:
        count = svc.bulk_link_bibliography_collection_to_teaching(
            bibliography_collection_id,
            project_id=uuid.UUID(payload.project_id),
            actor_user_id=current_user.id,
        )
    except (NotFoundError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return {"linked": count}


@bibliography_router.get("", response_model=BibliographyReferenceListRead)
def list_global_bibliography(
    bibliography_collection_id: str | None = Query(default=None),
    search: str | None = Query(default=None, alias="q"),
    visibility: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceListRead:
    svc = ResearchService(db)
    try:
        items, total = svc.list_bibliography(
            current_user.id,
            bibliography_collection_id=uuid.UUID(bibliography_collection_id) if bibliography_collection_id else None,
            search=search,
            visibility=visibility,
            page=page,
            page_size=page_size,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ref_ids = [item.id for item in items]
    note_counts = svc.bibliography_note_counts(ref_ids)
    reading_statuses = svc.get_bibliography_reading_statuses(current_user.id, ref_ids)
    return BibliographyReferenceListRead(
        items=[
            _bibliography_read_global(svc, item, note_counts=note_counts, reading_statuses=reading_statuses)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@bibliography_router.get("/search", response_model=BibliographyReferenceListRead)
def search_global_bibliography_semantic(
    q: str = Query(..., min_length=1),
    visibility: str | None = Query(default=None),
    top_k: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceListRead:
    """Semantic search over bibliography references using vector embeddings."""
    svc = ResearchService(db)
    items = svc.search_bibliography_semantic(current_user.id, q, visibility=visibility, top_k=top_k)
    ref_ids = [item.id for item in items]
    note_counts = svc.bibliography_note_counts(ref_ids)
    reading_statuses = svc.get_bibliography_reading_statuses(current_user.id, ref_ids)
    return BibliographyReferenceListRead(
        items=[
            _bibliography_read_global(svc, item, note_counts=note_counts, reading_statuses=reading_statuses)
            for item in items
        ],
        page=1,
        page_size=top_k,
        total=len(items),
    )


@bibliography_router.post("/embed-backfill")
def bibliography_embed_backfill(
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> dict[str, int]:
    """Backfill embeddings for bibliography references that don't have one yet."""
    svc = ResearchService(db)
    count = svc.embed_bibliography_backfill()
    db.commit()
    return {"embedded": count}


@bibliography_router.get("/tags", response_model=BibliographyTagListRead)
def list_global_bibliography_tags(
    search: str | None = Query(default=None, alias="q"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> BibliographyTagListRead:
    svc = ResearchService(db)
    items, total = svc.list_bibliography_tags(search=search, page=page, page_size=page_size)
    return BibliographyTagListRead(
        items=[
            BibliographyTagRead(
                id=str(item.id),
                label=item.label,
                slug=item.slug,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@bibliography_router.post("", response_model=BibliographyReferenceRead, status_code=status.HTTP_201_CREATED)
def create_global_bibliography_reference(
    payload: BibliographyReferenceCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.create_bibliography_reference(
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
            created_by_user_id=current_user.id,
            allow_duplicate=payload.allow_duplicate,
            reuse_existing_id=uuid.UUID(payload.reuse_existing_id) if payload.reuse_existing_id else None,
        )
    except DuplicateBibliographyError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "matches": [
                    {
                        "match_reason": reason,
                        "reference": _bibliography_read_global(svc, item),
                    }
                    for reason, item in exc.matches
                ],
            },
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.post("/check-duplicates", response_model=BibliographyDuplicateCheckRead)
def check_global_bibliography_duplicates(
    payload: BibliographyDuplicateCheckPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyDuplicateCheckRead:
    svc = ResearchService(db)
    matches = svc.find_bibliography_duplicates(
        created_by_user_id=current_user.id,
        doi=payload.doi,
        title=payload.title,
    )
    return BibliographyDuplicateCheckRead(
        matches=[
            BibliographyDuplicateMatchRead(
                match_reason=reason,
                reference=_bibliography_read_global(svc, item),
            )
            for reason, item in matches
        ]
    )


@bibliography_router.put("/{bibliography_reference_id}", response_model=BibliographyReferenceRead)
def update_global_bibliography_reference(
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyReferenceUpdate,
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.update_bibliography_reference(
            bibliography_reference_id,
            title=payload.title,
            authors=payload.authors,
            year=payload.year,
            venue=payload.venue,
            doi=payload.doi,
            url=payload.url,
            abstract=payload.abstract,
            bibtex_raw=payload.bibtex_raw,
            tags=payload.tags,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_read_global(svc, item)


@bibliography_router.delete("/{bibliography_reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_global_bibliography_reference(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@bibliography_router.post("/import-bibtex", response_model=BibliographyBibtexImportRead)
def import_global_bibliography_bibtex(
    payload: BibtexImportPayload,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyBibtexImportRead:
    from app.services.bibtex_parser import parse_bibtex

    entries = parse_bibtex(payload.bibtex)
    if not entries:
        raise HTTPException(status_code=400, detail="No valid BibTeX entries found")

    svc = ResearchService(db)
    created: list[BibliographyReferenceRead] = []
    errors: list[str] = []
    for entry in entries:
        try:
            item = svc.create_bibliography_reference(
                title=entry["title"],
                authors=entry["authors"],
                year=entry["year"],
                venue=entry["venue"],
                doi=entry["doi"],
                url=entry["url"],
                abstract=entry["abstract"],
                bibtex_raw=entry.get("raw") or None,
                visibility=payload.visibility,
                created_by_user_id=current_user.id,
            )
            created.append(_bibliography_read_global(svc, item))
        except DuplicateBibliographyError as exc:
            duplicate_titles = ", ".join(item.title for _, item in exc.matches[:2])
            errors.append(f"{entry.get('cite_key', '?')}: duplicate ({duplicate_titles})")
        except Exception as exc:
            errors.append(f"{entry.get('cite_key', '?')}: {exc}")
    return BibliographyBibtexImportRead(created=created, errors=errors)


@bibliography_router.post("/{bibliography_reference_id}/attachment", response_model=BibliographyReferenceRead)
async def upload_global_bibliography_attachment(
    bibliography_reference_id: uuid.UUID,
    source_project_id: uuid.UUID = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BibliographyReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.attach_bibliography_file(
            source_project_id,
            bibliography_reference_id,
            file_name=file.filename or "reference.pdf",
            content_type=file.content_type or "application/pdf",
            file_stream=file.file,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    finally:
        await file.close()
    return _bibliography_read_global(svc, item)


@bibliography_router.get("/{bibliography_reference_id}/file")
def download_global_bibliography_attachment(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    svc = ResearchService(db)
    try:
        item = svc.get_bibliography_reference(bibliography_reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if item.document_key and item.source_project_id:
        from app.models.document import ProjectDocument

        document = db.scalar(
            select(ProjectDocument)
            .where(
                ProjectDocument.project_id == item.source_project_id,
                ProjectDocument.document_key == item.document_key,
            )
            .order_by(ProjectDocument.version.desc())
            .limit(1)
        )
        if document and Path(document.storage_uri).exists():
            return FileResponse(
                str(Path(document.storage_uri)),
                media_type=document.mime_type or "application/pdf",
                filename=document.original_filename or item.attachment_filename or "reference.pdf",
            )
    if not item.attachment_path:
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    path = Path(item.attachment_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Bibliography attachment not found.")
    return FileResponse(
        path,
        media_type=item.attachment_mime_type or "application/pdf",
        filename=item.attachment_filename or path.name,
    )


# ── Bibliography notes ─────────────────────────────────────────────


def _bibliography_note_read(note, display_name: str) -> BibliographyNoteRead:
    return BibliographyNoteRead(
        id=str(note.id),
        bibliography_reference_id=str(note.bibliography_reference_id),
        user_id=str(note.user_id),
        user_display_name=display_name,
        content=note.content,
        note_type=note.note_type,
        visibility=note.visibility.value if hasattr(note.visibility, "value") else str(note.visibility),
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@bibliography_router.get("/{bibliography_reference_id}/notes", response_model=BibliographyNoteListRead)
def list_bibliography_notes(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyNoteListRead:
    svc = ResearchService(db)
    rows = svc.list_bibliography_notes(bibliography_reference_id, current_user.id)
    return BibliographyNoteListRead(
        items=[_bibliography_note_read(note, display_name) for note, display_name in rows],
    )


@bibliography_router.post("/{bibliography_reference_id}/notes", response_model=BibliographyNoteRead, status_code=status.HTTP_201_CREATED)
def create_bibliography_note(
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyNoteCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyNoteRead:
    svc = ResearchService(db)
    try:
        item = svc.create_bibliography_note(
            bibliography_reference_id,
            current_user.id,
            content=payload.content,
            note_type=payload.note_type,
            visibility=payload.visibility,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _bibliography_note_read(item, current_user.display_name)


@bibliography_router.put("/notes/{note_id}", response_model=BibliographyNoteRead)
def update_bibliography_note(
    note_id: uuid.UUID,
    payload: BibliographyNoteUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyNoteRead:
    svc = ResearchService(db)
    try:
        item = svc.update_bibliography_note(
            note_id,
            current_user.id,
            content=payload.content,
            note_type=payload.note_type,
            visibility=payload.visibility,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _bibliography_note_read(item, current_user.display_name)


@bibliography_router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bibliography_note(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_bibliography_note(note_id, current_user.id)
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 403
        raise HTTPException(status_code=code, detail=str(exc)) from exc


# ── Bibliography reading status ───────────────────────────────────


@bibliography_router.get("/{bibliography_reference_id}/status", response_model=BibliographyReadingStatusRead)
def get_bibliography_reading_status(
    bibliography_reference_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReadingStatusRead:
    svc = ResearchService(db)
    return BibliographyReadingStatusRead(
        reading_status=svc.get_bibliography_reading_status(bibliography_reference_id, current_user.id),
    )


@bibliography_router.put("/{bibliography_reference_id}/status", response_model=BibliographyReadingStatusRead)
def set_bibliography_reading_status(
    bibliography_reference_id: uuid.UUID,
    payload: BibliographyReadingStatusUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> BibliographyReadingStatusRead:
    svc = ResearchService(db)
    try:
        result = svc.set_bibliography_reading_status(bibliography_reference_id, current_user.id, payload.reading_status)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BibliographyReadingStatusRead(reading_status=result)


@router.delete("/{project_id}/research/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_reference(project_id, reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{project_id}/research/references/{reference_id}/move", response_model=ReferenceRead)
def move_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    payload: ReferenceMovePayload,
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.move_reference(
            project_id,
            reference_id,
            collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _reference_read(svc, item)


@router.put("/{project_id}/research/references/{reference_id}/status", response_model=ReferenceRead)
def update_reference_status(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    payload: ReferenceStatusPayload,
    db: Session = Depends(get_db),
) -> ReferenceRead:
    svc = ResearchService(db)
    try:
        item = svc.update_reference_status(
            project_id,
            reference_id,
            reading_status=payload.reading_status,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


# ══════════════════════════════════════════════════════════════════════
# Notes
# ══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research/notes", response_model=NoteListRead)
def list_notes(
    project_id: uuid.UUID,
    collection_id: str | None = Query(default=None),
    note_type: str | None = Query(default=None),
    author_member_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> NoteListRead:
    svc = ResearchService(db)
    try:
        items, total = svc.list_notes(
            project_id,
            collection_id=uuid.UUID(collection_id) if collection_id else None,
            note_type=note_type,
            author_member_id=uuid.UUID(author_member_id) if author_member_id else None,
            page=page,
            page_size=page_size,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return NoteListRead(
        items=[_note_read(svc, n) for n in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/research/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    project_id: uuid.UUID,
    payload: NoteCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> NoteRead:
    svc = ResearchService(db)
    member_id = _resolve_member_id(db, current_user, project_id)
    try:
        item = svc.create_note(
            project_id,
            title=payload.title,
            content=payload.content,
            collection_id=uuid.UUID(payload.collection_id) if payload.collection_id else None,
            note_type=payload.note_type,
            tags=payload.tags,
            author_member_id=member_id,
            linked_reference_ids=payload.linked_reference_ids,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.get("/{project_id}/research/notes/{note_id}", response_model=NoteRead)
def get_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> NoteRead:
    svc = ResearchService(db)
    try:
        item = svc.get_note(project_id, note_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.put("/{project_id}/research/notes/{note_id}", response_model=NoteRead)
def update_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
) -> NoteRead:
    svc = ResearchService(db)
    try:
        item = svc.update_note(
            project_id,
            note_id,
            title=payload.title,
            content=payload.content,
            collection_id=payload.collection_id,
            note_type=payload.note_type,
            tags=payload.tags,
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _note_read(svc, item)


@router.delete("/{project_id}/research/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    svc = ResearchService(db)
    try:
        svc.delete_note(project_id, note_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{project_id}/research/notes/{note_id}/references", response_model=NoteRead)
def set_note_references(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: NoteReferencesPayload,
    db: Session = Depends(get_db),
) -> NoteRead:
    svc = ResearchService(db)
    try:
        item = svc.set_note_references(
            project_id,
            note_id,
            reference_ids=payload.reference_ids,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _note_read(svc, item)


# ══════════════════════════════════════════════════════════════════════
# AI
# ══════════════════════════════════════════════════════════════════════


@router.post("/{project_id}/research/references/{reference_id}/summarize", response_model=AISummaryRead)
def summarize_reference(
    project_id: uuid.UUID,
    reference_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AISummaryRead:
    from app.services.research_ai_service import ResearchAIService
    svc = ResearchAIService(db)
    try:
        ref = svc.summarize_reference(project_id, reference_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI summarization failed: {exc}") from exc
    return AISummaryRead(ai_summary=ref.ai_summary, ai_summary_at=ref.ai_summary_at)


@router.post("/{project_id}/research/references/extract-from-pdf", response_model=ReferenceMetadataRead)
def extract_metadata_from_pdf(
    project_id: uuid.UUID,
    document_key: str = Query(...),
    db: Session = Depends(get_db),
) -> ReferenceMetadataRead:
    from app.services.research_ai_service import ResearchAIService
    svc = ResearchAIService(db)
    try:
        metadata = svc.extract_metadata_from_pdf(project_id, uuid.UUID(document_key))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Metadata extraction failed: {exc}") from exc
    return ReferenceMetadataRead(**metadata)


@router.post("/{project_id}/research/collections/{collection_id}/synthesize", response_model=AISynthesisRead)
def synthesize_collection(
    project_id: uuid.UUID,
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> AISynthesisRead:
    from app.services.research_ai_service import ResearchAIService
    svc = ResearchAIService(db)
    try:
        col = svc.synthesize_collection(project_id, collection_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI synthesis failed: {exc}") from exc
    return AISynthesisRead(ai_synthesis=col.ai_synthesis, ai_synthesis_at=col.ai_synthesis_at)


# ══════════════════════════════════════════════════════════════════════
# Read helpers
# ══════════════════════════════════════════════════════════════════════


def _collection_read(svc: ResearchService, item) -> CollectionRead:
    return CollectionRead(
        id=str(item.id),
        project_id=str(item.project_id),
        title=item.title,
        description=item.description,
        hypothesis=item.hypothesis,
        open_questions=item.open_questions or [],
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        tags=item.tags or [],
        overleaf_url=item.overleaf_url,
        target_output_title=item.target_output_title,
        output_status=item.output_status.value if hasattr(item.output_status, "value") else str(item.output_status),
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        ai_synthesis=item.ai_synthesis,
        ai_synthesis_at=item.ai_synthesis_at,
        reference_count=svc._reference_count(item.id),
        note_count=svc._note_count(item.id),
        member_count=svc._member_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _member_read(data: dict) -> CollectionMemberRead:
    cm = data["item"]
    return CollectionMemberRead(
        id=str(cm.id),
        member_id=str(cm.member_id),
        member_name=data.get("member_name", ""),
        organization_short_name=data.get("organization_short_name", ""),
        role=cm.role.value if hasattr(cm.role, "value") else str(cm.role),
        created_at=cm.created_at,
        updated_at=cm.updated_at,
    )


def _meeting_read(item) -> CollectionMeetingRead:
    return CollectionMeetingRead(
        id=str(item.id),
        title=item.title,
        starts_at=item.starts_at,
        source_type=item.source_type.value if hasattr(item.source_type, "value") else str(item.source_type),
        summary=item.summary,
    )


def _reference_read(svc: ResearchService, item) -> ReferenceRead:
    bibliography = svc.get_bibliography_reference(item.bibliography_reference_id) if item.bibliography_reference_id else None
    return ReferenceRead(
        id=str(item.id),
        project_id=str(item.project_id),
        bibliography_reference_id=str(item.bibliography_reference_id) if item.bibliography_reference_id else None,
        collection_id=str(item.collection_id) if item.collection_id else None,
        title=item.title,
        authors=item.authors or [],
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        url=item.url,
        abstract=item.abstract,
        document_key=str(item.document_key) if item.document_key else None,
        tags=item.tags or [],
        bibliography_visibility=(
            bibliography.visibility.value if bibliography and hasattr(bibliography.visibility, "value")
            else str(bibliography.visibility) if bibliography and bibliography.visibility
            else None
        ),
        bibliography_attachment_filename=bibliography.attachment_filename if bibliography else None,
        bibliography_attachment_url=(
            f"/projects/{item.project_id}/research/bibliography/{item.bibliography_reference_id}/file"
            if bibliography and bibliography.attachment_path
            else None
        ),
        reading_status=item.reading_status.value if hasattr(item.reading_status, "value") else str(item.reading_status),
        added_by_member_id=str(item.added_by_member_id) if item.added_by_member_id else None,
        ai_summary=item.ai_summary,
        ai_summary_at=item.ai_summary_at,
        note_count=svc._ref_note_count(item.id),
        annotation_count=svc._ref_annotation_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _bibliography_read(svc: ResearchService, project_id: uuid.UUID, item: BibliographyReference) -> BibliographyReferenceRead:
    return BibliographyReferenceRead(
        id=str(item.id),
        source_project_id=str(item.source_project_id) if item.source_project_id else None,
        document_key=str(item.document_key) if item.document_key else None,
        title=item.title,
        authors=item.authors or [],
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        url=item.url,
        abstract=item.abstract,
        bibtex_raw=item.bibtex_raw,
        tags=svc.bibliography_tags_for_reference(item.id),
        visibility=item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility),
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        attachment_filename=item.attachment_filename,
        attachment_url=(
            f"/projects/{project_id}/research/bibliography/{item.id}/file"
            if item.attachment_path
            else None
        ),
        linked_project_count=svc.bibliography_link_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _bibliography_read_global(
    svc: ResearchService,
    item: BibliographyReference,
    *,
    note_counts: dict | None = None,
    reading_statuses: dict | None = None,
) -> BibliographyReferenceRead:
    return BibliographyReferenceRead(
        id=str(item.id),
        source_project_id=str(item.source_project_id) if item.source_project_id else None,
        document_key=str(item.document_key) if item.document_key else None,
        title=item.title,
        authors=item.authors or [],
        year=item.year,
        venue=item.venue,
        doi=item.doi,
        url=item.url,
        abstract=item.abstract,
        bibtex_raw=item.bibtex_raw,
        tags=svc.bibliography_tags_for_reference(item.id),
        visibility=item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility),
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        attachment_filename=item.attachment_filename,
        attachment_url=(f"/bibliography/{item.id}/file" if (item.document_key or item.attachment_path) else None),
        linked_project_count=svc.bibliography_link_count(item.id),
        note_count=note_counts.get(item.id, 0) if note_counts else svc.bibliography_note_count(item.id),
        reading_status=reading_statuses.get(item.id, "unread") if reading_statuses else "unread",
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _bibliography_collection_read(svc: ResearchService, item) -> BibliographyCollectionRead:
    return BibliographyCollectionRead(
        id=str(item.id),
        title=item.title,
        description=item.description,
        visibility=item.visibility.value if hasattr(item.visibility, "value") else str(item.visibility),
        owner_user_id=str(item.owner_user_id),
        reference_count=svc.bibliography_collection_reference_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _note_read(svc: ResearchService, item) -> NoteRead:
    return NoteRead(
        id=str(item.id),
        project_id=str(item.project_id),
        collection_id=str(item.collection_id) if item.collection_id else None,
        author_member_id=str(item.author_member_id) if item.author_member_id else None,
        author_name=svc.get_author_name(item.author_member_id),
        title=item.title,
        content=item.content,
        note_type=item.note_type.value if hasattr(item.note_type, "value") else str(item.note_type),
        tags=item.tags or [],
        linked_reference_ids=svc.get_note_reference_ids(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
