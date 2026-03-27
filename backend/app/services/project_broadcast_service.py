from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.auth import ProjectRole, UserAccount
from app.models.notification import BroadcastSeverity, ProjectBroadcast, ProjectBroadcastRecipient
from app.models.resources import Equipment, EquipmentBooking, Lab, LabStaffAssignment
from app.services.auth_service import AuthService
from app.services.notification_service import NotificationService
from app.services.onboarding_service import ValidationError
from app.services.project_chat_service import ProjectChatService
from app.services.resources_service import ACTIVE_BOOKING_STATUSES, ResourcesService


BROADCAST_AUTHOR_ROLES = {ProjectRole.project_owner.value, ProjectRole.project_manager.value}
BROADCAST_READ_ROLES = {item.value for item in ProjectRole}


class ProjectBroadcastService:
    def __init__(self, db: Session):
        self.db = db
        self.chat_service = ProjectChatService(db)
        self.resources_service = ResourcesService(db)

    def list_broadcasts(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ProjectBroadcast], int]:
        role = self.chat_service._get_user_project_role(project_id, user_id)
        if role not in BROADCAST_READ_ROLES:
            raise ValidationError("Insufficient role to read project broadcasts.")
        stmt = select(ProjectBroadcast).where(ProjectBroadcast.project_id == project_id).order_by(ProjectBroadcast.sent_at.desc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def list_lab_broadcasts(
        self,
        lab_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[ProjectBroadcast], int]:
        self.resources_service.get_lab(lab_id)
        stmt = select(ProjectBroadcast).where(ProjectBroadcast.lab_id == lab_id).order_by(ProjectBroadcast.sent_at.desc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def create_broadcast(
        self,
        project_id: uuid.UUID,
        author_user_id: uuid.UUID,
        *,
        title: str,
        body: str,
        severity: str,
        deliver_telegram: bool,
    ) -> ProjectBroadcast:
        role = self.chat_service._get_user_project_role(project_id, author_user_id)
        if role not in BROADCAST_AUTHOR_ROLES:
            raise ValidationError("Insufficient role to broadcast in this project.")
        normalized_title, normalized_body, normalized_severity = self._validate_broadcast_payload(title, body, severity)

        broadcast = ProjectBroadcast(
            project_id=project_id,
            lab_id=None,
            author_user_id=author_user_id,
            title=normalized_title,
            body=normalized_body,
            severity=normalized_severity,
            deliver_telegram=deliver_telegram,
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(broadcast)
        self.db.commit()
        self.db.refresh(broadcast)

        memberships = AuthService(self.db).list_project_memberships(project_id)
        recipient_ids: list[uuid.UUID] = []
        seen: set[uuid.UUID] = set()
        for membership in memberships:
            if membership.user_id == author_user_id:
                continue
            if membership.user_id in seen:
                continue
            seen.add(membership.user_id)
            recipient_ids.append(membership.user_id)

        self._deliver_broadcast_notifications(
            broadcast,
            recipient_ids,
            normalized_title,
            normalized_body,
            normalized_severity,
            deliver_telegram,
            link_type="project_broadcast",
            project_id=project_id,
            author_user_id=author_user_id,
            scope_label="Project broadcast",
            confirmation_body=f"{normalized_title}\n\n{normalized_body}\n\nSent to {len(recipient_ids)} recipients.",
        )
        self.db.refresh(broadcast)
        return broadcast

    def create_lab_broadcast(
        self,
        lab_id: uuid.UUID,
        author_user_id: uuid.UUID,
        platform_role: str,
        *,
        title: str,
        body: str,
        severity: str,
        deliver_telegram: bool,
    ) -> ProjectBroadcast:
        if not self.resources_service.can_manage_lab(lab_id, author_user_id, platform_role):
            raise ValidationError("Insufficient role to broadcast in this lab.")
        normalized_title, normalized_body, normalized_severity = self._validate_broadcast_payload(title, body, severity)
        broadcast = ProjectBroadcast(
            project_id=None,
            lab_id=lab_id,
            author_user_id=author_user_id,
            title=normalized_title,
            body=normalized_body,
            severity=normalized_severity,
            deliver_telegram=deliver_telegram,
            sent_at=datetime.now(timezone.utc),
        )
        self.db.add(broadcast)
        self.db.commit()
        self.db.refresh(broadcast)

        recipient_ids = self._lab_recipient_ids(lab_id, author_user_id)
        self._deliver_broadcast_notifications(
            broadcast,
            recipient_ids,
            normalized_title,
            normalized_body,
            normalized_severity,
            deliver_telegram,
            link_type="lab_broadcast",
            project_id=None,
            author_user_id=author_user_id,
            scope_label="Lab broadcast",
            confirmation_body=f"{normalized_title}\n\n{normalized_body}\n\nSent to {len(recipient_ids)} recipients.",
        )
        self.db.refresh(broadcast)
        return broadcast

    def recipient_count_by_broadcast(self, broadcast_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not broadcast_ids:
            return {}
        rows = self.db.execute(
            select(ProjectBroadcastRecipient.broadcast_id, func.count(ProjectBroadcastRecipient.id))
            .where(ProjectBroadcastRecipient.broadcast_id.in_(broadcast_ids))
            .group_by(ProjectBroadcastRecipient.broadcast_id)
        ).all()
        return {broadcast_id: int(count) for broadcast_id, count in rows}

    def author_lookup(self, author_ids: list[uuid.UUID]) -> dict[uuid.UUID, UserAccount]:
        if not author_ids:
            return {}
        rows = self.db.scalars(select(UserAccount).where(UserAccount.id.in_(author_ids))).all()
        return {item.id: item for item in rows}

    def _validate_broadcast_payload(self, title: str, body: str, severity: str) -> tuple[str, str, str]:
        normalized_title = title.strip()
        normalized_body = body.strip()
        normalized_severity = (severity or BroadcastSeverity.important.value).strip().lower()
        allowed_severities = {item.value for item in BroadcastSeverity}
        if normalized_severity not in allowed_severities:
            raise ValidationError(f"Invalid severity. Allowed: {', '.join(sorted(allowed_severities))}.")
        if not normalized_title:
            raise ValidationError("Broadcast title is required.")
        if not normalized_body:
            raise ValidationError("Broadcast body is required.")
        return normalized_title, normalized_body, normalized_severity

    def _deliver_broadcast_notifications(
        self,
        broadcast: ProjectBroadcast,
        recipient_ids: list[uuid.UUID],
        title: str,
        body: str,
        severity: str,
        deliver_telegram: bool,
        *,
        link_type: str,
        project_id: uuid.UUID | None,
        author_user_id: uuid.UUID,
        scope_label: str,
        confirmation_body: str,
    ) -> None:
        notification_service = NotificationService(self.db)
        prefix = severity.upper()
        title_text = f"{prefix} {scope_label}"
        rendered_body = f"{title}\n\n{body}"
        for recipient_user_id in recipient_ids:
            notification = notification_service.notify(
                recipient_user_id,
                project_id=project_id,
                title=title_text,
                body=rendered_body,
                link_type=link_type,
                link_id=broadcast.id,
                forward_telegram=deliver_telegram,
            )
            self.db.add(
                ProjectBroadcastRecipient(
                    broadcast_id=broadcast.id,
                    user_id=recipient_user_id,
                    notification_id=notification.id,
                )
            )
        notification_service.notify(
            author_user_id,
            project_id=project_id,
            title=f"{prefix} {scope_label} sent",
            body=confirmation_body,
            link_type=link_type,
            link_id=broadcast.id,
            forward_telegram=deliver_telegram,
        )
        self.db.commit()

    def _lab_recipient_ids(self, lab_id: uuid.UUID, author_user_id: uuid.UUID) -> list[uuid.UUID]:
        from datetime import timedelta

        self.resources_service.get_lab(lab_id)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=90)
        recipient_ids: set[uuid.UUID] = set()

        lab = self.db.get(Lab, lab_id)
        if lab and lab.responsible_user_id:
            recipient_ids.add(lab.responsible_user_id)

        for user_id in self.db.scalars(select(LabStaffAssignment.user_id).where(LabStaffAssignment.lab_id == lab_id)).all():
            recipient_ids.add(user_id)

        for user_id in self.db.scalars(select(Equipment.owner_user_id).where(Equipment.lab_id == lab_id, Equipment.owner_user_id.is_not(None))).all():
            recipient_ids.add(user_id)

        booking_rows = self.db.scalars(
            select(EquipmentBooking.requester_user_id)
            .join(Equipment, Equipment.id == EquipmentBooking.equipment_id)
            .where(
                Equipment.lab_id == lab_id,
                EquipmentBooking.requester_user_id.is_not(None),
                EquipmentBooking.end_at >= window_start,
                EquipmentBooking.status.in_(tuple(ACTIVE_BOOKING_STATUSES | {"completed"})),
            )
        ).all()
        for user_id in booking_rows:
            recipient_ids.add(user_id)

        recipient_ids.discard(author_user_id)
        return sorted(recipient_ids, key=str)
