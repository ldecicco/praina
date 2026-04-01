import uuid
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import DocumentChunk, DocumentStatus, ProjectDocument
from app.models.proposal import ProjectProposalSection
from app.models.auth import PlatformRole, ProjectMembership, ProjectRole, UserAccount
from app.models.collaboration_chat import (
    ProjectChatMessage,
    ProjectChatMessageReaction,
    ProjectChatRoom,
    ProjectChatRoomMember,
)
from app.models.organization import PartnerOrganization, TeamMember
from app.models.project import Project, ProjectKind
from app.models.course import Course, CourseMaterial, CourseTeachingAssistant
from app.models.teaching import (
    TeachingProgressReport,
    TeachingProjectArtifact,
    TeachingProjectBlocker,
    TeachingProjectMilestone,
    TeachingProjectProfile,
    TeachingProjectStudent,
)
from app.models.work import Deliverable, Milestone, Task, WorkPackage, deliverable_wps, milestone_wps
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError
from app.services.resources_service import ResourcesService
from app.services.scoped_chat_service import ScopedChatService
from app.services.teaching_service import TeachingService

MANAGE_ROOMS_ROLES = {ProjectRole.project_owner.value, ProjectRole.project_manager.value}
READ_ROLES = {item.value for item in ProjectRole}
WRITE_ROLES = {
    ProjectRole.project_owner.value,
    ProjectRole.project_manager.value,
    ProjectRole.partner_lead.value,
    ProjectRole.partner_member.value,
    ProjectRole.reviewer.value,
}
BOT_USER_EMAIL = "project-bot@agenticpm.local"
LEGACY_BOT_USER_EMAILS = {"project-bot@local"}
BOT_DISPLAY_NAME = "Project Bot"
BOT_PLATFORM_ROLE = PlatformRole.user.value
BOT_MENTION_RE = re.compile(r"(^|\s)@bot\b", flags=re.IGNORECASE)
USER_MENTION_RE = re.compile(r"(?<![A-Za-z0-9._:-])@([A-Za-z0-9._:-]+)")
MAX_CITATIONS = 3
MAX_CHUNK_SCAN = 400
DOCUMENT_REF_RE = re.compile(r"(?<!\w)#([A-Za-z0-9._-]+)")


