import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import IdMixin, TimestampMixin


class ProjectHealthSnapshot(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_health_snapshots"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    health_score: Mapped[str] = mapped_column(String(16), index=True)
    validation_errors: Mapped[int] = mapped_column(Integer, default=0)
    validation_warnings: Mapped[int] = mapped_column(Integer, default=0)
    coherence_issues: Mapped[int] = mapped_column(Integer, default=0)
    action_items_pending: Mapped[int] = mapped_column(Integer, default=0)
    risks_open: Mapped[int] = mapped_column(Integer, default=0)
    overdue_deliverables: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict)
