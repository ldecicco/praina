"""Report generation service — status reports, meeting reports, audit log export."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.action_item import ActionItemStatus, MeetingActionItem
from app.models.audit import AuditEvent
from app.models.meeting import MeetingRecord
from app.models.organization import TeamMember
from app.models.project import Project
from app.models.work import (
    Deliverable,
    Milestone,
    ProjectRisk,
    Task,
    WorkExecutionStatus,
    WorkPackage,
)


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def generate_status_report(self, project_id: uuid.UUID) -> str:
        project = self.db.get(Project, project_id)
        if not project:
            return "Project not found."

        lines: list[str] = []
        lines.append(f"# Project Status Report: {project.code} — {project.title}")
        lines.append("")
        lines.append(f"- **Status:** {project.status}")
        lines.append(f"- **Start date:** {project.start_date}")
        lines.append(f"- **Duration:** {project.duration_months} months")
        lines.append(f"- **Baseline version:** {project.baseline_version}")
        lines.append(f"- **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("")

        # Work packages summary
        wps = list(self.db.scalars(
            select(WorkPackage).where(
                WorkPackage.project_id == project_id,
                WorkPackage.is_trashed.is_(False),
            ).order_by(WorkPackage.code)
        ).all())
        lines.append("## Work Packages")
        lines.append("")
        if wps:
            lines.append("| Code | Title | Exec Status | Tasks (done/total) |")
            lines.append("|------|-------|-------------|-------------------|")
            for wp in wps:
                total_tasks = self.db.scalar(
                    select(func.count()).select_from(Task).where(
                        Task.wp_id == wp.id, Task.is_trashed.is_(False),
                    )
                ) or 0
                done_tasks = self.db.scalar(
                    select(func.count()).select_from(Task).where(
                        Task.wp_id == wp.id, Task.is_trashed.is_(False),
                        Task.execution_status == WorkExecutionStatus.closed,
                    )
                ) or 0
                status = wp.execution_status.value if hasattr(wp.execution_status, "value") else str(wp.execution_status or "—")
                lines.append(f"| {wp.code} | {wp.title} | {status} | {done_tasks}/{total_tasks} |")
        else:
            lines.append("_No work packages._")
        lines.append("")

        # Deliverables
        deliverables = list(self.db.scalars(
            select(Deliverable).where(
                Deliverable.project_id == project_id,
                Deliverable.is_trashed.is_(False),
            ).order_by(Deliverable.code)
        ).all())
        lines.append("## Deliverables")
        lines.append("")
        if deliverables:
            lines.append("| Code | Title | Workflow | Due Month |")
            lines.append("|------|-------|---------|-----------|")
            for d in deliverables:
                wf = d.workflow_status.value if hasattr(d.workflow_status, "value") else str(d.workflow_status or "—")
                due = f"M{d.due_month}" if d.due_month else "—"
                lines.append(f"| {d.code} | {d.title} | {wf} | {due} |")
        else:
            lines.append("_No deliverables._")
        lines.append("")

        # Milestones
        milestones = list(self.db.scalars(
            select(Milestone).where(
                Milestone.project_id == project_id,
                Milestone.is_trashed.is_(False),
            ).order_by(Milestone.due_month)
        ).all())
        if milestones:
            lines.append("## Milestones")
            lines.append("")
            lines.append("| Code | Title | Due Month | Status |")
            lines.append("|------|-------|-----------|--------|")
            for m in milestones:
                due = f"M{m.due_month}" if m.due_month else "—"
                status = "—"
                lines.append(f"| {m.code} | {m.title} | {due} | {status} |")
            lines.append("")

        # Open risks
        risks = list(self.db.scalars(
            select(ProjectRisk).where(
                ProjectRisk.project_id == project_id,
                ProjectRisk.status != "closed",
            ).order_by(ProjectRisk.code)
        ).all())
        lines.append("## Open Risks")
        lines.append("")
        if risks:
            lines.append("| Code | Title | Probability | Impact | Status |")
            lines.append("|------|-------|-------------|--------|--------|")
            for r in risks:
                probability = r.probability.value if hasattr(r.probability, "value") else str(r.probability)
                impact = r.impact.value if hasattr(r.impact, "value") else str(r.impact)
                status = r.status.value if hasattr(r.status, "value") else str(r.status)
                lines.append(f"| {r.code} | {r.title} | {probability} | {impact} | {status} |")
        else:
            lines.append("_No open risks._")
        lines.append("")

        # Recent meetings
        meetings = list(self.db.scalars(
            select(MeetingRecord).where(
                MeetingRecord.project_id == project_id,
            ).order_by(MeetingRecord.starts_at.desc()).limit(5)
        ).all())
        if meetings:
            lines.append("## Recent Meetings")
            lines.append("")
            for m in meetings:
                date_str = m.starts_at.strftime("%Y-%m-%d") if m.starts_at else "N/A"
                lines.append(f"### {m.title} ({date_str})")
                if m.summary:
                    lines.append(f"\n{m.summary}\n")
                else:
                    lines.append("")

        # Pending action items
        pending_items = list(self.db.scalars(
            select(MeetingActionItem).where(
                MeetingActionItem.project_id == project_id,
                MeetingActionItem.status == ActionItemStatus.pending,
            ).order_by(MeetingActionItem.created_at.desc()).limit(20)
        ).all())
        if pending_items:
            lines.append("## Pending Action Items")
            lines.append("")
            for item in pending_items:
                assignee = item.assignee_name or "Unassigned"
                due = f" (due {item.due_date})" if item.due_date else ""
                lines.append(f"- [ ] {item.description} — _{assignee}{due}_")
            lines.append("")

        return "\n".join(lines)

    def generate_meeting_report(self, project_id: uuid.UUID, meeting_id: uuid.UUID) -> str:
        meeting = self.db.scalar(
            select(MeetingRecord).where(
                MeetingRecord.project_id == project_id,
                MeetingRecord.id == meeting_id,
            )
        )
        if not meeting:
            return "Meeting not found."

        lines: list[str] = []
        date_str = meeting.starts_at.strftime("%Y-%m-%d") if meeting.starts_at else "N/A"
        lines.append(f"# Meeting Report: {meeting.title}")
        lines.append("")
        lines.append(f"- **Date:** {date_str}")
        participants = meeting.participants_json if isinstance(meeting.participants_json, list) else []
        if participants:
            lines.append(f"- **Participants:** {', '.join(participants)}")
        lines.append("")

        if meeting.summary:
            lines.append("## Summary")
            lines.append("")
            lines.append(meeting.summary)
            lines.append("")

        # Action items
        items = list(self.db.scalars(
            select(MeetingActionItem).where(
                MeetingActionItem.meeting_id == meeting_id,
            ).order_by(MeetingActionItem.sort_order)
        ).all())
        if items:
            lines.append("## Action Items")
            lines.append("")
            for item in items:
                check = "x" if item.status in (ActionItemStatus.done, "done") else " "
                assignee = item.assignee_name or "Unassigned"
                due = f" (due {item.due_date})" if item.due_date else ""
                lines.append(f"- [{check}] {item.description} — _{assignee}{due}_")
            lines.append("")

        # Content excerpt
        if meeting.content_text:
            excerpt = meeting.content_text[:2000]
            if len(meeting.content_text) > 2000:
                excerpt += "\n\n_(truncated)_"
            lines.append("## Content")
            lines.append("")
            lines.append(excerpt)
            lines.append("")

        return "\n".join(lines)

    def export_audit_log(
        self,
        project_id: uuid.UUID,
        event_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        stmt = select(AuditEvent).where(AuditEvent.project_id == project_id)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        if start_date:
            stmt = stmt.where(AuditEvent.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditEvent.created_at <= end_date)
        stmt = stmt.order_by(AuditEvent.created_at.desc())

        rows = list(self.db.scalars(stmt).all())
        actor_ids = [row.actor_id for row in rows if row.actor_id]
        actor_map: dict[uuid.UUID, str] = {}
        if actor_ids:
            actors = self.db.scalars(select(TeamMember).where(TeamMember.id.in_(actor_ids))).all()
            actor_map = {actor.id: actor.full_name for actor in actors}
        return [
            {
                "id": str(r.id),
                "event_type": r.event_type,
                "entity_type": r.entity_type,
                "entity_id": str(r.entity_id),
                "actor_name": actor_map.get(r.actor_id, "") if r.actor_id else "",
                "reason": r.reason or "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
