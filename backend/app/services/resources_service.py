from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import ProjectMembership, ProjectRole, UserAccount
from app.models.project import Project, ProjectKind
from app.models.resources import (
    Equipment,
    EquipmentBlocker,
    EquipmentBooking,
    EquipmentDowntime,
    EquipmentMaterial,
    EquipmentRequirement,
    Lab,
    LabClosure,
    LabStaffAssignment,
)
from app.core.config import settings
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.teaching_service import TeachingService


ACTIVE_BOOKING_STATUSES = {"requested", "approved", "active"}
CLOSED_BOOKING_STATUSES = {"completed", "cancelled", "rejected"}
PROJECT_MANAGE_ROLES = {
    ProjectRole.project_owner.value,
    ProjectRole.project_manager.value,
    ProjectRole.partner_lead.value,
    ProjectRole.partner_member.value,
}


class ResourcesService:
    def __init__(self, db: Session):
        self.db = db

    def list_equipment(
        self,
        *,
        search: str | None,
        category: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Equipment], int]:
        filters = []
        if search:
            token = f"%{search.strip()}%"
            filters.append(
                or_(
                    Equipment.name.ilike(token),
                    Equipment.category.ilike(token),
                    Equipment.location.ilike(token),
                    Equipment.model.ilike(token),
                )
            )
        if category:
            filters.append(Equipment.category == category.strip())
        if status:
            filters.append(Equipment.status == status.strip())
        stmt = select(Equipment)
        count_stmt = select(func.count()).select_from(Equipment)
        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)
        total = int(self.db.scalar(count_stmt) or 0)
        items = self.db.scalars(
            stmt.order_by(Equipment.name.asc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(items), total

    def list_labs(self, *, page: int, page_size: int) -> tuple[list[Lab], int]:
        total = int(self.db.scalar(select(func.count()).select_from(Lab)) or 0)
        items = self.db.scalars(
            select(Lab).order_by(Lab.name.asc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(items), total

    def create_lab(self, **fields) -> Lab:
        responsible_user_id = self._normalize_user_id(fields.get("responsible_user_id")) if fields.get("responsible_user_id") else None
        item = Lab(
            name=fields["name"].strip(),
            building=(fields.get("building") or "").strip() or None,
            room=(fields.get("room") or "").strip() or None,
            notes=fields.get("notes"),
            responsible_user_id=responsible_user_id,
            is_active=bool(fields.get("is_active", True)),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_lab_staff(self, lab_id: uuid.UUID) -> list[LabStaffAssignment]:
        self.get_lab(lab_id)
        return list(
            self.db.scalars(
                select(LabStaffAssignment)
                .where(LabStaffAssignment.lab_id == lab_id)
                .order_by(LabStaffAssignment.role.asc(), LabStaffAssignment.created_at.asc())
            ).all()
        )

    def get_lab_staff_assignment(self, lab_id: uuid.UUID, user_id: uuid.UUID) -> LabStaffAssignment:
        item = self.db.scalar(
            select(LabStaffAssignment).where(
                LabStaffAssignment.lab_id == lab_id,
                LabStaffAssignment.user_id == user_id,
            )
        )
        if not item:
            raise NotFoundError("Lab staff assignment not found.")
        return item

    def add_lab_staff(self, lab_id: uuid.UUID, *, user_id: str | uuid.UUID, role: str = "staff") -> LabStaffAssignment:
        self.get_lab(lab_id)
        normalized_user_id = self._normalize_user_id(user_id)
        normalized_role = self._normalize_lab_staff_role(role)
        assignment = LabStaffAssignment(lab_id=lab_id, user_id=normalized_user_id, role=normalized_role)
        self.db.add(assignment)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("User is already assigned to this lab.") from exc
        self.db.refresh(assignment)
        return assignment

    def remove_lab_staff(self, lab_id: uuid.UUID, user_id: uuid.UUID) -> None:
        item = self.get_lab_staff_assignment(lab_id, user_id)
        self.db.delete(item)
        self.db.commit()

    def update_lab(self, lab_id: uuid.UUID, **fields) -> Lab:
        item = self.get_lab(lab_id)
        if "name" in fields and fields["name"] is not None:
            item.name = fields["name"].strip()
        if "building" in fields:
            item.building = (fields["building"] or "").strip() or None
        if "room" in fields:
            item.room = (fields["room"] or "").strip() or None
        if "notes" in fields:
            item.notes = fields["notes"]
        if "responsible_user_id" in fields:
            item.responsible_user_id = self._normalize_user_id(fields["responsible_user_id"]) if fields["responsible_user_id"] else None
        if "is_active" in fields and fields["is_active"] is not None:
            item.is_active = bool(fields["is_active"])
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_lab(self, lab_id: uuid.UUID) -> None:
        item = self.get_lab(lab_id)
        self.db.delete(item)
        self.db.commit()

    def get_lab(self, lab_id: uuid.UUID) -> Lab:
        item = self.db.scalar(select(Lab).where(Lab.id == lab_id))
        if not item:
            raise NotFoundError("Lab not found.")
        return item

    def list_lab_closures(self, *, lab_id: uuid.UUID | None, page: int, page_size: int) -> tuple[list[LabClosure], int]:
        stmt = select(LabClosure)
        count_stmt = select(func.count()).select_from(LabClosure)
        if lab_id:
            stmt = stmt.where(LabClosure.lab_id == lab_id)
            count_stmt = count_stmt.where(LabClosure.lab_id == lab_id)
        total = int(self.db.scalar(count_stmt) or 0)
        items = self.db.scalars(
            stmt.order_by(LabClosure.start_at.desc(), LabClosure.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(items), total

    def create_lab_closure(self, *, created_by_user_id: uuid.UUID | None, **fields) -> tuple[LabClosure, list[EquipmentBooking]]:
        lab_id = uuid.UUID(fields["lab_id"])
        self.get_lab(lab_id)
        start_at = fields["start_at"]
        end_at = fields["end_at"]
        self._validate_time_window(start_at, end_at)
        item = LabClosure(
            lab_id=lab_id,
            start_at=start_at,
            end_at=end_at,
            reason=(fields.get("reason") or "personnel_unavailable").strip(),
            notes=fields.get("notes"),
            created_by_user_id=created_by_user_id,
            cancelled_booking_count=0,
        )
        self.db.add(item)
        self.db.flush()
        cancelled = self._apply_lab_closure_effects(item, created_by_user_id=created_by_user_id)
        self.db.commit()
        self.db.refresh(item)
        return item, cancelled

    def update_lab_closure(self, closure_id: uuid.UUID, *, updated_by_user_id: uuid.UUID | None, **fields) -> tuple[LabClosure, list[EquipmentBooking]]:
        item = self.get_lab_closure(closure_id)
        self._clear_lab_closure_effects(item.id)
        if "lab_id" in fields and fields["lab_id"] is not None:
            item.lab_id = uuid.UUID(fields["lab_id"])
            self.get_lab(item.lab_id)
        if "start_at" in fields and fields["start_at"] is not None:
            item.start_at = fields["start_at"]
        if "end_at" in fields and fields["end_at"] is not None:
            item.end_at = fields["end_at"]
        self._validate_time_window(item.start_at, item.end_at)
        if "reason" in fields and fields["reason"] is not None:
            item.reason = fields["reason"].strip()
        if "notes" in fields:
            item.notes = fields["notes"]
        cancelled = self._apply_lab_closure_effects(item, created_by_user_id=updated_by_user_id)
        self.db.commit()
        self.db.refresh(item)
        return item, cancelled

    def delete_lab_closure(self, closure_id: uuid.UUID) -> None:
        item = self.get_lab_closure(closure_id)
        self._clear_lab_closure_effects(item.id)
        self.db.delete(item)
        self.db.commit()

    def create_equipment(self, *, created_by_user_id: uuid.UUID | None = None, **fields) -> Equipment:
        lab_id = self._normalize_lab_id(fields.get("lab_id")) if fields.get("lab_id") else None
        owner_user_id = self._normalize_user_id(fields.get("owner_user_id")) if fields.get("owner_user_id") else None
        item = Equipment(
            name=fields["name"].strip(),
            category=(fields.get("category") or "").strip() or None,
            model=(fields.get("model") or "").strip() or None,
            serial_number=(fields.get("serial_number") or "").strip() or None,
            description=fields.get("description"),
            location=(fields.get("location") or "").strip() or None,
            lab_id=lab_id,
            owner_user_id=owner_user_id,
            status=(fields.get("status") or "active").strip(),
            usage_mode=(fields.get("usage_mode") or "exclusive").strip(),
            access_notes=fields.get("access_notes"),
            booking_notes=fields.get("booking_notes"),
            maintenance_notes=fields.get("maintenance_notes"),
            is_active=bool(fields.get("is_active", True)),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_equipment(self, equipment_id: uuid.UUID, **fields) -> Equipment:
        item = self.get_equipment(equipment_id)
        if "name" in fields and fields["name"] is not None:
            item.name = fields["name"].strip()
        if "category" in fields:
            item.category = (fields["category"] or "").strip() or None
        if "model" in fields:
            item.model = (fields["model"] or "").strip() or None
        if "serial_number" in fields:
            item.serial_number = (fields["serial_number"] or "").strip() or None
        if "description" in fields:
            item.description = fields["description"]
        if "location" in fields:
            item.location = (fields["location"] or "").strip() or None
        if "lab_id" in fields:
            item.lab_id = self._normalize_lab_id(fields["lab_id"]) if fields["lab_id"] else None
        if "owner_user_id" in fields:
            item.owner_user_id = self._normalize_user_id(fields["owner_user_id"]) if fields["owner_user_id"] else None
        if "status" in fields and fields["status"] is not None:
            item.status = fields["status"].strip()
        if "usage_mode" in fields and fields["usage_mode"] is not None:
            item.usage_mode = fields["usage_mode"].strip()
        if "access_notes" in fields:
            item.access_notes = fields["access_notes"]
        if "booking_notes" in fields:
            item.booking_notes = fields["booking_notes"]
        if "maintenance_notes" in fields:
            item.maintenance_notes = fields["maintenance_notes"]
        if "is_active" in fields and fields["is_active"] is not None:
            item.is_active = bool(fields["is_active"])
        self._rebuild_equipment_blockers(item.id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_equipment(self, equipment_id: uuid.UUID) -> None:
        item = self.get_equipment(equipment_id)
        self.db.delete(item)
        self.db.commit()

    def list_equipment_materials(
        self, *, equipment_id: uuid.UUID | None, page: int, page_size: int
    ) -> tuple[list[EquipmentMaterial], int]:
        stmt = select(EquipmentMaterial)
        count_stmt = select(func.count()).select_from(EquipmentMaterial)
        if equipment_id:
            stmt = stmt.where(EquipmentMaterial.equipment_id == equipment_id)
            count_stmt = count_stmt.where(EquipmentMaterial.equipment_id == equipment_id)
        total = int(self.db.scalar(count_stmt) or 0)
        items = self.db.scalars(
            stmt.order_by(EquipmentMaterial.created_at.asc(), EquipmentMaterial.title.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def create_equipment_material(self, *, equipment_id: uuid.UUID, **fields) -> EquipmentMaterial:
        self.get_equipment(equipment_id)
        item = EquipmentMaterial(
            equipment_id=equipment_id,
            material_type=(fields.get("material_type") or "manual").strip(),
            title=fields["title"].strip(),
            external_url=(fields.get("external_url") or "").strip() or None,
            notes=fields.get("notes"),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_equipment_material(self, material_id: uuid.UUID, **fields) -> EquipmentMaterial:
        item = self.get_equipment_material(material_id)
        if "material_type" in fields and fields["material_type"] is not None:
            item.material_type = fields["material_type"].strip()
        if "title" in fields and fields["title"] is not None:
            item.title = fields["title"].strip()
        if "external_url" in fields:
            item.external_url = (fields["external_url"] or "").strip() or None
        if "notes" in fields:
            item.notes = fields["notes"]
        self.db.commit()
        self.db.refresh(item)
        return item

    def attach_equipment_material_file(
        self,
        material_id: uuid.UUID,
        *,
        file_name: str,
        content_type: str,
        file_stream: BinaryIO,
    ) -> EquipmentMaterial:
        item = self.get_equipment_material(material_id)
        self._delete_attachment_file(item)
        safe_name = Path(file_name).name or "attachment.bin"
        storage_path = self._equipment_material_storage_path(item.equipment_id, item.id, safe_name)
        self._write_file(file_stream, storage_path)
        item.attachment_path = str(storage_path)
        item.attachment_filename = safe_name
        item.attachment_mime_type = content_type or "application/octet-stream"
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_equipment_material(self, material_id: uuid.UUID) -> None:
        item = self.get_equipment_material(material_id)
        self._delete_attachment_file(item)
        self.db.delete(item)
        self.db.commit()

    def get_equipment(self, equipment_id: uuid.UUID) -> Equipment:
        item = self.db.scalar(select(Equipment).where(Equipment.id == equipment_id))
        if not item:
            raise NotFoundError("Equipment not found.")
        return item

    def get_equipment_material(self, material_id: uuid.UUID) -> EquipmentMaterial:
        item = self.db.scalar(select(EquipmentMaterial).where(EquipmentMaterial.id == material_id))
        if not item:
            raise NotFoundError("Equipment material not found.")
        return item

    @staticmethod
    def _write_file(file_stream: BinaryIO, target_path: Path) -> int:
        total = 0
        with target_path.open("wb") as output:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                total += len(chunk)
        return total

    def _equipment_material_storage_path(self, equipment_id: uuid.UUID, material_id: uuid.UUID, file_name: str) -> Path:
        root = Path(settings.documents_storage_path)
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        target_dir = root / "_resources" / "equipment" / str(equipment_id) / str(material_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / file_name

    @staticmethod
    def _delete_attachment_file(item: EquipmentMaterial) -> None:
        if not item.attachment_path:
            return
        path = Path(item.attachment_path)
        if path.exists():
            path.unlink(missing_ok=True)

    def list_project_requirements(self, project_id: uuid.UUID) -> list[EquipmentRequirement]:
        self._get_project(project_id)
        return list(
            self.db.scalars(
                select(EquipmentRequirement)
                .where(EquipmentRequirement.project_id == project_id)
                .order_by(EquipmentRequirement.created_at.asc())
            ).all()
        )

    def create_requirement(self, project_id: uuid.UUID, *, created_by_user_id: uuid.UUID | None = None, **fields) -> EquipmentRequirement:
        self._get_project(project_id)
        equipment_id = uuid.UUID(fields["equipment_id"])
        self.get_equipment(equipment_id)
        item = EquipmentRequirement(
            project_id=project_id,
            equipment_id=equipment_id,
            priority=(fields.get("priority") or "important").strip(),
            purpose=fields["purpose"].strip(),
            notes=fields.get("notes"),
            created_by_user_id=created_by_user_id,
        )
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Equipment requirement already exists for this project.") from exc
        self.db.refresh(item)
        return item

    def update_requirement(self, project_id: uuid.UUID, requirement_id: uuid.UUID, **fields) -> EquipmentRequirement:
        item = self._get_requirement(project_id, requirement_id)
        if "priority" in fields and fields["priority"] is not None:
            item.priority = fields["priority"].strip()
        if "purpose" in fields and fields["purpose"] is not None:
            item.purpose = fields["purpose"].strip()
        if "notes" in fields:
            item.notes = fields["notes"]
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_requirement(self, project_id: uuid.UUID, requirement_id: uuid.UUID) -> None:
        item = self._get_requirement(project_id, requirement_id)
        self.db.delete(item)
        self.db.commit()

    def list_bookings(
        self,
        *,
        equipment_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EquipmentBooking], int]:
        filters = []
        if equipment_id:
            filters.append(EquipmentBooking.equipment_id == equipment_id)
        if project_id:
            filters.append(EquipmentBooking.project_id == project_id)
        if status:
            filters.append(EquipmentBooking.status == status.strip())
        stmt = select(EquipmentBooking)
        count_stmt = select(func.count()).select_from(EquipmentBooking)
        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)
        total = int(self.db.scalar(count_stmt) or 0)
        items = self.db.scalars(
            stmt.order_by(EquipmentBooking.start_at.asc(), EquipmentBooking.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def list_project_bookings(self, project_id: uuid.UUID) -> list[EquipmentBooking]:
        self._get_project(project_id)
        return list(
            self.db.scalars(
                select(EquipmentBooking)
                .where(EquipmentBooking.project_id == project_id)
                .order_by(EquipmentBooking.start_at.asc(), EquipmentBooking.created_at.asc())
            ).all()
        )

    def create_booking(self, *, requester_user_id: uuid.UUID | None, **fields) -> EquipmentBooking:
        equipment_id = uuid.UUID(fields["equipment_id"])
        project_id = uuid.UUID(fields["project_id"])
        self.get_equipment(equipment_id)
        self._get_project(project_id)
        start_at = fields["start_at"]
        end_at = fields["end_at"]
        self._validate_time_window(start_at, end_at)
        item = EquipmentBooking(
            equipment_id=equipment_id,
            project_id=project_id,
            requester_user_id=requester_user_id,
            start_at=start_at,
            end_at=end_at,
            status="requested",
            purpose=fields["purpose"].strip(),
            notes=fields.get("notes"),
        )
        self.db.add(item)
        self.db.flush()
        self._rebuild_equipment_blockers(equipment_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_booking(self, booking_id: uuid.UUID, **fields) -> EquipmentBooking:
        item = self.get_booking(booking_id)
        previous_equipment_id = item.equipment_id
        if "start_at" in fields and fields["start_at"] is not None:
            item.start_at = fields["start_at"]
        if "end_at" in fields and fields["end_at"] is not None:
            item.end_at = fields["end_at"]
        self._validate_time_window(item.start_at, item.end_at)
        if "purpose" in fields and fields["purpose"] is not None:
            item.purpose = fields["purpose"].strip()
        if "notes" in fields:
            item.notes = fields["notes"]
        if "status" in fields and fields["status"] is not None:
            item.status = fields["status"].strip()
        self._rebuild_equipment_blockers(previous_equipment_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def approve_booking(self, booking_id: uuid.UUID, *, approver_user_id: uuid.UUID, notes: str | None = None) -> EquipmentBooking:
        item = self.get_booking(booking_id)
        item.status = "approved"
        item.approved_by_user_id = approver_user_id
        if notes:
            item.notes = f"{(item.notes or '').strip()}\n\nApproval Notes:\n{notes.strip()}".strip()
        self._rebuild_equipment_blockers(item.equipment_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def reject_booking(self, booking_id: uuid.UUID, *, approver_user_id: uuid.UUID, notes: str | None = None) -> EquipmentBooking:
        item = self.get_booking(booking_id)
        item.status = "rejected"
        item.approved_by_user_id = approver_user_id
        if notes:
            item.notes = f"{(item.notes or '').strip()}\n\nRejection Notes:\n{notes.strip()}".strip()
        self._rebuild_equipment_blockers(item.equipment_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_downtime(
        self,
        *,
        equipment_id: uuid.UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EquipmentDowntime], int]:
        stmt = select(EquipmentDowntime)
        count_stmt = select(func.count()).select_from(EquipmentDowntime)
        if equipment_id:
            stmt = stmt.where(EquipmentDowntime.equipment_id == equipment_id)
            count_stmt = count_stmt.where(EquipmentDowntime.equipment_id == equipment_id)
        total = int(self.db.scalar(count_stmt) or 0)
        items = self.db.scalars(
            stmt.order_by(EquipmentDowntime.start_at.asc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(items), total

    def create_downtime(self, *, created_by_user_id: uuid.UUID | None, **fields) -> EquipmentDowntime:
        equipment_id = uuid.UUID(fields["equipment_id"])
        self.get_equipment(equipment_id)
        start_at = fields["start_at"]
        end_at = fields["end_at"]
        self._validate_time_window(start_at, end_at)
        item = EquipmentDowntime(
            equipment_id=equipment_id,
            start_at=start_at,
            end_at=end_at,
            reason=(fields.get("reason") or "maintenance").strip(),
            notes=fields.get("notes"),
            created_by_user_id=created_by_user_id,
        )
        self.db.add(item)
        self.db.flush()
        self._rebuild_equipment_blockers(equipment_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_downtime(self, downtime_id: uuid.UUID, **fields) -> EquipmentDowntime:
        item = self.get_downtime(downtime_id)
        if "start_at" in fields and fields["start_at"] is not None:
            item.start_at = fields["start_at"]
        if "end_at" in fields and fields["end_at"] is not None:
            item.end_at = fields["end_at"]
        self._validate_time_window(item.start_at, item.end_at)
        if "reason" in fields and fields["reason"] is not None:
            item.reason = fields["reason"].strip()
        if "notes" in fields:
            item.notes = fields["notes"]
        self._rebuild_equipment_blockers(item.equipment_id)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete_downtime(self, downtime_id: uuid.UUID) -> None:
        item = self.get_downtime(downtime_id)
        equipment_id = item.equipment_id
        self.db.delete(item)
        self._rebuild_equipment_blockers(equipment_id)
        self.db.commit()

    def list_conflicts(
        self,
        *,
        equipment_id: uuid.UUID | None,
        project_id: uuid.UUID | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> list[dict[str, object]]:
        bookings = self.db.scalars(select(EquipmentBooking).order_by(EquipmentBooking.start_at.asc())).all()
        equipment_lookup = {str(item.id): item for item in self.db.scalars(select(Equipment)).all()}
        downtime_items = self.db.scalars(select(EquipmentDowntime).order_by(EquipmentDowntime.start_at.asc())).all()
        results: list[dict[str, object]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for booking in bookings:
            equipment = equipment_lookup.get(str(booking.equipment_id))
            if not equipment:
                continue
            if equipment_id and booking.equipment_id != equipment_id:
                continue
            if project_id and booking.project_id != project_id:
                continue
            if start_at and booking.end_at < start_at:
                continue
            if end_at and booking.start_at > end_at:
                continue
            for downtime in downtime_items:
                if downtime.equipment_id != booking.equipment_id:
                    continue
                if self._overlaps(booking.start_at, booking.end_at, downtime.start_at, downtime.end_at):
                    results.append(
                        {
                            "equipment_id": str(equipment.id),
                            "equipment_name": equipment.name,
                            "conflict_type": "downtime",
                            "booking_id": str(booking.id),
                            "conflicting_booking_id": None,
                            "downtime_id": str(downtime.id),
                            "project_id": str(booking.project_id),
                            "conflicting_project_id": None,
                            "start_at": max(booking.start_at, downtime.start_at),
                            "end_at": min(booking.end_at, downtime.end_at),
                            "detail": f"{equipment.name} is unavailable due to {downtime.reason}.",
                        }
                    )
            if equipment.usage_mode != "exclusive" or booking.status not in ACTIVE_BOOKING_STATUSES:
                continue
            for other in bookings:
                if other.id == booking.id or other.equipment_id != booking.equipment_id:
                    continue
                if other.status not in ACTIVE_BOOKING_STATUSES:
                    continue
                if not self._overlaps(booking.start_at, booking.end_at, other.start_at, other.end_at):
                    continue
                key = tuple(sorted((str(booking.id), str(other.id))))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                results.append(
                    {
                        "equipment_id": str(equipment.id),
                        "equipment_name": equipment.name,
                        "conflict_type": "overlap",
                        "booking_id": str(booking.id),
                        "conflicting_booking_id": str(other.id),
                        "downtime_id": None,
                        "project_id": str(booking.project_id),
                        "conflicting_project_id": str(other.project_id),
                        "start_at": max(booking.start_at, other.start_at),
                        "end_at": min(booking.end_at, other.end_at),
                        "detail": f"{equipment.name} has overlapping bookings.",
                    }
                )
        return results

    def get_project_workspace(self, project_id: uuid.UUID) -> dict[str, list]:
        self._get_project(project_id)
        requirements = self.list_project_requirements(project_id)
        bookings = self.list_project_bookings(project_id)
        blockers = list(
            self.db.scalars(
                select(EquipmentBlocker)
                .where(EquipmentBlocker.project_id == project_id)
                .order_by(EquipmentBlocker.status.asc(), EquipmentBlocker.started_at.desc())
            ).all()
        )
        return {"requirements": requirements, "bookings": bookings, "blockers": blockers}

    def get_booking(self, booking_id: uuid.UUID) -> EquipmentBooking:
        item = self.db.scalar(select(EquipmentBooking).where(EquipmentBooking.id == booking_id))
        if not item:
            raise NotFoundError("Equipment booking not found.")
        return item

    def get_downtime(self, downtime_id: uuid.UUID) -> EquipmentDowntime:
        item = self.db.scalar(select(EquipmentDowntime).where(EquipmentDowntime.id == downtime_id))
        if not item:
            raise NotFoundError("Equipment downtime not found.")
        return item

    def get_lab_closure(self, closure_id: uuid.UUID) -> LabClosure:
        item = self.db.scalar(select(LabClosure).where(LabClosure.id == closure_id))
        if not item:
            raise NotFoundError("Lab closure not found.")
        return item

    def can_view_project_resources(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        platform_role: str,
        *,
        can_access_research: bool,
        can_access_teaching: bool,
    ) -> bool:
        if platform_role == "super_admin":
            return True
        project = self._get_project(project_id)
        if project.project_kind == ProjectKind.teaching.value:
            if not can_access_teaching:
                return False
            return TeachingService(self.db).can_manage_project(project_id, user_id, platform_role)
        if not can_access_research:
            return False
        membership = self.db.scalar(
            select(ProjectMembership.role).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
        return membership is not None

    def can_manage_project_resources(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        platform_role: str,
        *,
        can_access_research: bool,
        can_access_teaching: bool,
    ) -> bool:
        if platform_role == "super_admin":
            return True
        project = self._get_project(project_id)
        if project.project_kind == ProjectKind.teaching.value:
            if not can_access_teaching:
                return False
            return TeachingService(self.db).can_manage_project(project_id, user_id, platform_role)
        if not can_access_research:
            return False
        membership = self.db.scalar(
            select(ProjectMembership.role).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == user_id,
            )
        )
        return membership in PROJECT_MANAGE_ROLES

    def can_manage_equipment(self, equipment_id: uuid.UUID, user_id: uuid.UUID, platform_role: str) -> bool:
        if platform_role == "super_admin":
            return True
        equipment = self.get_equipment(equipment_id)
        if equipment.owner_user_id and equipment.owner_user_id == user_id:
            return True
        if equipment.lab_id:
            return self.can_manage_lab_equipment(equipment.lab_id, user_id, platform_role)
        return False

    def can_manage_lab(self, lab_id: uuid.UUID, user_id: uuid.UUID, platform_role: str) -> bool:
        if platform_role == "super_admin":
            return True
        lab = self.get_lab(lab_id)
        if lab.responsible_user_id and lab.responsible_user_id == user_id:
            return True
        return self.db.scalar(
            select(func.count())
            .select_from(LabStaffAssignment)
            .where(
                LabStaffAssignment.lab_id == lab_id,
                LabStaffAssignment.user_id == user_id,
                LabStaffAssignment.role == "manager",
            )
        ) > 0

    def can_manage_lab_staff(self, lab_id: uuid.UUID, user_id: uuid.UUID, platform_role: str) -> bool:
        return self.can_manage_lab(lab_id, user_id, platform_role)

    def can_manage_lab_equipment(self, lab_id: uuid.UUID, user_id: uuid.UUID, platform_role: str) -> bool:
        if platform_role == "super_admin":
            return True
        lab = self.get_lab(lab_id)
        if lab.responsible_user_id and lab.responsible_user_id == user_id:
            return True
        return self.db.scalar(
            select(func.count())
            .select_from(LabStaffAssignment)
            .where(
                LabStaffAssignment.lab_id == lab_id,
                LabStaffAssignment.user_id == user_id,
                LabStaffAssignment.role.in_(("manager", "staff")),
            )
        ) > 0

    def can_access_resources(self, user: UserAccount) -> bool:
        return bool(user.platform_role == "super_admin" or user.can_access_research or user.can_access_teaching)

    def project_resource_summary(self, project_id: uuid.UUID) -> dict[str, object]:
        self._get_project(project_id)
        requirements = self.list_project_requirements(project_id)
        bookings = self.list_project_bookings(project_id)
        blockers = list(
            self.db.scalars(
                select(EquipmentBlocker)
                .where(EquipmentBlocker.project_id == project_id)
                .order_by(EquipmentBlocker.status.asc(), EquipmentBlocker.started_at.desc())
            ).all()
        )
        equipment_ids = {item.equipment_id for item in requirements} | {item.equipment_id for item in bookings}
        equipment_rows = {
            item.id: item
            for item in self.db.scalars(
                select(Equipment).where(Equipment.id.in_(equipment_ids)) if equipment_ids else select(Equipment).where(false())
            ).all()
        }
        downtime_rows = list(
            self.db.scalars(
                select(EquipmentDowntime)
                .where(EquipmentDowntime.equipment_id.in_(equipment_ids))
                .order_by(EquipmentDowntime.start_at.desc())
            ).all()
        ) if equipment_ids else []
        active_statuses = {"requested", "approved", "active"}
        return {
            "counts": {
                "requirements": len(requirements),
                "bookings": len(bookings),
                "active_bookings": len([item for item in bookings if item.status in active_statuses]),
                "open_blockers": len([item for item in blockers if item.status == "open"]),
                "blocker_days": sum(int(item.blocked_days or 0) for item in blockers),
                "downtime_items": len(downtime_rows),
            },
            "requirements": [
                {
                    "equipment_name": equipment_rows.get(item.equipment_id).name if equipment_rows.get(item.equipment_id) else "Equipment",
                    "lab_name": self._equipment_lab_name(equipment_rows.get(item.equipment_id)),
                    "equipment_status": equipment_rows.get(item.equipment_id).status if equipment_rows.get(item.equipment_id) else None,
                    "priority": item.priority,
                    "purpose": item.purpose,
                    "notes": item.notes,
                }
                for item in requirements[:10]
            ],
            "bookings": [
                {
                    "equipment_name": equipment_rows.get(item.equipment_id).name if equipment_rows.get(item.equipment_id) else "Equipment",
                    "lab_name": self._equipment_lab_name(equipment_rows.get(item.equipment_id)),
                    "status": item.status,
                    "purpose": item.purpose,
                    "start_at": item.start_at.isoformat() if item.start_at else None,
                    "end_at": item.end_at.isoformat() if item.end_at else None,
                    "requester_user_id": str(item.requester_user_id) if item.requester_user_id else None,
                }
                for item in bookings[:12]
            ],
            "open_blockers": [
                {
                    "equipment_name": equipment_rows.get(item.equipment_id).name if equipment_rows.get(item.equipment_id) else "Equipment",
                    "lab_name": self._equipment_lab_name(equipment_rows.get(item.equipment_id)),
                    "reason": item.reason,
                    "blocked_days": int(item.blocked_days or 0),
                    "started_at": item.started_at.isoformat() if item.started_at else None,
                }
                for item in blockers
                if item.status == "open"
            ][:10],
            "downtime": [
                {
                    "equipment_name": equipment_rows.get(item.equipment_id).name if equipment_rows.get(item.equipment_id) else "Equipment",
                    "lab_name": self._equipment_lab_name(equipment_rows.get(item.equipment_id)),
                    "reason": item.reason,
                    "start_at": item.start_at.isoformat() if item.start_at else None,
                    "end_at": item.end_at.isoformat() if item.end_at else None,
                }
                for item in downtime_rows[:10]
            ],
        }

    def _rebuild_equipment_blockers(self, equipment_id: uuid.UUID) -> None:
        equipment = self.get_equipment(equipment_id)
        now = datetime.now(timezone.utc)
        bookings = list(
            self.db.scalars(
                select(EquipmentBooking)
                .where(EquipmentBooking.equipment_id == equipment_id)
                .order_by(EquipmentBooking.created_at.asc(), EquipmentBooking.start_at.asc())
            ).all()
        )
        downtimes = list(
            self.db.scalars(
                select(EquipmentDowntime)
                .where(EquipmentDowntime.equipment_id == equipment_id)
                .order_by(EquipmentDowntime.start_at.asc())
            ).all()
        )
        existing = {
            str(item.booking_id): item
            for item in self.db.scalars(
                select(EquipmentBlocker).where(
                    EquipmentBlocker.equipment_id == equipment_id,
                    EquipmentBlocker.booking_id.is_not(None),
                )
            ).all()
        }
        for booking in bookings:
            blocker = existing.get(str(booking.id))
            reason = None
            if booking.status == "requested":
                if equipment.status in {"maintenance", "unavailable", "retired"}:
                    reason = "maintenance"
                elif any(self._overlaps(booking.start_at, booking.end_at, item.start_at, item.end_at) for item in downtimes):
                    reason = "maintenance"
                elif equipment.usage_mode == "exclusive" and any(
                    other.id != booking.id
                    and other.status in {"approved", "active"}
                    and self._overlaps(booking.start_at, booking.end_at, other.start_at, other.end_at)
                    for other in bookings
                ):
                    reason = "fully_booked"
                else:
                    reason = "approval_pending"

            if reason:
                if blocker:
                    blocker.reason = reason
                    blocker.status = "open"
                    blocker.ended_at = None
                    blocker.blocked_days = max(0, (now.date() - blocker.started_at.date()).days)
                else:
                    self.db.add(
                        EquipmentBlocker(
                            project_id=booking.project_id,
                            equipment_id=equipment_id,
                            booking_id=booking.id,
                            started_at=booking.created_at,
                            blocked_days=max(0, (now.date() - booking.created_at.date()).days),
                            reason=reason,
                            status="open",
                        )
                    )
                continue

            if blocker and blocker.status == "open":
                blocker.status = "resolved"
                blocker.ended_at = now
                blocker.blocked_days = max(0, (now.date() - blocker.started_at.date()).days)

    @staticmethod
    def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
        return start_a < end_b and start_b < end_a

    @staticmethod
    def _validate_time_window(start_at: datetime, end_at: datetime) -> None:
        if end_at <= start_at:
            raise ValidationError("end_at must be after start_at.")

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _get_requirement(self, project_id: uuid.UUID, requirement_id: uuid.UUID) -> EquipmentRequirement:
        item = self.db.scalar(
            select(EquipmentRequirement).where(
                EquipmentRequirement.project_id == project_id,
                EquipmentRequirement.id == requirement_id,
            )
        )
        if not item:
            raise NotFoundError("Equipment requirement not found.")
        return item

    def _normalize_user_id(self, value: str | uuid.UUID) -> uuid.UUID:
        user_id = value if isinstance(value, uuid.UUID) else uuid.UUID(value)
        user = self.db.scalar(select(UserAccount).where(UserAccount.id == user_id))
        if not user:
            raise NotFoundError("User not found.")
        return user_id

    def _normalize_lab_id(self, value: str | uuid.UUID) -> uuid.UUID:
        lab_id = value if isinstance(value, uuid.UUID) else uuid.UUID(value)
        self.get_lab(lab_id)
        return lab_id

    @staticmethod
    def _normalize_lab_staff_role(value: str | None) -> str:
        role = (value or "staff").strip().lower()
        if role not in {"manager", "staff"}:
            raise ValidationError("Lab staff role must be `manager` or `staff`.")
        return role

    def _apply_lab_closure_effects(self, closure: LabClosure, *, created_by_user_id: uuid.UUID | None) -> list[EquipmentBooking]:
        lab = self.get_lab(closure.lab_id)
        equipment_rows = list(
            self.db.scalars(select(Equipment).where(Equipment.lab_id == closure.lab_id).order_by(Equipment.name.asc())).all()
        )
        now = datetime.now(timezone.utc)
        cancelled: list[EquipmentBooking] = []
        for equipment in equipment_rows:
            self.db.add(
                EquipmentDowntime(
                    equipment_id=equipment.id,
                    source_lab_closure_id=closure.id,
                    start_at=closure.start_at,
                    end_at=closure.end_at,
                    reason="lab_closed",
                    notes=self._compose_lab_closure_notes(lab, closure.reason, closure.notes),
                    created_by_user_id=created_by_user_id,
                )
            )
            bookings = list(
                self.db.scalars(
                    select(EquipmentBooking).where(
                        EquipmentBooking.equipment_id == equipment.id,
                        EquipmentBooking.status.in_(("requested", "approved")),
                        EquipmentBooking.start_at >= now,
                        EquipmentBooking.start_at < closure.end_at,
                        EquipmentBooking.end_at > closure.start_at,
                    )
                ).all()
            )
            for booking in bookings:
                booking.lab_closure_previous_status = booking.status
                booking.cancelled_by_lab_closure_id = closure.id
                booking.status = "cancelled"
                booking.notes = self._append_note(
                    booking.notes,
                    f"Cancelled automatically because lab {lab.name} is closed from {closure.start_at.isoformat()} to {closure.end_at.isoformat()} ({closure.reason}).",
                )
                cancelled.append(booking)
            self._rebuild_equipment_blockers(equipment.id)
        closure.cancelled_booking_count = len(cancelled)
        return cancelled

    def _clear_lab_closure_effects(self, closure_id: uuid.UUID) -> None:
        closure = self.get_lab_closure(closure_id)
        equipment_ids = list(
            self.db.scalars(select(Equipment.id).where(Equipment.lab_id == closure.lab_id)).all()
        )
        downtime_rows = list(
            self.db.scalars(select(EquipmentDowntime).where(EquipmentDowntime.source_lab_closure_id == closure_id)).all()
        )
        if equipment_ids:
            legacy_rows = list(
                self.db.scalars(
                    select(EquipmentDowntime).where(
                        EquipmentDowntime.source_lab_closure_id.is_(None),
                        EquipmentDowntime.equipment_id.in_(equipment_ids),
                        EquipmentDowntime.reason == "lab_closed",
                        EquipmentDowntime.start_at == closure.start_at,
                        EquipmentDowntime.end_at == closure.end_at,
                    )
                ).all()
            )
            seen = {item.id for item in downtime_rows}
            downtime_rows.extend([item for item in legacy_rows if item.id not in seen])
        restored_bookings = list(
            self.db.scalars(select(EquipmentBooking).where(EquipmentBooking.cancelled_by_lab_closure_id == closure_id)).all()
        )
        affected_equipment_ids = {item.equipment_id for item in downtime_rows} | {item.equipment_id for item in restored_bookings}
        for item in downtime_rows:
            self.db.delete(item)
        for booking in restored_bookings:
            if booking.status == "cancelled":
                booking.status = booking.lab_closure_previous_status or "requested"
            booking.cancelled_by_lab_closure_id = None
            booking.lab_closure_previous_status = None
        for equipment_id in affected_equipment_ids:
            self._rebuild_equipment_blockers(equipment_id)

    def lab_equipment_count(self, lab_id: uuid.UUID) -> int:
        return int(self.db.scalar(select(func.count()).select_from(Equipment).where(Equipment.lab_id == lab_id)) or 0)

    @staticmethod
    def _append_note(existing: str | None, addition: str) -> str:
        base = (existing or "").strip()
        return f"{base}\n\n{addition}".strip() if base else addition

    @staticmethod
    def _compose_lab_closure_notes(lab: Lab, reason: str, notes: str | None) -> str:
        base = f"Lab {lab.name} closed: {reason}."
        if notes and notes.strip():
            return f"{base}\n\n{notes.strip()}"
        return base

    def _equipment_lab_name(self, equipment: Equipment | None) -> str | None:
        if not equipment or not equipment.lab_id:
            return None
        lab = self.db.scalar(select(Lab).where(Lab.id == equipment.lab_id))
        return lab.name if lab else None
