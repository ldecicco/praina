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
from app.models.project import Project
from app.models.work import Deliverable, Milestone, Task, WorkPackage, deliverable_wps, milestone_wps
from app.services.onboarding_service import ConflictError, NotFoundError, ValidationError

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
MAX_CITATIONS = 3
MAX_CHUNK_SCAN = 400
DOCUMENT_REF_RE = re.compile(r"(?<!\w)#([A-Za-z0-9._-]+)")


class ProjectChatService:
    def __init__(self, db: Session):
        self.db = db

    def list_rooms(self, project_id: uuid.UUID, user_id: uuid.UUID) -> list[ProjectChatRoom]:
        role = self._get_user_project_role(project_id, user_id)
        if role not in READ_ROLES:
            raise ValidationError("Insufficient role to read project chat.")
        self._ensure_default_room(project_id)

        rooms = self.db.scalars(
            select(ProjectChatRoom)
            .where(ProjectChatRoom.project_id == project_id, ProjectChatRoom.is_archived.is_(False))
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

        rel = ProjectChatRoomMember(room_id=room.id, user_id=target_user_id)
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
            select(ProjectChatRoomMember).where(ProjectChatRoomMember.room_id == room.id, ProjectChatRoomMember.user_id == target_user_id)
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

        stmt = select(ProjectChatMessage).where(
            ProjectChatMessage.project_id == project_id,
            ProjectChatMessage.room_id == room.id,
        ).order_by(ProjectChatMessage.created_at.asc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

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
        text = content.strip()
        if not text:
            raise ValidationError("Message content cannot be empty.")
        if len(text) > 8000:
            raise ValidationError("Message content cannot exceed 8000 characters.")

        reply_to_id: uuid.UUID | None = None
        if reply_to_message_id:
            reply_target = self._get_message(project_id, room.id, reply_to_message_id)
            reply_to_id = reply_target.id

        message = ProjectChatMessage(
            project_id=project_id,
            room_id=room.id,
            sender_user_id=user_id,
            reply_to_message_id=reply_to_id,
            content=text,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
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

        target = self._get_message(project_id, room.id, message_id)
        symbol = emoji.strip()
        if not symbol:
            raise ValidationError("Reaction emoji cannot be empty.")
        if len(symbol) > 32:
            raise ValidationError("Reaction emoji is too long.")

        existing = self.db.scalar(
            select(ProjectChatMessageReaction).where(
                ProjectChatMessageReaction.message_id == target.id,
                ProjectChatMessageReaction.user_id == user_id,
                ProjectChatMessageReaction.emoji == symbol,
            )
        )
        if existing:
            self.db.delete(existing)
        else:
            self.db.add(ProjectChatMessageReaction(message_id=target.id, user_id=user_id, emoji=symbol))

        self.db.commit()
        self.db.refresh(target)
        return target

    def get_message(self, project_id: uuid.UUID, room_id: uuid.UUID, user_id: uuid.UUID, message_id: uuid.UUID) -> ProjectChatMessage:
        role = self._get_user_project_role(project_id, user_id)
        room = self._get_room(project_id, room_id)
        if role not in READ_ROLES or not self._can_access_room(project_id, room.id, user_id, role):
            raise ValidationError("Insufficient role or membership to read room messages.")
        return self._get_message(project_id, room.id, message_id)

    def message_lookup(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, ProjectChatMessage]:
        if not message_ids:
            return {}
        rows = self.db.scalars(select(ProjectChatMessage).where(ProjectChatMessage.id.in_(message_ids))).all()
        return {item.id: item for item in rows}

    def reaction_summary_by_message(self, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
        if not message_ids:
            return {}
        rows = self.db.scalars(
            select(ProjectChatMessageReaction)
            .where(ProjectChatMessageReaction.message_id.in_(message_ids))
            .order_by(ProjectChatMessageReaction.created_at.asc())
        ).all()
        by_message: dict[uuid.UUID, dict[str, list[uuid.UUID]]] = {}
        for row in rows:
            bucket = by_message.setdefault(row.message_id, {})
            bucket.setdefault(row.emoji, []).append(row.user_id)

        output: dict[uuid.UUID, list[dict]] = {}
        for message_id, by_emoji in by_message.items():
            summary = [
                {
                    "emoji": emoji,
                    "count": len(user_ids),
                    "user_ids": [str(user_id) for user_id in sorted(user_ids, key=str)],
                }
                for emoji, user_ids in by_emoji.items()
            ]
            summary.sort(key=lambda item: (-item["count"], item["emoji"]))
            output[message_id] = summary
        return output

    def create_bot_message(self, project_id: uuid.UUID, room_id: uuid.UUID, content: str) -> ProjectChatMessage:
        room = self._get_room(project_id, room_id)
        text = content.strip()
        if not text:
            raise ValidationError("Bot message content cannot be empty.")
        bot_user = self.ensure_bot_user()
        message = ProjectChatMessage(
            project_id=project_id,
            room_id=room.id,
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
            .where(ProjectChatMessage.project_id == project_id, ProjectChatMessage.room_id == room_id)
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
                    ProjectChatRoom.project_id == project_id, ProjectChatRoom.is_archived.is_(False)
                )
            )
            or 0
        )
        return {
            "project_id": str(project.id),
            "project_code": project.code,
            "project_title": project.title,
            "project_status": project.status.value if hasattr(project.status, "value") else str(project.status),
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
            "proposal_sections": self._proposal_summary(project_id, partner_by_id, members),
        }

    def retrieve_citations(self, project_id: uuid.UUID, prompt: str) -> list[dict]:
        doc_refs = self.extract_document_references(project_id, prompt)
        tokens = self._query_tokens(doc_refs["cleaned_prompt"])
        rows = self.db.execute(
            select(DocumentChunk, ProjectDocument)
            .join(ProjectDocument, DocumentChunk.document_id == ProjectDocument.id)
            .where(
                ProjectDocument.project_id == project_id,
                ProjectDocument.status == DocumentStatus.indexed.value,
            )
            .order_by(ProjectDocument.updated_at.desc(), DocumentChunk.chunk_index.asc())
            .limit(MAX_CHUNK_SCAN)
        ).all()
        if not rows:
            return []

        referenced_keys = {str(item) for item in doc_refs["document_keys"]}
        if referenced_keys:
            rows = [
                (chunk, document)
                for chunk, document in rows
                if str(document.document_key) in referenced_keys
            ]
            if not rows:
                return []

        ranked: list[tuple[int, DocumentChunk, ProjectDocument]] = []
        for chunk, document in rows:
            chunk_text = (chunk.content or "").lower()
            if not chunk_text:
                continue
            score = sum(chunk_text.count(token) for token in tokens)
            if score <= 0 and tokens:
                continue
            ranked.append((score, chunk, document))

        if not ranked:
            ranked = [(0, chunk, document) for chunk, document in rows[:MAX_CITATIONS]]

        ranked.sort(key=lambda item: item[0], reverse=True)
        top = ranked[:MAX_CITATIONS]
        return [
            {
                "document_id": str(document.id),
                "document_key": str(document.document_key),
                "title": document.title,
                "version": document.version,
                "chunk_index": chunk.chunk_index,
                "snippet": self._snippet(chunk.content),
            }
            for _, chunk, document in top
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
        return "\n".join(lines)

    @staticmethod
    def has_bot_mention(content: str) -> bool:
        return BOT_MENTION_RE.search(content or "") is not None

    @staticmethod
    def strip_bot_mentions(content: str) -> str:
        cleaned = BOT_MENTION_RE.sub(" ", content or "")
        return " ".join(cleaned.split()).strip()

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
            select(ProjectChatRoomMember.user_id).where(ProjectChatRoomMember.room_id == room_id)
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

    def _get_user_project_role(self, project_id: uuid.UUID, user_id: uuid.UUID) -> str:
        user = self.db.get(UserAccount, user_id)
        if user and user.platform_role == PlatformRole.super_admin.value:
            return ProjectRole.project_owner.value
        self._get_project(project_id)
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
            )
        )
        if not room:
            raise NotFoundError("Room not found in project.")
        return room

    def _get_message(self, project_id: uuid.UUID, room_id: uuid.UUID, message_id: uuid.UUID) -> ProjectChatMessage:
        message = self.db.scalar(
            select(ProjectChatMessage).where(
                ProjectChatMessage.id == message_id,
                ProjectChatMessage.project_id == project_id,
                ProjectChatMessage.room_id == room_id,
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