class ProjectChatService:
    def __init__(self, db: Session):
        self.db = db
        self.scoped = ScopedChatService(db)

    def list_rooms(self, project_id: uuid.UUID, user_id: uuid.UUID) -> list[ProjectChatRoom]:
        role = self._get_user_project_role(project_id, user_id)
        if role not in READ_ROLES:
            raise ValidationError("Insufficient role to read project chat.")
        self._ensure_default_room(project_id)

        rooms = self.db.scalars(
            select(ProjectChatRoom)
            .where(
                ProjectChatRoom.project_id == project_id,
                ProjectChatRoom.is_archived.is_(False),
                ProjectChatRoom.scope_type != "research_collection",
            )
            .order_by(ProjectChatRoom.created_at.asc())
        ).all()
        return [room for room in rooms if self._can_access_room(project_id, room.id, user_id, role)]

    def create_room(
        self, project_id: uuid.UUID, user_id: uuid.UUID, name: str, description: str | None, scope_type: str, scope_ref_id: uuid.UUID | None
    ) -> ProjectChatRoom:
        role = self._get_user_project_role(project_id, user_id)
        if role not in MANAGE_ROOMS_ROLES:
            raise ValidationError("Insufficient role to create project chat rooms.")

        room = ProjectChatRoom(
            project_id=project_id,
            name=name.strip(),
            description=description.strip() if description else None,
            scope_type=scope_type.strip().lower() if scope_type else "project",
            scope_ref_id=scope_ref_id,
            is_archived=False,
        )
        self.db.add(room)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Room name already exists in this project.") from exc
        self.db.refresh(room)
        return room

    def add_room_member(self, project_id: uuid.UUID, room_id: uuid.UUID, actor_user_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        role = self._get_user_project_role(project_id, actor_user_id)
        if role not in MANAGE_ROOMS_ROLES:
            raise ValidationError("Insufficient role to manage room members.")
        room = self._get_room(project_id, room_id)
        self._get_user_project_role(project_id, target_user_id)

        rel = ProjectChatRoomMember(thread_id=room.id, user_id=target_user_id)
        self.db.add(rel)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def remove_room_member(
        self, project_id: uuid.UUID, room_id: uuid.UUID, actor_user_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> None:
        role = self._get_user_project_role(project_id, actor_user_id)
        if role not in MANAGE_ROOMS_ROLES:
            raise ValidationError("Insufficient role to manage room members.")
        room = self._get_room(project_id, room_id)
        rel = self.db.scalar(
            select(ProjectChatRoomMember).where(ProjectChatRoomMember.thread_id == room.id, ProjectChatRoomMember.user_id == target_user_id)
        )
        if rel:
            self.db.delete(rel)
            self.db.commit()

    def list_messages(
        self, project_id: uuid.UUID, room_id: uuid.UUID, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[ProjectChatMessage], int]:
        role = self._get_user_project_role(project_id, user_id)
        room = self._get_room(project_id, room_id)
        if role not in READ_ROLES or not self._can_access_room(project_id, room.id, user_id, role):
            raise ValidationError("Insufficient role or membership to read room messages.")
        return self.scoped.list_messages(
            ProjectChatMessage,
            scope_field="thread_id",
            scope_id=room.id,
            page=page,
            page_size=page_size,
        )

    def get_room(self, project_id: uuid.UUID, room_id: uuid.UUID) -> ProjectChatRoom:
        return self._get_room(project_id, room_id)

    def create_message(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        reply_to_message_id: uuid.UUID | None = None,
    ) -> ProjectChatMessage:
        role = self._get_user_project_role(project_id, user_id)
        room = self._get_room(project_id, room_id)
        if role not in WRITE_ROLES or not self._can_access_room(project_id, room.id, user_id, role):
            raise ValidationError("Insufficient role or membership to write in this room.")
        message = self.scoped.create_message(
            ProjectChatMessage,
            scope_field="thread_id",
            scope_id=room.id,
            sender_user_id=user_id,
            content=content,
            reply_to_message_id=reply_to_message_id,
        )
        self._notify_user_mentions(project_id, room, message, sender_user_id=user_id)
        return message

    def toggle_message_reaction(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        emoji: str,
    ) -> ProjectChatMessage:
        role = self._get_user_project_role(project_id, user_id)
        room = self._get_room(project_id, room_id)
        if role not in WRITE_ROLES or not self._can_access_room(project_id, room.id, user_id, role):
            raise ValidationError("Insufficient role or membership to react in this room.")
        return self.scoped.toggle_reaction(
            ProjectChatMessage,
            ProjectChatMessageReaction,
            scope_field="thread_id",
            scope_id=room.id,
            message_id=message_id,
            actor_user_id=user_id,
            emoji=emoji,
        )

    def get_message(self, project_id: uuid.UUID, room_id: uuid.UUID, user_id: uuid.UUID, message_id: uuid.UUID) -> ProjectChatMessage:
        role = self._get_user_project_role(project_id, user_id)
        room = self._get_room(project_id, room_id)
        if role not in READ_ROLES or not self._can_access_room(project_id, room.id, user_id, role):
            raise ValidationError("Insufficient role or membership to read room messages.")
        return self._get_message(project_id, room.id, message_id)

    def message_lookup(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, ProjectChatMessage]:
        return self.scoped.message_lookup(ProjectChatMessage, message_ids)

    def reaction_summary_by_message(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
        return self.scoped.reaction_summary_by_message(ProjectChatMessageReaction, message_ids)

    def create_bot_message(self, project_id: uuid.UUID, room_id: uuid.UUID, content: str) -> ProjectChatMessage:
        room = self._get_room(project_id, room_id)
        text = content.strip()
        if not text:
            raise ValidationError("Bot message content cannot be empty.")
        bot_user = self.ensure_bot_user()
        message = ProjectChatMessage(
            thread_id=room.id,
            sender_user_id=bot_user.id,
            content=text[:8000],
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def ensure_bot_user(self) -> UserAccount:
        bot = self.db.scalar(select(UserAccount).where(UserAccount.email == BOT_USER_EMAIL))
        if bot:
            return bot
        legacy_bot = self.db.scalar(select(UserAccount).where(UserAccount.email.in_(LEGACY_BOT_USER_EMAILS)))
        if legacy_bot:
            legacy_bot.email = BOT_USER_EMAIL
            legacy_bot.display_name = BOT_DISPLAY_NAME
            legacy_bot.platform_role = BOT_PLATFORM_ROLE
            legacy_bot.is_active = True
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                bot = self.db.scalar(select(UserAccount).where(UserAccount.email == BOT_USER_EMAIL))
                if bot:
                    return bot
                raise
            self.db.refresh(legacy_bot)
            return legacy_bot
        bot = UserAccount(
            email=BOT_USER_EMAIL,
            password_hash="bot-account",
            display_name=BOT_DISPLAY_NAME,
            platform_role=BOT_PLATFORM_ROLE,
            is_active=True,
        )
        self.db.add(bot)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # Race-safe retry.
            bot = self.db.scalar(select(UserAccount).where(UserAccount.email == BOT_USER_EMAIL))
            if bot:
                return bot
            raise
        self.db.refresh(bot)
        return bot

    def recent_messages_for_agent(self, project_id: uuid.UUID, room_id: uuid.UUID, limit: int = 12) -> list[dict[str, str]]:
        stmt = (
            select(ProjectChatMessage)
            .where(ProjectChatMessage.thread_id == room_id)
            .order_by(ProjectChatMessage.created_at.desc())
            .limit(limit)
        )
        items = list(self.db.scalars(stmt).all())
        items.reverse()
        output: list[dict[str, str]] = []
        for item in items:
            role = "assistant" if self._is_bot_user(item.sender_user_id) else "user"
            output.append({"role": role, "content": item.content})
        return output

    def project_context_for_agent(self, project_id: uuid.UUID) -> dict:
        project = self._get_project(project_id)
        if (getattr(project, "project_kind", "funded") or "funded") == "teaching":
            return self._teaching_context_for_agent(project)
        partners = self.db.scalars(
            select(PartnerOrganization).where(PartnerOrganization.project_id == project_id).order_by(PartnerOrganization.short_name.asc())
        ).all()
        members = self.db.scalars(
            select(TeamMember).where(TeamMember.project_id == project_id).order_by(TeamMember.full_name.asc())
        ).all()
        wps = self.db.scalars(select(WorkPackage).where(WorkPackage.project_id == project_id).order_by(WorkPackage.code.asc())).all()
        tasks = self.db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.code.asc())).all()
        milestones = self.db.scalars(
            select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.code.asc())
        ).all()
        deliverables = self.db.scalars(
            select(Deliverable).where(Deliverable.project_id == project_id).order_by(Deliverable.code.asc())
        ).all()

        wp_by_id = {wp.id: wp for wp in wps}
        partner_by_id = {item.id: item for item in partners}

        member_rows: list[dict] = []
        for member in members:
            partner = partner_by_id.get(member.organization_id)
            member_rows.append(
                {
                    "full_name": member.full_name,
                    "email": member.email,
                    "role": member.role,
                    "partner_short_name": partner.short_name if partner else None,
                    "is_active": member.is_active,
                }
            )

        task_rows: list[dict] = []
        for task in tasks:
            parent_wp = wp_by_id.get(task.wp_id)
            task_rows.append(
                {
                    "code": task.code,
                    "title": task.title,
                    "wp_code": parent_wp.code if parent_wp else None,
                    "start_month": task.start_month,
                    "end_month": task.end_month,
                }
            )

        milestone_wps_map = self._linked_wps_for_entities(milestone_wps, "milestone_id", [item.id for item in milestones], wp_by_id)
        deliverable_wps_map = self._linked_wps_for_entities(
            deliverable_wps, "deliverable_id", [item.id for item in deliverables], wp_by_id
        )

        rooms_count = int(
            self.db.scalar(
                select(func.count()).select_from(ProjectChatRoom).where(
                    ProjectChatRoom.project_id == project_id,
                    ProjectChatRoom.is_archived.is_(False),
                    ProjectChatRoom.scope_type != "research_collection",
                )
            )
            or 0
        )
        return {
            "project_id": str(project.id),
            "project_code": project.code,
            "project_title": project.title,
            "project_status": project.status.value if hasattr(project.status, "value") else str(project.status),
            "project_kind": getattr(project, "project_kind", "funded") or "funded",
            "start_date": project.start_date.isoformat(),
            "duration_months": project.duration_months,
            "reporting_dates": list(project.reporting_dates or []),
            "language": project.language,
            "coordinator_partner_id": str(project.coordinator_partner_id) if project.coordinator_partner_id else None,
            "coordinator_partner_name": partner_by_id[project.coordinator_partner_id].short_name if project.coordinator_partner_id and project.coordinator_partner_id in partner_by_id else None,
            "principal_investigator_id": str(project.principal_investigator_id) if project.principal_investigator_id else None,
            "principal_investigator_name": next((m.full_name for m in members if m.id == project.principal_investigator_id), None) if project.principal_investigator_id else None,
            "partners": [
                {"short_name": item.short_name, "legal_name": item.legal_name, "partner_type": item.partner_type, "country": item.country, "expertise": item.expertise}
                for item in partners
            ],
            "participants": member_rows,
            "work_packages": [
                {
                    "code": wp.code,
                    "title": wp.title,
                    "start_month": wp.start_month,
                    "end_month": wp.end_month,
                }
                for wp in wps
            ],
            "tasks": task_rows,
            "deliverables": [
                {
                    "code": item.code,
                    "title": item.title,
                    "due_month": item.due_month,
                    "wp_codes": deliverable_wps_map.get(item.id, []),
                }
                for item in deliverables
            ],
            "milestones": [
                {
                    "code": item.code,
                    "title": item.title,
                    "due_month": item.due_month,
                    "wp_codes": milestone_wps_map.get(item.id, []),
                }
                for item in milestones
            ],
            "rooms_count": rooms_count,
            "documents": self._document_summary(project_id),
            "resources": ResourcesService(self.db).project_resource_summary(project_id),
            "proposal_sections": self._proposal_summary(project_id, partner_by_id, members),
            "teaching_project": self._teaching_summary(project_id, members),
        }

    def _teaching_context_for_agent(self, project: Project) -> dict:
        rooms_count = int(
            self.db.scalar(
                select(func.count()).select_from(ProjectChatRoom).where(
                    ProjectChatRoom.project_id == project.id,
                    ProjectChatRoom.is_archived.is_(False),
                    ProjectChatRoom.scope_type != "research_collection",
                )
            )
            or 0
        )
        return {
            "assistant_domain": "teaching",
            "project_id": str(project.id),
            "project_code": project.code,
            "project_title": project.title,
            "project_status": project.status.value if hasattr(project.status, "value") else str(project.status),
            "project_kind": getattr(project, "project_kind", "teaching") or "teaching",
            "language": project.language,
            "rooms_count": rooms_count,
            "documents": self._document_summary(project.id),
            "resources": ResourcesService(self.db).project_resource_summary(project.id),
            "teaching_project": self._teaching_summary(project.id, []),
        }

    def _teaching_summary(self, project_id: uuid.UUID, members: list[TeamMember]) -> dict[str, object] | None:
        profile = self.db.scalar(
            select(TeachingProjectProfile).where(TeachingProjectProfile.project_id == project_id)
        )
        if not profile:
            return None
        students = self.db.scalars(
            select(TeachingProjectStudent).where(TeachingProjectStudent.project_id == project_id).order_by(TeachingProjectStudent.full_name.asc())
        ).all()
        artifacts = self.db.scalars(
            select(TeachingProjectArtifact).where(TeachingProjectArtifact.project_id == project_id).order_by(TeachingProjectArtifact.required.desc(), TeachingProjectArtifact.label.asc())
        ).all()
        blockers = self.db.scalars(
            select(TeachingProjectBlocker).where(TeachingProjectBlocker.project_id == project_id).order_by(TeachingProjectBlocker.created_at.desc())
        ).all()
        milestones = self.db.scalars(
            select(TeachingProjectMilestone).where(TeachingProjectMilestone.project_id == project_id).order_by(TeachingProjectMilestone.due_at.asc().nullslast())
        ).all()
        reports = self.db.scalars(
            select(TeachingProgressReport)
            .where(TeachingProgressReport.project_id == project_id)
            .order_by(TeachingProgressReport.report_date.desc().nullslast(), TeachingProgressReport.created_at.desc())
            .limit(4)
        ).all()
        course = self.db.scalar(select(Course).where(Course.id == profile.course_id)) if profile.course_id else None
        responsible_user = self.db.scalar(select(UserAccount).where(UserAccount.id == profile.responsible_user_id)) if profile.responsible_user_id else None
        teaching_assistants: list[UserAccount] = []
        course_materials: list[CourseMaterial] = []
        if profile.course_id:
            teaching_assistants = list(
                self.db.scalars(
                    select(UserAccount)
                    .join(CourseTeachingAssistant, CourseTeachingAssistant.user_id == UserAccount.id)
                    .where(CourseTeachingAssistant.course_id == profile.course_id)
                    .order_by(UserAccount.display_name.asc(), UserAccount.email.asc())
                ).all()
            )
            course_materials = list(
                self.db.scalars(
                    select(CourseMaterial)
                    .where(CourseMaterial.course_id == profile.course_id)
                    .order_by(CourseMaterial.sort_order.asc(), CourseMaterial.title.asc())
                    .limit(8)
                ).all()
            )
        return {
            "course_id": str(profile.course_id) if profile.course_id else None,
            "course_code": course.code if course else None,
            "course_name": course.title if course else None,
            "academic_year": profile.academic_year,
            "term": profile.term,
            "status": profile.status.value,
            "health": profile.health.value,
            "functional_objectives_markdown": (profile.functional_objectives_markdown or "")[:2000] or None,
            "specifications_markdown": (profile.specifications_markdown or "")[:2000] or None,
            "responsible_user_id": str(profile.responsible_user_id) if profile.responsible_user_id else None,
            "responsible_user_name": responsible_user.display_name if responsible_user else None,
            "teacher_name": course.teacher_user_id and (
                self.db.scalar(select(UserAccount.display_name).where(UserAccount.id == course.teacher_user_id))
            ) if course and course.teacher_user_id else None,
            "teaching_assistants": [
                {"user_id": str(item.id), "display_name": item.display_name, "email": item.email}
                for item in teaching_assistants
            ],
            "reporting_cadence_days": profile.reporting_cadence_days,
            "final_grade": profile.final_grade,
            "counts": {
                "students": len(students),
                "artifacts": len(artifacts),
                "open_blockers": len([item for item in blockers if item.status.value != "resolved"]),
                "milestones": len(milestones),
                "progress_reports": len(reports),
                "course_materials": len(course_materials),
            },
            "students": [{"full_name": item.full_name, "email": item.email} for item in students],
            "artifacts": [
                {"label": item.label, "type": item.artifact_type.value, "required": item.required, "status": item.status.value}
                for item in artifacts
            ],
            "blockers": [
                {"title": item.title, "severity": item.severity.value, "status": item.status.value}
                for item in blockers
            ],
            "milestones": [
                {"kind": item.kind, "label": item.label, "status": item.status.value, "due_at": item.due_at.isoformat() if item.due_at else None}
                for item in milestones
            ],
            "course_materials": [
                {
                    "type": item.material_type.value,
                    "title": item.title,
                    "content_markdown": (item.content_markdown or "")[:1200] or None,
                    "external_url": item.external_url,
                }
                for item in course_materials
            ],
            "recent_progress_reports": [
                {
                    "report_date": item.report_date.isoformat() if item.report_date else None,
                    "meeting_date": item.meeting_date.isoformat() if item.meeting_date else None,
                    "work_done_markdown": (item.work_done_markdown or "")[:1200],
                    "next_steps_markdown": (item.next_steps_markdown or "")[:1200],
                    "supervisor_feedback_markdown": (item.supervisor_feedback_markdown or "")[:1200] or None,
                    "attachments_count": len(item.attachment_document_keys or []),
                    "transcripts_count": len(item.transcript_document_keys or []),
                }
                for item in reports
            ],
        }

    def retrieve_citations(self, project_id: uuid.UUID, prompt: str) -> list[dict]:
        from app.agents.retrieval_agent import RetrievalAgent

        doc_refs = self.extract_document_references(project_id, prompt)
        agent = RetrievalAgent(self.db)
        results = agent.retrieve(
            query=str(doc_refs["cleaned_prompt"]),
            project_id=project_id,
            top_k=MAX_CITATIONS,
            referenced_document_keys=[str(item) for item in doc_refs["document_keys"]] or None,
        )
        return [
            {
                "document_id": item.source_id,
                "document_key": item.source_key,
                "title": item.title,
                "version": item.version,
                "chunk_index": item.chunk_index,
                "snippet": self._snippet(item.content),
                "source_type": item.source_type,
            }
            for item in results
        ]

    def compose_fallback_reply(self, project_id: uuid.UUID, prompt: str, context: dict, citations: list[dict]) -> str:
        doc_refs = self.extract_document_references(project_id, prompt)
        participants = context.get("participants", [])
        if "participant" in prompt.lower() or "participants" in prompt.lower() or "who is in" in prompt.lower():
            if participants:
                lines = ["Project participants:"]
                for item in participants:
                    partner = item.get("partner_short_name") or "Unknown partner"
                    lines.append(f"- {item.get('full_name')} ({item.get('email')}) - {partner}")
                return "\n".join(lines)

        lines = [
            f"Project {context.get('project_code')}: {context.get('project_title')}",
            f"Participants: {len(participants)}, WPs: {len(context.get('work_packages', []))}, "
            f"Tasks: {len(context.get('tasks', []))}, Deliverables: {len(context.get('deliverables', []))}, "
            f"Milestones: {len(context.get('milestones', []))}.",
        ]
        if doc_refs["titles"]:
            lines.append("Referenced documents: " + ", ".join(doc_refs["titles"]) + ".")
        if doc_refs["unresolved_tokens"]:
            lines.append(
                "Unresolved document references: "
                + ", ".join(f"#{token}" for token in doc_refs["unresolved_tokens"])
                + "."
            )
        if citations:
            lines.append("I found relevant evidence in indexed documents.")
        else:
            lines.append("No indexed document excerpt matched this question yet.")
        resources = context.get("resources")
        if isinstance(resources, dict):
            counts = resources.get("counts", {})
            if isinstance(counts, dict) and counts.get("requirements", 0):
                lines.append(
                    f"Resources: {counts.get('requirements', 0)} requirements, {counts.get('active_bookings', 0)} active bookings, {counts.get('open_blockers', 0)} open equipment blockers."
                )
        return "\n".join(lines)

    @staticmethod
    def has_bot_mention(content: str) -> bool:
        return BOT_MENTION_RE.search(content or "") is not None

    @staticmethod
    def strip_bot_mentions(content: str) -> str:
        cleaned = BOT_MENTION_RE.sub(" ", content or "")
        return " ".join(cleaned.split()).strip()

    @staticmethod
    def extract_user_mention_tokens(content: str) -> list[str]:
        seen: set[str] = set()
        tokens: list[str] = []
        for token in USER_MENTION_RE.findall(content or ""):
            normalized = token.strip().lower()
            if not normalized or normalized == "bot" or normalized in seen:
                continue
            seen.add(normalized)
            tokens.append(normalized)
        return tokens

    def extract_document_references(self, project_id: uuid.UUID, prompt: str) -> dict[str, object]:
        raw_tokens = [item.lower() for item in DOCUMENT_REF_RE.findall(prompt or "")]
        if not raw_tokens:
            return {
                "document_keys": [],
                "titles": [],
                "resolved_tokens": [],
                "unresolved_tokens": [],
                "cleaned_prompt": prompt,
            }

        documents = self.db.scalars(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.updated_at.desc(), ProjectDocument.version.desc())
        ).all()
        if not documents:
            cleaned_prompt = DOCUMENT_REF_RE.sub(" ", prompt or "")
            return {
                "document_keys": [],
                "titles": [],
                "resolved_tokens": [],
                "unresolved_tokens": raw_tokens,
                "cleaned_prompt": " ".join(cleaned_prompt.split()).strip(),
            }

        latest_by_key: dict[str, ProjectDocument] = {}
        for document in documents:
            key = str(document.document_key)
            if key not in latest_by_key:
                latest_by_key[key] = document

        token_map: dict[str, ProjectDocument] = {}
        seen = set()
        for index, document in enumerate(latest_by_key.values(), start=1):
            for alias in self._document_aliases(document, index, seen):
                token_map.setdefault(alias, document)

        resolved: list[ProjectDocument] = []
        unresolved: list[str] = []
        for token in raw_tokens:
            match = token_map.get(token)
            if not match:
                unresolved.append(token)
                continue
            if all(existing.document_key != match.document_key for existing in resolved):
                resolved.append(match)

        cleaned_prompt = DOCUMENT_REF_RE.sub(" ", prompt or "")
        return {
            "document_keys": [document.document_key for document in resolved],
            "titles": [document.title for document in resolved],
            "resolved_tokens": [token for token in raw_tokens if token not in unresolved],
            "unresolved_tokens": unresolved,
            "cleaned_prompt": " ".join(cleaned_prompt.split()).strip(),
        }

    @classmethod
    def _document_aliases(cls, document: ProjectDocument, index: int, seen: set[str]) -> list[str]:
        aliases: list[str] = []

        code_match = re.search(r"\b([A-Za-z]{1,4}\d+(?:\.\d+)*)\b", document.title or "")
        seed = code_match.group(1).lower() if code_match else ""
        title_slug = cls._to_slug(document.title or "")
        file_slug = cls._to_slug((document.original_filename or "").rsplit(".", 1)[0])

        primary_seed = seed or (title_slug.split("_")[0] if title_slug else "") or f"doc{index}"
        alias = primary_seed
        suffix = 2
        while alias in seen:
            alias = f"{primary_seed}{suffix}"
            suffix += 1
        seen.add(alias)
        aliases.append(alias)

        for extra in [title_slug, file_slug, str(document.document_key).lower()]:
            if not extra or extra in seen:
                continue
            seen.add(extra)
            aliases.append(extra)

        return aliases

    @staticmethod
    def _to_slug(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9._-]+", "_", (value or "").lower()).strip("_")
        return cleaned or "item"

    def room_member_ids(self, room_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self.db.scalars(
            select(ProjectChatRoomMember.user_id).where(ProjectChatRoomMember.thread_id == room_id)
        ).all()
        return list(rows)

    def get_user_display_name(self, user_id: uuid.UUID) -> str:
        user = self.db.get(UserAccount, user_id)
        if not user:
            return "Unknown"
        return user.display_name

    def _is_bot_user(self, user_id: uuid.UUID) -> bool:
        user = self.db.get(UserAccount, user_id)
        if not user:
            return False
        return user.email == BOT_USER_EMAIL

    def _can_access_room(self, project_id: uuid.UUID, room_id: uuid.UUID, user_id: uuid.UUID, role: str) -> bool:
        if role in MANAGE_ROOMS_ROLES:
            return True
        scoped_members = self.room_member_ids(room_id)
        if not scoped_members:
            return True
        return user_id in scoped_members

    def _ensure_default_room(self, project_id: uuid.UUID) -> None:
        existing = self.db.scalar(
            select(ProjectChatRoom).where(
                ProjectChatRoom.project_id == project_id,
                func.lower(ProjectChatRoom.name) == "general",
                ProjectChatRoom.scope_type == "project",
            )
        )
        if existing:
            return
        default_room = ProjectChatRoom(
            project_id=project_id,
            name="General",
            description="Default project room",
            scope_type="project",
            scope_ref_id=None,
            is_archived=False,
        )
        self.db.add(default_room)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def _notify_user_mentions(
        self,
        project_id: uuid.UUID,
        room: ProjectChatRoom,
        message: ProjectChatMessage,
        *,
        sender_user_id: uuid.UUID,
    ) -> None:
        tokens = self.extract_user_mention_tokens(message.content)
        if not tokens:
            return

        from app.services.notification_service import NotificationService

        token_map = self._project_user_token_map(project_id)
        sender_name = self.get_user_display_name(sender_user_id)
        content_preview = self._notification_excerpt(message.content, max_chars=220)
        notification_service = NotificationService(self.db)
        notified_user_ids: set[uuid.UUID] = set()

        for token in tokens:
            target = token_map.get(token)
            if not target or target.id == sender_user_id or target.id in notified_user_ids:
                continue
            try:
                role = self._get_user_project_role(project_id, target.id)
            except NotFoundError:
                continue
            if not self._can_access_room(project_id, room.id, target.id, role):
                continue
            notification_service.notify(
                target.id,
                project_id=project_id,
                title=f"Mentioned in {room.name}",
                body=f"{sender_name}: {content_preview}",
                link_type="project_chat_mention",
                link_id=room.id,
            )
            notified_user_ids.add(target.id)

    @staticmethod
    def _notification_excerpt(content: str, *, max_chars: int = 220) -> str:
        normalized = " ".join((content or "").split()).strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1].rstrip()}…"

    @classmethod
    def _to_user_token(cls, raw: str) -> str:
        token = re.sub(r"[^a-z0-9._-]+", "_", (raw or "").strip().lower()).strip("_")
        return token or "user"

    def _project_user_token_map(self, project_id: uuid.UUID) -> dict[str, UserAccount]:
        users = list(
            self.db.scalars(
                select(UserAccount)
                .join(ProjectMembership, ProjectMembership.user_id == UserAccount.id)
                .where(ProjectMembership.project_id == project_id)
                .order_by(UserAccount.display_name.asc(), UserAccount.email.asc())
            ).all()
        )
        token_map: dict[str, UserAccount] = {}
        seen: set[str] = {"bot"}
        for user in users:
            base = self._to_user_token(user.display_name or user.email.split("@")[0] or "user")
            token = base
            suffix = 2
            while token in seen:
                token = f"{base}{suffix}"
                suffix += 1
            seen.add(token)
            token_map[token] = user
        return token_map

    def _get_user_project_role(self, project_id: uuid.UUID, user_id: uuid.UUID) -> str:
        user = self.db.get(UserAccount, user_id)
        if user and user.platform_role == PlatformRole.super_admin.value:
            return ProjectRole.project_owner.value
        project = self._get_project(project_id)
        if (getattr(project, "project_kind", ProjectKind.funded.value) or ProjectKind.funded.value) == ProjectKind.teaching.value:
            teaching_service = TeachingService(self.db)
            if not teaching_service.can_manage_project(project_id, user_id, user.platform_role if user else PlatformRole.user.value):
                raise NotFoundError("User is not allowed to access this teaching project.")
            profile = teaching_service.ensure_profile(project_id)
            if profile.course_id:
                course = self.db.scalar(select(Course).where(Course.id == profile.course_id))
                if course and course.teacher_user_id == user_id:
                    return ProjectRole.project_owner.value
            return ProjectRole.project_manager.value
        membership = self.db.scalar(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        )
        if not membership:
            raise NotFoundError("User is not a member of this project.")
        return membership.role

    def _get_room(self, project_id: uuid.UUID, room_id: uuid.UUID) -> ProjectChatRoom:
        room = self.db.scalar(
            select(ProjectChatRoom).where(
                ProjectChatRoom.id == room_id,
                ProjectChatRoom.project_id == project_id,
                ProjectChatRoom.is_archived.is_(False),
                ProjectChatRoom.scope_type != "research_collection",
            )
        )
        if not room:
            raise NotFoundError("Room not found in project.")
        return room

    def _get_message(self, project_id: uuid.UUID, room_id: uuid.UUID, message_id: uuid.UUID) -> ProjectChatMessage:
        message = self.db.scalar(
            select(ProjectChatMessage).where(
                ProjectChatMessage.id == message_id,
                ProjectChatMessage.thread_id == room_id,
            )
        )
        if not message:
            raise NotFoundError("Message not found in room.")
        return message

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _linked_wps_for_entities(self, table, fk_name: str, entity_ids: list[uuid.UUID], wp_by_id: dict[uuid.UUID, WorkPackage]) -> dict[uuid.UUID, list[str]]:
        if not entity_ids:
            return {}
        rows = self.db.execute(
            select(table.c[fk_name], table.c.wp_id).where(table.c[fk_name].in_(entity_ids))
        ).all()
        output: dict[uuid.UUID, list[str]] = {}
        for entity_id, wp_id in rows:
            code = wp_by_id.get(wp_id).code if wp_id in wp_by_id else None
            if not code:
                continue
            output.setdefault(entity_id, []).append(code)
        return output

    def _document_summary(self, project_id: uuid.UUID) -> list[dict]:
        docs = self.db.scalars(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.updated_at.desc())
            .limit(20)
        ).all()
        return [
            {
                "title": item.title,
                "scope": item.scope.value if hasattr(item.scope, "value") else str(item.scope),
                "version": item.version,
                "status": item.status,
            }
            for item in docs
        ]

    def _proposal_summary(
        self,
        project_id: uuid.UUID,
        partner_by_id: dict,
        members: list,
    ) -> list[dict]:
        sections = self.db.scalars(
            select(ProjectProposalSection)
            .where(ProjectProposalSection.project_id == project_id)
            .order_by(ProjectProposalSection.position.asc())
        ).all()
        if not sections:
            return []
        section_ids = [s.id for s in sections]
        doc_counts: dict[uuid.UUID, int] = {}
        if section_ids:
            doc_counts = dict(
                self.db.execute(
                    select(ProjectDocument.proposal_section_id, func.count(ProjectDocument.id))
                    .where(
                        ProjectDocument.project_id == project_id,
                        ProjectDocument.proposal_section_id.in_(section_ids),
                    )
                    .group_by(ProjectDocument.proposal_section_id)
                ).all()
            )
        member_by_id = {m.id: m for m in members}
        return [
            {
                "key": s.key,
                "title": s.title,
                "status": s.status,
                "required": s.required,
                "owner": member_by_id[s.owner_member_id].full_name if s.owner_member_id and s.owner_member_id in member_by_id else None,
                "reviewer": member_by_id[s.reviewer_member_id].full_name if s.reviewer_member_id and s.reviewer_member_id in member_by_id else None,
                "due_date": s.due_date.isoformat() if s.due_date else None,
                "linked_docs": int(doc_counts.get(s.id, 0)),
            }
            for s in sections
        ]

    def _query_tokens(self, text: str) -> list[str]:
        raw = re.split(r"[^a-zA-Z0-9]+", (text or "").lower())
        dedup: list[str] = []
        for token in raw:
            if len(token) < 3:
                continue
            if token in dedup:
                continue
            dedup.append(token)
        return dedup

    def _snippet(self, content: str, max_len: int = 220) -> str:
        text = " ".join((content or "").split())
        if len(text) <= max_len:
            return text
        return f"{text[:max_len - 1].rstrip()}…"
