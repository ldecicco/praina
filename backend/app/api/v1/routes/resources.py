from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.auth import UserAccount
from app.models.project import Project
from app.models.resources import Equipment, EquipmentBlocker, EquipmentBooking, EquipmentDowntime, EquipmentMaterial, EquipmentRequirement, Lab, LabClosure, LabStaffAssignment
from app.schemas.resources import (
    EquipmentBlockerRead,
    EquipmentBookingCreate,
    EquipmentBookingDecision,
    EquipmentBookingListRead,
    EquipmentBookingRead,
    EquipmentBookingUpdate,
    EquipmentConflictRead,
    EquipmentCreate,
    EquipmentDowntimeCreate,
    EquipmentDowntimeListRead,
    EquipmentDowntimeRead,
    EquipmentDowntimeUpdate,
    EquipmentListRead,
    EquipmentMaterialCreate,
    EquipmentMaterialListRead,
    EquipmentMaterialRead,
    EquipmentMaterialUpdate,
    EquipmentRead,
    EquipmentRequirementCreate,
    EquipmentRequirementListRead,
    EquipmentRequirementRead,
    EquipmentRequirementUpdate,
    EquipmentUpdate,
    LabClosureCreate,
    LabClosureListRead,
    LabClosureRead,
    LabCreate,
    LabListRead,
    LabStaffCreate,
    LabStaffRead,
    LabRead,
    LabUpdate,
    ProjectBroadcastCreateRequest,
    ProjectBroadcastListRead,
    ProjectBroadcastRead,
    ProjectResourcesWorkspaceRead,
    ResourceOwnerRead,
)
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.notification_service import NotificationService
from app.services.project_broadcast_service import ProjectBroadcastService
from app.services.resources_service import ResourcesService


def require_resources_access(current_user: UserAccount = Depends(get_current_user)) -> None:
    if not (current_user.platform_role == "super_admin" or current_user.can_access_research or current_user.can_access_teaching):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot access Resources.")


router = APIRouter(dependencies=[Depends(require_resources_access)])


