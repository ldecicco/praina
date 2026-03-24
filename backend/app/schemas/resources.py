from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import PaginatedResponse


class ResourceOwnerRead(BaseModel):
    user_id: str
    display_name: str
    email: str


class LabCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    building: str | None = Field(default=None, max_length=255)
    room: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    responsible_user_id: str | None = None
    is_active: bool = True


class LabUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    building: str | None = Field(default=None, max_length=255)
    room: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    responsible_user_id: str | None = None
    is_active: bool | None = None


class LabRead(BaseModel):
    id: str
    name: str
    building: str | None
    room: str | None
    notes: str | None
    responsible_user_id: str | None
    responsible: ResourceOwnerRead | None = None
    is_active: bool
    equipment_count: int = 0
    created_at: datetime
    updated_at: datetime


class LabListRead(PaginatedResponse):
    items: list[LabRead]


class LabClosureCreate(BaseModel):
    lab_id: str
    start_at: datetime
    end_at: datetime
    reason: str = "personnel_unavailable"
    notes: str | None = None


class LabClosureRead(BaseModel):
    id: str
    lab_id: str
    start_at: datetime
    end_at: datetime
    reason: str
    notes: str | None
    created_by_user_id: str | None
    cancelled_booking_count: int
    lab: LabRead
    created_at: datetime
    updated_at: datetime


class LabClosureListRead(PaginatedResponse):
    items: list[LabClosureRead]


class EquipmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    category: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    lab_id: str | None = None
    owner_user_id: str | None = None
    status: str = "active"
    usage_mode: str = "exclusive"
    access_notes: str | None = None
    booking_notes: str | None = None
    maintenance_notes: str | None = None
    is_active: bool = True


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    category: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    description: str | None = None
    location: str | None = Field(default=None, max_length=255)
    lab_id: str | None = None
    owner_user_id: str | None = None
    status: str | None = None
    usage_mode: str | None = None
    access_notes: str | None = None
    booking_notes: str | None = None
    maintenance_notes: str | None = None
    is_active: bool | None = None


class EquipmentRead(BaseModel):
    id: str
    name: str
    category: str | None
    model: str | None
    serial_number: str | None
    description: str | None
    location: str | None
    lab_id: str | None
    lab: LabRead | None = None
    owner_user_id: str | None
    owner: ResourceOwnerRead | None = None
    status: str
    usage_mode: str
    access_notes: str | None
    booking_notes: str | None
    maintenance_notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EquipmentListRead(PaginatedResponse):
    items: list[EquipmentRead]


class EquipmentRequirementCreate(BaseModel):
    equipment_id: str
    priority: str = "important"
    purpose: str = Field(min_length=2)
    notes: str | None = None


class EquipmentRequirementUpdate(BaseModel):
    priority: str | None = None
    purpose: str | None = Field(default=None, min_length=2)
    notes: str | None = None


class EquipmentRequirementRead(BaseModel):
    id: str
    project_id: str
    equipment_id: str
    priority: str
    purpose: str
    notes: str | None
    created_by_user_id: str | None
    equipment: EquipmentRead
    created_at: datetime
    updated_at: datetime


class EquipmentRequirementListRead(PaginatedResponse):
    items: list[EquipmentRequirementRead]


class EquipmentBookingCreate(BaseModel):
    equipment_id: str
    project_id: str
    start_at: datetime
    end_at: datetime
    purpose: str = Field(min_length=2)
    notes: str | None = None


class EquipmentBookingUpdate(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    purpose: str | None = Field(default=None, min_length=2)
    notes: str | None = None
    status: str | None = None


class EquipmentBookingDecision(BaseModel):
    notes: str | None = None


class EquipmentBookingRead(BaseModel):
    id: str
    equipment_id: str
    project_id: str
    requester_user_id: str | None
    approved_by_user_id: str | None
    start_at: datetime
    end_at: datetime
    status: str
    purpose: str
    notes: str | None
    equipment: EquipmentRead
    requester: ResourceOwnerRead | None = None
    approver: ResourceOwnerRead | None = None
    created_at: datetime
    updated_at: datetime


class EquipmentBookingListRead(PaginatedResponse):
    items: list[EquipmentBookingRead]


class EquipmentDowntimeCreate(BaseModel):
    equipment_id: str
    start_at: datetime
    end_at: datetime
    reason: str = "maintenance"
    notes: str | None = None


class EquipmentDowntimeUpdate(BaseModel):
    start_at: datetime | None = None
    end_at: datetime | None = None
    reason: str | None = None
    notes: str | None = None


class EquipmentDowntimeRead(BaseModel):
    id: str
    equipment_id: str
    start_at: datetime
    end_at: datetime
    reason: str
    notes: str | None
    created_by_user_id: str | None
    equipment: EquipmentRead
    created_at: datetime
    updated_at: datetime


class EquipmentDowntimeListRead(PaginatedResponse):
    items: list[EquipmentDowntimeRead]


class EquipmentBlockerRead(BaseModel):
    id: str
    project_id: str
    equipment_id: str
    booking_id: str | None
    started_at: datetime
    ended_at: datetime | None
    blocked_days: int
    reason: str
    status: str
    equipment: EquipmentRead
    created_at: datetime
    updated_at: datetime


class EquipmentConflictRead(BaseModel):
    equipment_id: str
    equipment_name: str
    conflict_type: str
    booking_id: str | None = None
    conflicting_booking_id: str | None = None
    downtime_id: str | None = None
    project_id: str | None = None
    conflicting_project_id: str | None = None
    start_at: datetime
    end_at: datetime
    detail: str


class ProjectResourcesWorkspaceRead(BaseModel):
    requirements: list[EquipmentRequirementRead] = Field(default_factory=list)
    bookings: list[EquipmentBookingRead] = Field(default_factory=list)
    blockers: list[EquipmentBlockerRead] = Field(default_factory=list)
