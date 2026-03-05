import uuid

from sqlalchemy import Column, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


wp_collaborators = Table(
    "wp_collaborators",
    Base.metadata,
    Column("wp_id", ForeignKey("work_packages.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)

task_collaborators = Table(
    "task_collaborators",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)

milestone_collaborators = Table(
    "milestone_collaborators",
    Base.metadata,
    Column("milestone_id", ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)

deliverable_collaborators = Table(
    "deliverable_collaborators",
    Base.metadata,
    Column("deliverable_id", ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)


class WorkPackage(Base, IdMixin, TimestampMixin):
    __tablename__ = "work_packages"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("work_packages.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    leader_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_organizations.id", ondelete="RESTRICT"), index=True
    )
    responsible_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("team_members.id", ondelete="RESTRICT"), index=True
    )

    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_deliverable_project_code"),)