@router.get("/resources/equipment", response_model=EquipmentListRead)
def list_equipment(
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentListRead:
    svc = ResourcesService(db)
    items, total = svc.list_equipment(search=search, category=category, status=status_value, page=page, page_size=page_size)
    return EquipmentListRead(items=[_equipment_read(db, item) for item in items], page=page, page_size=page_size, total=total)


@router.get("/resources/labs", response_model=LabListRead)
def list_labs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabListRead:
    svc = ResourcesService(db)
    items, total = svc.list_labs(page=page, page_size=page_size)
    return LabListRead(items=[_lab_read(db, svc, item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/resources/labs", response_model=LabRead, status_code=status.HTTP_201_CREATED)
def create_lab(
    payload: LabCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabRead:
    _require_super_admin(current_user)
    svc = ResourcesService(db)
    try:
        item = svc.create_lab(**payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _lab_read(db, svc, item)


@router.post("/resources/labs/{lab_id}/staff", response_model=LabRead)
def add_lab_staff(
    lab_id: uuid.UUID,
    payload: LabStaffCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabRead:
    svc = ResourcesService(db)
    _require_lab_staff_manager(svc, lab_id, current_user)
    if current_user.platform_role != "super_admin" and (payload.role or "staff").strip().lower() == "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super_admin can assign lab managers.")
    try:
        svc.add_lab_staff(lab_id, user_id=payload.user_id, role=payload.role)
    except (NotFoundError, ValidationError, ConflictError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _lab_read(db, svc, svc.get_lab(lab_id))


@router.delete("/resources/labs/{lab_id}/staff/{user_id}", response_model=LabRead)
def remove_lab_staff(
    lab_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabRead:
    svc = ResourcesService(db)
    _require_lab_staff_manager(svc, lab_id, current_user)
    try:
        assignment = svc.get_lab_staff_assignment(lab_id, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if current_user.platform_role != "super_admin" and assignment.role == "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super_admin can remove lab managers.")
    try:
        svc.remove_lab_staff(lab_id, user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _lab_read(db, svc, svc.get_lab(lab_id))


@router.patch("/resources/labs/{lab_id}", response_model=LabRead)
def update_lab(
    lab_id: uuid.UUID,
    payload: LabUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabRead:
    svc = ResourcesService(db)
    _require_lab_manager(svc, lab_id, current_user)
    try:
        item = svc.update_lab(lab_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _lab_read(db, svc, item)


@router.delete("/resources/labs/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab(
    lab_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    _require_super_admin(current_user)
    svc = ResourcesService(db)
    try:
        svc.delete_lab(lab_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/resources/lab-closures", response_model=LabClosureListRead)
def list_lab_closures(
    lab_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabClosureListRead:
    svc = ResourcesService(db)
    items, total = svc.list_lab_closures(lab_id=lab_id, page=page, page_size=page_size)
    return LabClosureListRead(items=[_lab_closure_read(db, svc, item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/resources/lab-closures", response_model=LabClosureRead, status_code=status.HTTP_201_CREATED)
def create_lab_closure(
    payload: LabClosureCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabClosureRead:
    svc = ResourcesService(db)
    _require_lab_closure_manager(svc, uuid.UUID(payload.lab_id), current_user)
    try:
        item, cancelled_bookings = svc.create_lab_closure(created_by_user_id=current_user.id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    for booking in cancelled_bookings:
        equipment = db.get(Equipment, booking.equipment_id)
        lab = db.get(Lab, equipment.lab_id) if equipment and equipment.lab_id else None
        _notify_booking_cancelled(
            db,
            booking,
            actor_user_id=current_user.id,
            reason_prefix="Lab Closed",
            body_override=f"{equipment.name if equipment else 'Equipment'} was cancelled because {lab.name if lab else 'the lab'} is closed." if equipment else None,
        )
    return _lab_closure_read(db, svc, item)


@router.patch("/resources/lab-closures/{closure_id}", response_model=LabClosureRead)
def update_lab_closure(
    closure_id: uuid.UUID,
    payload: LabClosureCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> LabClosureRead:
    svc = ResourcesService(db)
    try:
        current = svc.get_lab_closure(closure_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    target_lab_id = uuid.UUID(payload.lab_id)
    _require_lab_closure_manager(svc, current.lab_id, current_user)
    if target_lab_id != current.lab_id:
        _require_lab_closure_manager(svc, target_lab_id, current_user)
    try:
        item, cancelled_bookings = svc.update_lab_closure(closure_id, updated_by_user_id=current_user.id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    for booking in cancelled_bookings:
        equipment = db.get(Equipment, booking.equipment_id)
        lab = db.get(Lab, equipment.lab_id) if equipment and equipment.lab_id else None
        _notify_booking_cancelled(
            db,
            booking,
            actor_user_id=current_user.id,
            reason_prefix="Lab Closed",
            body_override=f"{equipment.name if equipment else 'Equipment'} was cancelled because {lab.name if lab else 'the lab'} is closed." if equipment else None,
        )
    return _lab_closure_read(db, svc, item)


@router.delete("/resources/lab-closures/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab_closure(
    closure_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResourcesService(db)
    try:
        item = svc.get_lab_closure(closure_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_lab_closure_manager(svc, item.lab_id, current_user)
    svc.delete_lab_closure(closure_id)


@router.get("/resources/labs/{lab_id}/broadcasts", response_model=ProjectBroadcastListRead)
def list_lab_broadcasts(
    lab_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ProjectBroadcastListRead:
    service = ProjectBroadcastService(db)
    try:
        items, total = service.list_lab_broadcasts(lab_id, page, page_size)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    broadcast_ids = [item.id for item in items]
    author_ids = [item.author_user_id for item in items]
    recipient_counts = service.recipient_count_by_broadcast(broadcast_ids)
    authors = service.author_lookup(author_ids)
    return ProjectBroadcastListRead(
        items=[_broadcast_read(item, authors, recipient_counts) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/resources/labs/{lab_id}/broadcasts", response_model=ProjectBroadcastRead)
def create_lab_broadcast(
    lab_id: uuid.UUID,
    payload: ProjectBroadcastCreateRequest,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ProjectBroadcastRead:
    service = ProjectBroadcastService(db)
    try:
        item = service.create_lab_broadcast(
            lab_id,
            current_user.id,
            current_user.platform_role,
            title=payload.title,
            body=payload.body,
            severity=payload.severity,
            deliver_telegram=payload.deliver_telegram,
        )
    except (NotFoundError, ValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    recipient_counts = service.recipient_count_by_broadcast([item.id])
    authors = service.author_lookup([item.author_user_id])
    return _broadcast_read(item, authors, recipient_counts)


@router.post("/resources/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentRead:
    svc = ResourcesService(db)
    lab_id = uuid.UUID(payload.lab_id) if payload.lab_id else None
    _require_equipment_create_manager(svc, lab_id, current_user)
    try:
        item = svc.create_equipment(created_by_user_id=current_user.id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _equipment_read(db, item)


@router.patch("/resources/equipment/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: uuid.UUID,
    payload: EquipmentUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentRead:
    svc = ResourcesService(db)
    _require_equipment_manager(svc, equipment_id, current_user)
    patch = payload.model_dump(exclude_unset=True)
    if "lab_id" in patch and patch["lab_id"]:
        _require_equipment_create_manager(svc, uuid.UUID(patch["lab_id"]), current_user)
    try:
        item = svc.update_equipment(equipment_id, **patch)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _equipment_read(db, item)


@router.delete("/resources/equipment/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment(
    equipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResourcesService(db)
    try:
        _require_equipment_manager(svc, equipment_id, current_user)
        svc.delete_equipment(equipment_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/resources/equipment-materials", response_model=EquipmentMaterialListRead)
def list_equipment_materials(
    equipment_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentMaterialListRead:
    svc = ResourcesService(db)
    items, total = svc.list_equipment_materials(equipment_id=equipment_id, page=page, page_size=page_size)
    return EquipmentMaterialListRead(
        items=[_equipment_material_read(item) for item in items], page=page, page_size=page_size, total=total
    )


@router.post("/resources/equipment-materials", response_model=EquipmentMaterialRead, status_code=status.HTTP_201_CREATED)
def create_equipment_material(
    payload: EquipmentMaterialCreate,
    equipment_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentMaterialRead:
    svc = ResourcesService(db)
    _require_equipment_manager(svc, equipment_id, current_user)
    try:
        item = svc.create_equipment_material(equipment_id=equipment_id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _equipment_material_read(item)


@router.patch("/resources/equipment-materials/{material_id}", response_model=EquipmentMaterialRead)
def update_equipment_material(
    material_id: uuid.UUID,
    payload: EquipmentMaterialUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentMaterialRead:
    svc = ResourcesService(db)
    try:
        item = svc.get_equipment_material(material_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, item.equipment_id, current_user)
    try:
        item = svc.update_equipment_material(material_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _equipment_material_read(item)


@router.post("/resources/equipment-materials/{material_id}/attachment", response_model=EquipmentMaterialRead)
def upload_equipment_material_attachment(
    material_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentMaterialRead:
    svc = ResourcesService(db)
    try:
        item = svc.get_equipment_material(material_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, item.equipment_id, current_user)
    try:
        item = svc.attach_equipment_material_file(
            material_id,
            file_name=file.filename or "attachment.bin",
            content_type=file.content_type or "application/octet-stream",
            file_stream=file.file,
        )
    finally:
        file.file.close()
    return _equipment_material_read(item)


@router.get("/resources/equipment-materials/{material_id}/file")
def get_equipment_material_attachment(
    material_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> FileResponse:
    svc = ResourcesService(db)
    try:
        item = svc.get_equipment_material(material_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not item.attachment_path:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    full_path = Path(item.attachment_path)
    if not full_path.is_absolute():
        root = Path(settings.documents_storage_path)
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        full_path = root / item.attachment_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found.")
    return FileResponse(str(full_path), filename=item.attachment_filename or full_path.name, media_type=item.attachment_mime_type)


@router.delete("/resources/equipment-materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment_material(
    material_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResourcesService(db)
    try:
        item = svc.get_equipment_material(material_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, item.equipment_id, current_user)
    svc.delete_equipment_material(material_id)


@router.get("/resources/bookings", response_model=EquipmentBookingListRead)
def list_bookings(
    equipment_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentBookingListRead:
    svc = ResourcesService(db)
    items, total = svc.list_bookings(equipment_id=equipment_id, project_id=project_id, status=status_value, page=page, page_size=page_size)
    return EquipmentBookingListRead(items=[_booking_read(db, item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/resources/bookings", response_model=EquipmentBookingRead, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: EquipmentBookingCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentBookingRead:
    svc = ResourcesService(db)
    _require_project_resource_manager(svc, uuid.UUID(payload.project_id), current_user)
    try:
        item = svc.create_booking(requester_user_id=current_user.id, **payload.model_dump())
    except (NotFoundError, ValidationError, ConflictError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    _notify_booking_created(db, item, actor_user_id=current_user.id)
    return _booking_read(db, item)


@router.patch("/resources/bookings/{booking_id}", response_model=EquipmentBookingRead)
def update_booking(
    booking_id: uuid.UUID,
    payload: EquipmentBookingUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentBookingRead:
    svc = ResourcesService(db)
    try:
        booking = svc.get_booking(booking_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_project_resource_manager(svc, booking.project_id, current_user)
    patch = payload.model_dump(exclude_unset=True)
    if "status" in patch:
        next_status = str(patch["status"] or "").strip().lower()
        if next_status not in {"cancelled", "completed"}:
            raise HTTPException(status_code=400, detail="Status updates here only allow `cancelled` or `completed`.")
        if booking.status in {"cancelled", "completed", "rejected"}:
            raise HTTPException(status_code=400, detail="Closed bookings cannot be changed.")
        if next_status == "completed" and booking.status not in {"approved", "active"}:
            raise HTTPException(status_code=400, detail="Only approved or active bookings can be completed.")
    elif booking.status in {"cancelled", "completed", "rejected"}:
        raise HTTPException(status_code=400, detail="Closed bookings cannot be edited.")
    try:
        item = svc.update_booking(booking_id, **patch)
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    if patch.get("status") == "cancelled":
        _notify_booking_cancelled(db, item, actor_user_id=current_user.id)
    return _booking_read(db, item)


@router.post("/resources/bookings/{booking_id}/approve", response_model=EquipmentBookingRead)
def approve_booking(
    booking_id: uuid.UUID,
    payload: EquipmentBookingDecision,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentBookingRead:
    svc = ResourcesService(db)
    try:
        booking = svc.get_booking(booking_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, booking.equipment_id, current_user)
    if booking.status != "requested":
        raise HTTPException(status_code=400, detail="Only requested bookings can be approved.")
    item = svc.approve_booking(booking_id, approver_user_id=current_user.id, notes=payload.notes)
    _notify_booking_approved(db, item, actor_user_id=current_user.id)
    return _booking_read(db, item)


@router.post("/resources/bookings/{booking_id}/reject", response_model=EquipmentBookingRead)
def reject_booking(
    booking_id: uuid.UUID,
    payload: EquipmentBookingDecision,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentBookingRead:
    svc = ResourcesService(db)
    try:
        booking = svc.get_booking(booking_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, booking.equipment_id, current_user)
    if booking.status != "requested":
        raise HTTPException(status_code=400, detail="Only requested bookings can be rejected.")
    item = svc.reject_booking(booking_id, approver_user_id=current_user.id, notes=payload.notes)
    _notify_booking_rejected(db, item, actor_user_id=current_user.id)
    return _booking_read(db, item)


@router.get("/resources/downtime", response_model=EquipmentDowntimeListRead)
def list_downtime(
    equipment_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentDowntimeListRead:
    svc = ResourcesService(db)
    items, total = svc.list_downtime(equipment_id=equipment_id, page=page, page_size=page_size)
    return EquipmentDowntimeListRead(items=[_downtime_read(db, item) for item in items], page=page, page_size=page_size, total=total)


@router.post("/resources/downtime", response_model=EquipmentDowntimeRead, status_code=status.HTTP_201_CREATED)
def create_downtime(
    payload: EquipmentDowntimeCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentDowntimeRead:
    svc = ResourcesService(db)
    _require_equipment_manager(svc, uuid.UUID(payload.equipment_id), current_user)
    try:
        item = svc.create_downtime(created_by_user_id=current_user.id, **payload.model_dump())
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _downtime_read(db, item)


@router.patch("/resources/downtime/{downtime_id}", response_model=EquipmentDowntimeRead)
def update_downtime(
    downtime_id: uuid.UUID,
    payload: EquipmentDowntimeUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentDowntimeRead:
    svc = ResourcesService(db)
    try:
        downtime = svc.get_downtime(downtime_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, downtime.equipment_id, current_user)
    try:
        item = svc.update_downtime(downtime_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _downtime_read(db, item)


@router.delete("/resources/downtime/{downtime_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_downtime(
    downtime_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResourcesService(db)
    try:
        downtime = svc.get_downtime(downtime_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_equipment_manager(svc, downtime.equipment_id, current_user)
    svc.delete_downtime(downtime_id)


@router.get("/resources/conflicts", response_model=list[EquipmentConflictRead])
def list_conflicts(
    equipment_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> list[EquipmentConflictRead]:
    svc = ResourcesService(db)
    rows = svc.list_conflicts(equipment_id=equipment_id, project_id=project_id, start_at=start_at, end_at=end_at)
    return [EquipmentConflictRead(**row) for row in rows]


@router.get("/projects/{project_id}/resources", response_model=ProjectResourcesWorkspaceRead)
def get_project_resources(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> ProjectResourcesWorkspaceRead:
    svc = ResourcesService(db)
    _require_project_resource_viewer(svc, project_id, current_user)
    workspace = svc.get_project_workspace(project_id)
    return ProjectResourcesWorkspaceRead(
        requirements=[_requirement_read(db, item) for item in workspace["requirements"]],
        bookings=[_booking_read(db, item) for item in workspace["bookings"]],
        blockers=[_blocker_read(db, item) for item in workspace["blockers"]],
    )


@router.get("/projects/{project_id}/resources/requirements", response_model=EquipmentRequirementListRead)
def list_project_requirements(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentRequirementListRead:
    svc = ResourcesService(db)
    _require_project_resource_viewer(svc, project_id, current_user)
    items = svc.list_project_requirements(project_id)
    return EquipmentRequirementListRead(items=[_requirement_read(db, item) for item in items], page=1, page_size=max(1, len(items)), total=len(items))


@router.post("/projects/{project_id}/resources/requirements", response_model=EquipmentRequirementRead, status_code=status.HTTP_201_CREATED)
def create_project_requirement(
    project_id: uuid.UUID,
    payload: EquipmentRequirementCreate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentRequirementRead:
    svc = ResourcesService(db)
    _require_project_resource_manager(svc, project_id, current_user)
    try:
        item = svc.create_requirement(project_id, created_by_user_id=current_user.id, **payload.model_dump())
    except (NotFoundError, ValidationError, ConflictError) as exc:
        code = 404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return _requirement_read(db, item)


@router.patch("/projects/{project_id}/resources/requirements/{requirement_id}", response_model=EquipmentRequirementRead)
def update_project_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: EquipmentRequirementUpdate,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> EquipmentRequirementRead:
    svc = ResourcesService(db)
    _require_project_resource_manager(svc, project_id, current_user)
    try:
        item = svc.update_requirement(project_id, requirement_id, **payload.model_dump(exclude_unset=True))
    except (NotFoundError, ValidationError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc)) from exc
    return _requirement_read(db, item)


@router.delete("/projects/{project_id}/resources/requirements/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_requirement(
    project_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
) -> None:
    svc = ResourcesService(db)
    _require_project_resource_manager(svc, project_id, current_user)
    try:
        svc.delete_requirement(project_id, requirement_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_super_admin(current_user: UserAccount) -> None:
    if current_user.platform_role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super_admin can manage equipment inventory.")


def _require_lab_manager(svc: ResourcesService, lab_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_manage_lab(lab_id, current_user.id, current_user.platform_role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only lab managers can manage this lab.")


def _require_lab_staff_manager(svc: ResourcesService, lab_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_manage_lab_staff(lab_id, current_user.id, current_user.platform_role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only lab managers can manage lab staff.")


def _require_lab_closure_manager(svc: ResourcesService, lab_id: uuid.UUID, current_user: UserAccount) -> None:
    _require_lab_manager(svc, lab_id, current_user)


def _require_equipment_create_manager(svc: ResourcesService, lab_id: uuid.UUID | None, current_user: UserAccount) -> None:
    if current_user.platform_role == "super_admin":
        return
    if not lab_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super_admin can create unassigned equipment.")
    try:
        allowed = svc.can_manage_lab_equipment(lab_id, current_user.id, current_user.platform_role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only lab staff can manage equipment in this lab.")


def _require_equipment_manager(svc: ResourcesService, equipment_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_manage_equipment(equipment_id, current_user.id, current_user.platform_role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the equipment owner or lab staff can manage this equipment.")


def _require_project_resource_viewer(svc: ResourcesService, project_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_view_project_resources(
            project_id,
            current_user.id,
            current_user.platform_role,
            can_access_research=current_user.can_access_research,
            can_access_teaching=current_user.can_access_teaching,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot access resources for this project.")


def _require_project_resource_manager(svc: ResourcesService, project_id: uuid.UUID, current_user: UserAccount) -> None:
    try:
        allowed = svc.can_manage_project_resources(
            project_id,
            current_user.id,
            current_user.platform_role,
            can_access_research=current_user.can_access_research,
            can_access_teaching=current_user.can_access_teaching,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot manage resources for this project.")


def _user_read(user: UserAccount | None) -> ResourceOwnerRead | None:
    if not user:
        return None
    return ResourceOwnerRead(user_id=str(user.id), display_name=user.display_name, email=user.email)


def _equipment_read(db: Session, item: Equipment) -> EquipmentRead:
    owner = db.get(UserAccount, item.owner_user_id) if item.owner_user_id else None
    lab = db.get(Lab, item.lab_id) if item.lab_id else None
    svc = ResourcesService(db)
    return EquipmentRead(
        id=str(item.id),
        name=item.name,
        category=item.category,
        model=item.model,
        serial_number=item.serial_number,
        description=item.description,
        location=item.location,
        lab_id=str(item.lab_id) if item.lab_id else None,
        lab=_lab_read(db, svc, lab) if lab else None,
        owner_user_id=str(item.owner_user_id) if item.owner_user_id else None,
        owner=_user_read(owner),
        status=item.status,
        usage_mode=item.usage_mode,
        access_notes=item.access_notes,
        booking_notes=item.booking_notes,
        maintenance_notes=item.maintenance_notes,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _lab_read(db: Session, svc: ResourcesService, item: Lab) -> LabRead:
    responsible = db.get(UserAccount, item.responsible_user_id) if item.responsible_user_id else None
    staff = svc.list_lab_staff(item.id)
    return LabRead(
        id=str(item.id),
        name=item.name,
        building=item.building,
        room=item.room,
        notes=item.notes,
        responsible_user_id=str(item.responsible_user_id) if item.responsible_user_id else None,
        responsible=_user_read(responsible),
        staff=[_lab_staff_read(db, row) for row in staff],
        is_active=item.is_active,
        equipment_count=svc.lab_equipment_count(item.id),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _lab_staff_read(db: Session, item: LabStaffAssignment) -> LabStaffRead:
    user = db.get(UserAccount, item.user_id)
    return LabStaffRead(
        id=str(item.id),
        lab_id=str(item.lab_id),
        user_id=str(item.user_id),
        role=item.role,
        user=_user_read(user),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _lab_closure_read(db: Session, svc: ResourcesService, item: LabClosure) -> LabClosureRead:
    lab = db.get(Lab, item.lab_id)
    return LabClosureRead(
        id=str(item.id),
        lab_id=str(item.lab_id),
        start_at=item.start_at,
        end_at=item.end_at,
        reason=item.reason,
        notes=item.notes,
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        cancelled_booking_count=int(item.cancelled_booking_count or 0),
        lab=_lab_read(db, svc, lab),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _requirement_read(db: Session, item: EquipmentRequirement) -> EquipmentRequirementRead:
    equipment = db.get(Equipment, item.equipment_id)
    return EquipmentRequirementRead(
        id=str(item.id),
        project_id=str(item.project_id),
        equipment_id=str(item.equipment_id),
        priority=item.priority,
        purpose=item.purpose,
        notes=item.notes,
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        equipment=_equipment_read(db, equipment),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _equipment_material_read(item: EquipmentMaterial) -> EquipmentMaterialRead:
    return EquipmentMaterialRead(
        id=str(item.id),
        equipment_id=str(item.equipment_id),
        material_type=item.material_type,
        title=item.title,
        external_url=item.external_url,
        attachment_filename=item.attachment_filename,
        attachment_url=f"/resources/equipment-materials/{item.id}/file" if item.attachment_path else None,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _booking_read(db: Session, item: EquipmentBooking) -> EquipmentBookingRead:
    equipment = db.get(Equipment, item.equipment_id)
    requester = db.get(UserAccount, item.requester_user_id) if item.requester_user_id else None
    approver = db.get(UserAccount, item.approved_by_user_id) if item.approved_by_user_id else None
    return EquipmentBookingRead(
        id=str(item.id),
        equipment_id=str(item.equipment_id),
        project_id=str(item.project_id),
        requester_user_id=str(item.requester_user_id) if item.requester_user_id else None,
        approved_by_user_id=str(item.approved_by_user_id) if item.approved_by_user_id else None,
        start_at=item.start_at,
        end_at=item.end_at,
        status=item.status,
        purpose=item.purpose,
        notes=item.notes,
        equipment=_equipment_read(db, equipment),
        requester=_user_read(requester),
        approver=_user_read(approver),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _downtime_read(db: Session, item: EquipmentDowntime) -> EquipmentDowntimeRead:
    equipment = db.get(Equipment, item.equipment_id)
    return EquipmentDowntimeRead(
        id=str(item.id),
        equipment_id=str(item.equipment_id),
        start_at=item.start_at,
        end_at=item.end_at,
        reason=item.reason,
        notes=item.notes,
        created_by_user_id=str(item.created_by_user_id) if item.created_by_user_id else None,
        equipment=_equipment_read(db, equipment),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _blocker_read(db: Session, item: EquipmentBlocker) -> EquipmentBlockerRead:
    equipment = db.get(Equipment, item.equipment_id)
    return EquipmentBlockerRead(
        id=str(item.id),
        project_id=str(item.project_id),
        equipment_id=str(item.equipment_id),
        booking_id=str(item.booking_id) if item.booking_id else None,
        started_at=item.started_at,
        ended_at=item.ended_at,
        blocked_days=item.blocked_days,
        reason=item.reason,
        status=item.status,
        equipment=_equipment_read(db, equipment),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _broadcast_read(item, authors: dict[uuid.UUID, UserAccount], recipient_counts: dict[uuid.UUID, int]) -> ProjectBroadcastRead:
    author = authors.get(item.author_user_id)
    return ProjectBroadcastRead(
        id=str(item.id),
        project_id=str(item.project_id) if item.project_id else None,
        lab_id=str(item.lab_id) if item.lab_id else None,
        author_user_id=str(item.author_user_id),
        author_display_name=author.display_name if author else "Unknown",
        title=item.title,
        body=item.body,
        severity=item.severity,
        deliver_telegram=item.deliver_telegram,
        recipient_count=int(recipient_counts.get(item.id, 0)),
        sent_at=item.sent_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _notify_booking_created(db: Session, booking: EquipmentBooking, *, actor_user_id: uuid.UUID) -> None:
    equipment = db.get(Equipment, booking.equipment_id)
    project = db.get(Project, booking.project_id)
    if not equipment or not equipment.owner_user_id or equipment.owner_user_id == actor_user_id:
        return
    NotificationService(db).notify(
        equipment.owner_user_id,
        booking.project_id,
        title=f"Booking Request · {equipment.name}",
        body=f"{project.code if project else 'Project'} requested {equipment.name} for {booking.start_at.date()}.",
        link_type="resource_booking",
        link_id=booking.id,
    )


def _notify_booking_approved(db: Session, booking: EquipmentBooking, *, actor_user_id: uuid.UUID) -> None:
    equipment = db.get(Equipment, booking.equipment_id)
    project = db.get(Project, booking.project_id)
    if not equipment or not booking.requester_user_id or booking.requester_user_id == actor_user_id:
        return
    NotificationService(db).notify(
        booking.requester_user_id,
        booking.project_id,
        title=f"Booking Approved · {equipment.name}",
        body=f"{equipment.name} was approved for {project.code if project else 'the project'}.",
        link_type="resource_booking",
        link_id=booking.id,
    )


def _notify_booking_rejected(db: Session, booking: EquipmentBooking, *, actor_user_id: uuid.UUID) -> None:
    equipment = db.get(Equipment, booking.equipment_id)
    project = db.get(Project, booking.project_id)
    if not equipment or not booking.requester_user_id or booking.requester_user_id == actor_user_id:
        return
    NotificationService(db).notify(
        booking.requester_user_id,
        booking.project_id,
        title=f"Booking Rejected · {equipment.name}",
        body=f"{equipment.name} was rejected for {project.code if project else 'the project'}.",
        link_type="resource_booking",
        link_id=booking.id,
    )


def _notify_booking_cancelled(
    db: Session,
    booking: EquipmentBooking,
    *,
    actor_user_id: uuid.UUID,
    reason_prefix: str = "Booking Cancelled",
    body_override: str | None = None,
) -> None:
    equipment = db.get(Equipment, booking.equipment_id)
    project = db.get(Project, booking.project_id)
    if not equipment:
        return
    svc = NotificationService(db)
    if equipment.owner_user_id and equipment.owner_user_id != actor_user_id:
        svc.notify(
            equipment.owner_user_id,
            booking.project_id,
            title=f"{reason_prefix} · {equipment.name}",
            body=body_override or f"{project.code if project else 'Project'} cancelled the request for {equipment.name}.",
            link_type="resource_booking",
            link_id=booking.id,
        )
    if booking.requester_user_id and booking.requester_user_id != actor_user_id:
        svc.notify(
            booking.requester_user_id,
            booking.project_id,
            title=f"{reason_prefix} · {equipment.name}",
            body=body_override or f"The request for {equipment.name} was cancelled.",
            link_type="resource_booking",
            link_id=booking.id,
        )
