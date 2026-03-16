from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.agents.meeting_action_extraction_agent import MeetingActionExtractionAgent
from app.models.action_item import ActionItemPriority, ActionItemSource, ActionItemStatus, MeetingActionItem
from app.models.meeting import MeetingRecord
from app.models.organization import TeamMember
from app.models.project import Project
from app.models.work import Task, WorkExecutionStatus, WorkPackage
from app.schemas.action_item import ActionItemCreate, ActionItemUpdate
from app.schemas.work import AssignmentPayload, TaskCreate
from app.services.onboarding_service import NotFoundError, OnboardingService, ValidationError
from app.services.project_chat_service import ProjectChatService

import logging

logger = logging.getLogger(__name__)


class ActionItemService:
    def __init__(self, db: Session):
        self.db = db

    def list_action_items(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        status_filter: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[MeetingActionItem], int]:
        self._get_meeting(project_id, meeting_id)
        stmt = select(MeetingActionItem).where(
            MeetingActionItem.project_id == project_id,
            MeetingActionItem.meeting_id == meeting_id,
        )
        if status_filter:
            stmt = stmt.where(MeetingActionItem.status == self._normalize_status(status_filter))
        stmt = stmt.order_by(MeetingActionItem.sort_order.asc(), MeetingActionItem.created_at.asc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(items), total

    def create_action_item(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        payload: ActionItemCreate,
    ) -> MeetingActionItem:
        self._get_meeting(project_id, meeting_id)
        description = payload.description.strip()
        if not description:
            raise ValidationError("Action item description cannot be empty.")
        assignee_member = self._validate_member(project_id, payload.assignee_member_id)
        item = MeetingActionItem(
            project_id=project_id,
            meeting_id=meeting_id,
            description=description,
            assignee_name=(payload.assignee_name or "").strip() or (assignee_member.full_name if assignee_member else None),
            assignee_member_id=assignee_member.id if assignee_member else None,
            due_date=payload.due_date,
            priority=self._normalize_priority(payload.priority),
            source=self._normalize_source(payload.source),
            sort_order=self._next_sort_order(project_id, meeting_id),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_action_item(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: ActionItemUpdate,
    ) -> MeetingActionItem:
        item = self._get_item(project_id, meeting_id, item_id)
        update_data = payload.model_dump(exclude_unset=True)
        if "description" in update_data and update_data["description"] is not None:
            description = str(update_data["description"]).strip()
            if not description:
                raise ValidationError("Action item description cannot be empty.")
            item.description = description
        if "assignee_member_id" in update_data:
            member = self._validate_member(project_id, update_data["assignee_member_id"])
            item.assignee_member_id = member.id if member else None
            if member and not (update_data.get("assignee_name") or "").strip():
                item.assignee_name = member.full_name
        if "assignee_name" in update_data:
            item.assignee_name = str(update_data["assignee_name"] or "").strip() or None
        if "due_date" in update_data:
            item.due_date = update_data["due_date"]
        if "priority" in update_data and update_data["priority"] is not None:
            item.priority = self._normalize_priority(update_data["priority"])
        if "status" in update_data and update_data["status"] is not None:
            item.status = self._normalize_status(update_data["status"])
        self.db.commit()
        self.db.refresh(item)
        return item

    def bulk_create(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        items: list[dict],
        source: str | ActionItemSource,
    ) -> list[MeetingActionItem]:
        self._get_meeting(project_id, meeting_id)
        normalized_source = self._normalize_source(source)
        if normalized_source == ActionItemSource.assistant:
            self.db.execute(
                delete(MeetingActionItem).where(
                    MeetingActionItem.project_id == project_id,
                    MeetingActionItem.meeting_id == meeting_id,
                    MeetingActionItem.source == ActionItemSource.assistant,
                )
            )
        start_order = self._next_sort_order(project_id, meeting_id)
        created: list[MeetingActionItem] = []
        for offset, raw in enumerate(items):
            description = str(raw.get("description") or "").strip()
            if not description:
                continue
            assignee_name = str(raw.get("assignee_name") or "").strip() or None
            due_date_value = raw.get("due_date")
            if isinstance(due_date_value, str) and due_date_value.strip():
                try:
                    due_date_value = date.fromisoformat(due_date_value.strip())
                except ValueError:
                    due_date_value = None
            elif not isinstance(due_date_value, date):
                due_date_value = None
            item = MeetingActionItem(
                project_id=project_id,
                meeting_id=meeting_id,
                description=description,
                assignee_name=assignee_name,
                due_date=due_date_value,
                priority=self._normalize_priority(raw.get("priority", "normal")),
                status=ActionItemStatus.pending,
                source=normalized_source,
                sort_order=start_order + offset,
            )
            self.db.add(item)
            created.append(item)
        self.db.commit()
        for item in created:
            self.db.refresh(item)

        # Notify meeting creator about AI extraction
        if normalized_source == ActionItemSource.assistant and created:
            try:
                from app.services.notification_service import NotificationService
                meeting = self.db.get(MeetingRecord, meeting_id)
                if meeting and meeting.created_by_member_id:
                    member = self.db.get(TeamMember, meeting.created_by_member_id)
                    if member and member.user_account_id:
                        NotificationService(self.db).notify(
                            user_id=member.user_account_id,
                            project_id=project_id,
                            title=f"AI extracted {len(created)} action items from {meeting.title}",
                            body="Review the extracted action items in the meeting details.",
                            link_type="meeting",
                            link_id=meeting_id,
                        )
            except Exception:
                logger.warning("Failed to send bulk-create notification", exc_info=True)

        return created

    def promote_to_task(
        self,
        project_id: uuid.UUID,
        meeting_id: uuid.UUID,
        item_id: uuid.UUID,
        wp_id: uuid.UUID,
    ) -> MeetingActionItem:
        item = self._get_item(project_id, meeting_id, item_id)
        if item.linked_task_id:
            return item
        project = self._get_project(project_id)
        wp = self.db.scalar(
            select(WorkPackage).where(
                WorkPackage.project_id == project_id,
                WorkPackage.id == wp_id,
                WorkPackage.is_trashed.is_(False),
            )
        )
        if not wp:
            raise NotFoundError("Work package not found in project.")
        responsible_person_id = item.assignee_member_id or wp.responsible_person_id
        member = self._validate_member(project_id, responsible_person_id)
        leader_organization_id = member.organization_id if member else wp.leader_organization_id
        start_month = min(max(self._current_project_month(project), wp.start_month), wp.end_month)
        due_month = self._project_month_for_due_date(project, item.due_date) if item.due_date else None
        end_month = min(max(due_month or start_month, start_month), wp.end_month)
        task = OnboardingService(self.db).create_task(
            project_id,
            TaskCreate(
                wp_id=wp.id,
                code=self._next_task_code(project_id, wp.code),
                title=self._task_title(item.description),
                description=item.description,
                start_month=start_month,
                end_month=end_month,
                execution_status=WorkExecutionStatus.in_progress.value,
                assignment=AssignmentPayload(
                    leader_organization_id=leader_organization_id,
                    responsible_person_id=responsible_person_id,
                    collaborating_partner_ids=[],
                ),
            ),
        )
        item.linked_task_id = task.id
        item.status = ActionItemStatus.in_progress
        self.db.commit()
        self.db.refresh(item)

        # Notify assignee about promotion
        try:
            from app.services.notification_service import NotificationService
            if item.assignee_member_id:
                member = self.db.get(TeamMember, item.assignee_member_id)
                if member and member.user_account_id:
                    NotificationService(self.db).notify(
                        user_id=member.user_account_id,
                        project_id=project_id,
                        title=f"Action item promoted to task {task.code}",
                        body=item.description[:200],
                        link_type="task",
                        link_id=task.id,
                    )
        except Exception:
            logger.warning("Failed to send promote-to-task notification", exc_info=True)

        return item

    def extract_action_items(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> tuple[MeetingRecord, list[MeetingActionItem]]:
        meeting = self._get_meeting(project_id, meeting_id)
        result = self._extract_from_content(project_id, meeting.content_text)
        if result is None:
            raise ValidationError("Meeting action extraction failed.")
        meeting.summary = result.get("summary")
        items = self.bulk_create(project_id, meeting_id, result.get("action_items", []), ActionItemSource.assistant)
        self.db.refresh(meeting)
        return meeting, items

    def _extract_from_content(self, project_id: uuid.UUID, content_text: str) -> dict | None:
        context = ProjectChatService(self.db).project_context_for_agent(project_id)
        return MeetingActionExtractionAgent().extract(meeting_content=content_text, project_context=context)

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _get_meeting(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> MeetingRecord:
        self._get_project(project_id)
        meeting = self.db.scalar(
            select(MeetingRecord).where(MeetingRecord.project_id == project_id, MeetingRecord.id == meeting_id)
        )
        if not meeting:
            raise NotFoundError("Meeting not found in project.")
        return meeting

    def _get_item(self, project_id: uuid.UUID, meeting_id: uuid.UUID, item_id: uuid.UUID) -> MeetingActionItem:
        self._get_meeting(project_id, meeting_id)
        item = self.db.scalar(
            select(MeetingActionItem).where(
                MeetingActionItem.project_id == project_id,
                MeetingActionItem.meeting_id == meeting_id,
                MeetingActionItem.id == item_id,
            )
        )
        if not item:
            raise NotFoundError("Action item not found in meeting.")
        return item

    def _validate_member(self, project_id: uuid.UUID, member_id: str | uuid.UUID | None) -> TeamMember | None:
        if not member_id:
            return None
        if isinstance(member_id, str):
            try:
                member_id = uuid.UUID(member_id)
            except ValueError as exc:
                raise ValidationError("Assignee member id is invalid.") from exc
        member = self.db.scalar(select(TeamMember).where(TeamMember.project_id == project_id, TeamMember.id == member_id))
        if not member:
            raise ValidationError("Assignee is not part of the project.")
        return member

    def _normalize_priority(self, value: str | ActionItemPriority) -> ActionItemPriority:
        try:
            return ActionItemPriority(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Priority must be low, normal, high, or urgent.") from exc

    def _normalize_status(self, value: str | ActionItemStatus) -> ActionItemStatus:
        try:
            return ActionItemStatus(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Status must be pending, in_progress, done, or dismissed.") from exc

    def _normalize_source(self, value: str | ActionItemSource) -> ActionItemSource:
        try:
            return ActionItemSource(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError("Source must be manual or assistant.") from exc

    def _next_sort_order(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> int:
        return int(
            self.db.scalar(
                select(func.coalesce(func.max(MeetingActionItem.sort_order) + 1, 0)).where(
                    MeetingActionItem.project_id == project_id,
                    MeetingActionItem.meeting_id == meeting_id,
                )
            )
            or 0
        )

    def _current_project_month(self, project: Project) -> int:
        today = date.today()
        months = (today.year - project.start_date.year) * 12 + (today.month - project.start_date.month) + 1
        return max(1, min(months, project.duration_months))

    def _project_month_for_due_date(self, project: Project, due_date: date) -> int:
        months = (due_date.year - project.start_date.year) * 12 + (due_date.month - project.start_date.month) + 1
        return max(1, min(months, project.duration_months))

    def _next_task_code(self, project_id: uuid.UUID, wp_code: str) -> str:
        prefix = f"{wp_code}-AI-"
        existing = self.db.scalars(
            select(Task.code).where(Task.project_id == project_id, Task.code.ilike(f"{prefix}%")).order_by(Task.code.asc())
        ).all()
        taken = set(existing)
        index = 1
        while f"{prefix}{index}" in taken:
            index += 1
        return f"{prefix}{index}"

    def _task_title(self, description: str) -> str:
        compact = " ".join(description.split())
        return compact[:255] or "Meeting follow-up"
