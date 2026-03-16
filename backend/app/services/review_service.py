import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import ProjectDocument
from app.models.organization import TeamMember
from app.models.review import DeliverableReviewFinding, ReviewFindingSource, ReviewFindingStatus, ReviewFindingType
from app.models.work import Deliverable
from app.schemas.review import ReviewFindingCreate, ReviewFindingUpdate
from app.services.onboarding_service import NotFoundError, ValidationError


class ReviewService:
    def __init__(self, db: Session):
        self.db = db

    def list_findings(self, project_id: uuid.UUID, deliverable_id: uuid.UUID, page: int, page_size: int) -> tuple[list[DeliverableReviewFinding], int]:
        self._get_deliverable(project_id, deliverable_id)
        stmt = select(DeliverableReviewFinding).where(
            DeliverableReviewFinding.project_id == project_id,
            DeliverableReviewFinding.deliverable_id == deliverable_id,
        ).order_by(DeliverableReviewFinding.created_at.desc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def create_finding(self, project_id: uuid.UUID, deliverable_id: uuid.UUID, payload: ReviewFindingCreate) -> DeliverableReviewFinding:
        self._get_deliverable(project_id, deliverable_id)
        self._validate_document(project_id, deliverable_id, payload.document_id)
        self._validate_member(project_id, payload.created_by_member_id)
        finding = DeliverableReviewFinding(
            project_id=project_id,
            deliverable_id=deliverable_id,
            document_id=payload.document_id,
            finding_type=self._normalize_finding_type(payload.finding_type),
            status=self._normalize_status(payload.status),
            source=self._normalize_source(payload.source),
            section_ref=(payload.section_ref or "").strip() or None,
            summary=payload.summary.strip(),
            details=(payload.details or "").strip() or None,
            created_by_member_id=payload.created_by_member_id,
        )
        self.db.add(finding)
        self.db.commit()
        self.db.refresh(finding)
        return finding

    def update_finding(self, project_id: uuid.UUID, deliverable_id: uuid.UUID, finding_id: uuid.UUID, payload: ReviewFindingUpdate) -> DeliverableReviewFinding:
        self._get_deliverable(project_id, deliverable_id)
        finding = self.db.scalar(select(DeliverableReviewFinding).where(
            DeliverableReviewFinding.project_id == project_id,
            DeliverableReviewFinding.deliverable_id == deliverable_id,
            DeliverableReviewFinding.id == finding_id,
        ))
        if not finding:
            raise NotFoundError("Review finding not found.")
        self._validate_document(project_id, deliverable_id, payload.document_id)
        finding.document_id = payload.document_id
        finding.finding_type = self._normalize_finding_type(payload.finding_type)
        finding.status = self._normalize_status(payload.status)
        finding.source = self._normalize_source(payload.source)
        finding.section_ref = (payload.section_ref or "").strip() or None
        finding.summary = payload.summary.strip()
        finding.details = (payload.details or "").strip() or None
        self.db.commit()
        self.db.refresh(finding)
        return finding

    def _get_deliverable(self, project_id: uuid.UUID, deliverable_id: uuid.UUID) -> Deliverable:
        deliverable = self.db.scalar(select(Deliverable).where(Deliverable.project_id == project_id, Deliverable.id == deliverable_id))
        if not deliverable:
            raise NotFoundError("Deliverable not found in project.")
        return deliverable

    def _validate_document(self, project_id: uuid.UUID, deliverable_id: uuid.UUID, document_id: uuid.UUID | None) -> None:
        if not document_id:
            return
        doc = self.db.scalar(select(ProjectDocument).where(ProjectDocument.project_id == project_id, ProjectDocument.id == document_id))
        if not doc or doc.deliverable_id != deliverable_id:
            raise ValidationError("Selected draft document is not linked to this deliverable.")

    def _validate_member(self, project_id: uuid.UUID, member_id: uuid.UUID | None) -> None:
        if not member_id:
            return
        member = self.db.scalar(select(TeamMember).where(TeamMember.project_id == project_id, TeamMember.id == member_id))
        if not member:
            raise ValidationError("Selected member is not part of the project.")

    @staticmethod
    def _normalize_finding_type(value: str) -> ReviewFindingType:
        try:
            return ReviewFindingType(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Finding type must be `issue`, `warning`, or `strength`.") from exc

    @staticmethod
    def _normalize_status(value: str) -> ReviewFindingStatus:
        try:
            return ReviewFindingStatus(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Finding status must be `open` or `resolved`.") from exc

    @staticmethod
    def _normalize_source(value: str) -> ReviewFindingSource:
        try:
            return ReviewFindingSource(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Finding source must be `manual` or `assistant`.") from exc
