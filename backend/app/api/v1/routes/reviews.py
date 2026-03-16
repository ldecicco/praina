import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.review import ReviewFindingCreate, ReviewFindingListRead, ReviewFindingRead, ReviewFindingUpdate
from app.services.onboarding_service import NotFoundError, ValidationError
from app.services.review_service import ReviewService

router = APIRouter()


@router.get("/{project_id}/deliverables/{deliverable_id}/review-findings", response_model=ReviewFindingListRead)
def list_findings(
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ReviewFindingListRead:
    service = ReviewService(db)
    try:
        items, total = service.list_findings(project_id, deliverable_id, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ReviewFindingListRead(items=[_read(item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/{project_id}/deliverables/{deliverable_id}/review-findings", response_model=ReviewFindingRead)
def create_finding(project_id: uuid.UUID, deliverable_id: uuid.UUID, payload: ReviewFindingCreate, db: Session = Depends(get_db)) -> ReviewFindingRead:
    service = ReviewService(db)
    try:
        item = service.create_finding(project_id, deliverable_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _read(item)


@router.patch("/{project_id}/deliverables/{deliverable_id}/review-findings/{finding_id}", response_model=ReviewFindingRead)
def update_finding(project_id: uuid.UUID, deliverable_id: uuid.UUID, finding_id: uuid.UUID, payload: ReviewFindingUpdate, db: Session = Depends(get_db)) -> ReviewFindingRead:
    service = ReviewService(db)
    try:
        item = service.update_finding(project_id, deliverable_id, finding_id, payload)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _read(item)


def _read(item) -> ReviewFindingRead:
    return ReviewFindingRead(
        id=str(item.id),
        project_id=str(item.project_id),
        deliverable_id=str(item.deliverable_id),
        document_id=str(item.document_id) if item.document_id else None,
        finding_type=item.finding_type.value if hasattr(item.finding_type, 'value') else str(item.finding_type),
        status=item.status.value if hasattr(item.status, 'value') else str(item.status),
        source=item.source.value if hasattr(item.source, 'value') else str(item.source),
        section_ref=item.section_ref,
        summary=item.summary,
        details=item.details,
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
