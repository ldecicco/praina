import uuid
from datetime import datetime
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


wp_collaborators = Table(
    "wp_collaborators",
    Base.metadata,
    Column("wp_id", ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
    Column("partner_id", ForeignKey("partner_organizations.id", ondelete="CASCADE"), primary_key=True),
)

task_collaborators = Table(
    "task_collaborators",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("partner_id", ForeignKey("partner_organizations.id", ondelete="CASCADE"), primary_key=True),
)

milestone_collaborators = Table(
    "milestone_collaborators",
    Base.metadata,
    Column("milestone_id", ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True),
    Column("partner_id", ForeignKey("partner_organizations.id", ondelete="CASCADE"), primary_key=True),
)

deliverable_collaborators = Table(
    "deliverable_collaborators",
    Base.metadata,
    Column("deliverable_id", ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True),
    Column("partner_id", ForeignKey("partner_organizations.id", ondelete="CASCADE"), primary_key=True),
)

deliverable_wps = Table(
    "deliverable_wps",
    Base.metadata,
    Column("deliverable_id", ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True),
    Column("wp_id", ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
)

milestone_wps = Table(
    "milestone_wps",
    Base.metadata,
    Column("milestone_id", ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True),
    Column("wp_id", ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
)


class DeliverableWorkflowStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    changes_requested = "changes_requested"
    approved = "approved"
    submitted = "submitted"


class WorkExecutionStatus(str, enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    blocked = "blocked"
    ready_for_closure = "ready_for_closure"
    closed = "closed"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class RiskStatus(str, enum.Enum):
    open = "open"
    monitoring = "monitoring"
    mitigated = "mitigated"
    closed = "closed"


class WorkPackage(Base, IdMixin, TimestampMixin):
    __tablename__ = "work_packages"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_month: Mapped[int] = mapped_column(Integer)
    end_month: Mapped[int] = mapped_column(Integer)
    execution_status: Mapped[WorkExecutionStatus] = mapped_column(
        Enum(WorkExecutionStatus), default=WorkExecutionStatus.planned, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    leader_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    responsible_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_wp_project_code"),)


class Task(Base, IdMixin, TimestampMixin):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    wp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work_packages.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_month: Mapped[int] = mapped_column(Integer)
    end_month: Mapped[int] = mapped_column(Integer)
    execution_status: Mapped[WorkExecutionStatus] = mapped_column(
        Enum(WorkExecutionStatus), default=WorkExecutionStatus.planned, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    leader_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    responsible_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_task_project_code"),)


class Milestone(Base, IdMixin, TimestampMixin):
    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_month: Mapped[int] = mapped_column(Integer)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    leader_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    responsible_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_milestone_project_code"),)


class Deliverable(Base, IdMixin, TimestampMixin):
    __tablename__ = "deliverables"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_month: Mapped[int] = mapped_column(Integer)
    workflow_status: Mapped[DeliverableWorkflowStatus] = mapped_column(
        Enum(DeliverableWorkflowStatus), default=DeliverableWorkflowStatus.draft, index=True
    )
    review_due_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_owner_member_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    leader_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    responsible_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_deliverable_project_code"),)


class ProjectRisk(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_risks"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitigation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RiskStatus] = mapped_column(Enum(RiskStatus), default=RiskStatus.open, index=True)
    probability: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.medium, index=True)
    impact: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), default=RiskLevel.medium, index=True)
    due_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    owner_member_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_project_risk_code"),)
