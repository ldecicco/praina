"""Research workspace API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.organization import TeamMember
from app.schemas.research import (
    AISummaryRead,
    AISynthesisRead,
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
from app.services.research_service import ResearchService


def require_research_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not current_user.can_access_research:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Research.")


router = APIRouter(dependencies=[Depends(require_research_access)])


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
            added_by_member_id=member_id,
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
                added_by_member_id=member_id,
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
        )
    except (NotFoundError, ValidationError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _reference_read(svc, item)


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
    return ReferenceRead(
        id=str(item.id),
        project_id=str(item.project_id),
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
        reading_status=item.reading_status.value if hasattr(item.reading_status, "value") else str(item.reading_status),
        added_by_member_id=str(item.added_by_member_id) if item.added_by_member_id else None,
        ai_summary=item.ai_summary,
        ai_summary_at=item.ai_summary_at,
        note_count=svc._ref_note_count(item.id),
        annotation_count=svc._ref_annotation_count(item.id),
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
