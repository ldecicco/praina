import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.meeting import MeetingRecord, MeetingSourceType
from app.models.organization import TeamMember
from app.models.project import Project
from app.schemas.meeting import MeetingRecordCreate, MeetingRecordUpdate
from app.services.meeting_ingestion_service import MeetingIngestionService
from app.services.onboarding_service import NotFoundError, ValidationError

import logging

logger = logging.getLogger(__name__)


class MeetingService:
    def __init__(self, db: Session):
        self.db = db

    def list_meetings(
        self,
        project_id: uuid.UUID,
        search: str | None,
        source_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[MeetingRecord], int]:
        self._get_project(project_id)
        stmt = select(MeetingRecord).where(MeetingRecord.project_id == project_id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(MeetingRecord.title.ilike(like), MeetingRecord.content_text.ilike(like)))
        if source_type:
            stmt = stmt.where(MeetingRecord.source_type == self._normalize_source_type(source_type))
        stmt = stmt.order_by(MeetingRecord.starts_at.desc(), MeetingRecord.created_at.desc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def create_meeting(self, project_id: uuid.UUID, payload: MeetingRecordCreate) -> MeetingRecord:
        self._get_project(project_id)
        self._validate_content(payload.content_text)
        self._validate_member(project_id, payload.created_by_member_id)
        record = MeetingRecord(
            project_id=project_id,
            title=payload.title.strip(),
            starts_at=payload.starts_at,
            source_type=self._normalize_source_type(payload.source_type),
            source_url=(payload.source_url or "").strip() or None,
            participants_json=[item.strip() for item in payload.participants if item.strip()],
            content_text=payload.content_text.strip(),
            linked_document_id=payload.linked_document_id,
            created_by_member_id=payload.created_by_member_id,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        MeetingIngestionService(self.db).index_meeting(record)

        # Notify project members about new meeting
        try:
            from app.services.notification_service import NotificationService
            creator_name = "Someone"
            creator_user_id = None
            if payload.created_by_member_id:
                member = self.db.get(TeamMember, payload.created_by_member_id)
                if member:
                    creator_name = member.full_name
                    creator_user_id = member.user_account_id
            NotificationService(self.db).notify_project_members(
                project_id,
                title=f"{creator_name} added meeting: {record.title}",
                body=f"Meeting on {record.starts_at.strftime('%Y-%m-%d') if record.starts_at else 'N/A'}",
                link_type="meeting",
                link_id=record.id,
                exclude_user_id=creator_user_id,
            )
        except Exception:
            logger.warning("Failed to send meeting creation notification", exc_info=True)

        return record

    def update_meeting(self, project_id: uuid.UUID, meeting_id: uuid.UUID, payload: MeetingRecordUpdate) -> MeetingRecord:
        self._get_project(project_id)
        record = self.db.scalar(select(MeetingRecord).where(MeetingRecord.project_id == project_id, MeetingRecord.id == meeting_id))
        if not record:
            raise NotFoundError("Meeting not found in project.")
        self._validate_content(payload.content_text)
        record.title = payload.title.strip()
        record.starts_at = payload.starts_at
        record.source_type = self._normalize_source_type(payload.source_type)
        record.source_url = (payload.source_url or "").strip() or None
        record.participants_json = [item.strip() for item in payload.participants if item.strip()]
        content_changed = record.content_text != payload.content_text.strip()
        record.content_text = payload.content_text.strip()
        record.linked_document_id = payload.linked_document_id
        self.db.commit()
        self.db.refresh(record)
        if content_changed:
            MeetingIngestionService(self.db).index_meeting(record)
        return record

    def delete_meeting(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> None:
        self._get_project(project_id)
        record = self.db.scalar(select(MeetingRecord).where(MeetingRecord.project_id == project_id, MeetingRecord.id == meeting_id))
        if not record:
            raise NotFoundError("Meeting not found in project.")
        self.db.delete(record)
        self.db.commit()

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    @staticmethod
    def _normalize_source_type(value: str) -> MeetingSourceType:
        try:
            return MeetingSourceType(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Meeting source type must be `minutes` or `transcript`.") from exc

    @staticmethod
    def _validate_content(content_text: str) -> None:
        if not content_text.strip():
            raise ValidationError("Meeting content cannot be empty.")

    def _validate_member(self, project_id: uuid.UUID, member_id: uuid.UUID | None) -> None:
        if not member_id:
            return
        member = self.db.scalar(select(TeamMember).where(TeamMember.project_id == project_id, TeamMember.id == member_id))
        if not member:
            raise ValidationError("Meeting owner is not part of the project.")
