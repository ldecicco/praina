import re
import shlex
import logging
import uuid
from calendar import monthrange
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.chat_action_extraction_agent import ChatActionExtractionAgent
from app.agents.chat_assistant_agent import ChatAssistantAgent
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.auth import UserAccount
from app.models.audit import AuditEvent
from app.models.chat import ChatActionProposal, ChatConversation, ChatMessage
from app.models.document import DocumentStatus, ProjectDocument
from app.models.proposal import ProjectProposalSection
from app.models.meeting import MeetingRecord
from app.models.organization import PartnerOrganization, TeamMember
from app.models.project import Project
from app.models.course import Course, CourseMaterial, CourseTeachingAssistant
from app.models.teaching import (
    TeachingProgressReport,
    TeachingProjectArtifact,
    TeachingProjectBlocker,
    TeachingProjectMilestone,
    TeachingProjectProfile,
    TeachingProjectStudent,
)
from app.models.work import (
    Deliverable,
    Milestone,
    ProjectRisk,
    Task,
    WorkExecutionStatus,
    WorkPackage,
    deliverable_collaborators,
    deliverable_wps,
    milestone_collaborators,
    milestone_wps,
    task_collaborators,
    wp_collaborators,
)
from app.schemas.work import (
    DeliverableCreate,
    DeliverableUpdate,
    MilestoneCreate,
    MilestoneUpdate,
    TaskCreate,
    TaskUpdate,
    WorkPackageCreate,
    WorkPackageUpdate,
)
from app.schemas.project import ProjectUpdate
from app.services.onboarding_service import NotFoundError, OnboardingService, ValidationError
from app.services.project_chat_service import ProjectChatService

MAX_CITATIONS = 3
PROJECT_CHAT_ROOM_CONVERSATION_PREFIX = "__project_chat_room__"
logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: Session):
        self.db = db
        self.assistant_agent = ChatAssistantAgent()
        self.action_extraction_agent = ChatActionExtractionAgent()

    def list_conversations(self, project_id: uuid.UUID, page: int, page_size: int) -> tuple[list[ChatConversation], int]:
        self._get_project(project_id)
        stmt = (
            select(ChatConversation)
            .where(
                ChatConversation.project_id == project_id,
                ~ChatConversation.title.like(f"{PROJECT_CHAT_ROOM_CONVERSATION_PREFIX}%"),
            )
            .order_by(ChatConversation.updated_at.desc())
        )
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def create_conversation(
        self, project_id: uuid.UUID, title: str | None, created_by_member_id: uuid.UUID | None
    ) -> ChatConversation:
        self._get_project(project_id)
        self._validate_member(project_id, created_by_member_id)
        conversation = ChatConversation(
            project_id=project_id,
            title=(title or "New conversation").strip() or "New conversation",
            created_by_member_id=created_by_member_id,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update_conversation(
        self, project_id: uuid.UUID, conversation_id: uuid.UUID, title: str
    ) -> ChatConversation:
        conversation = self._get_conversation(project_id, conversation_id)
        conversation.title = title.strip() or conversation.title
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete_conversation(self, project_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        conversation = self._get_conversation(project_id, conversation_id)
        self.db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id).delete()
        self.db.delete(conversation)
        self.db.commit()

    def list_messages(
        self, project_id: uuid.UUID, conversation_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[ChatMessage], int]:
        self._get_conversation(project_id, conversation_id)
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.project_id == project_id, ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
        )
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(rows), total

    def post_message(
        self, project_id: uuid.UUID, conversation_id: uuid.UUID, content: str, created_by_member_id: uuid.UUID | None
    ) -> tuple[ChatMessage, ChatMessage]:
        conversation = self._get_conversation(project_id, conversation_id)
        project = self._get_project(project_id)
        self._validate_member(project_id, created_by_member_id)

        text = content.strip()
        if not text:
            raise ValidationError("Message content cannot be empty.")

        user_message = ChatMessage(
            conversation_id=conversation.id,
            project_id=project_id,
            role="user",
            content=text,
            citations=[],
            created_by_member_id=created_by_member_id,
        )
        self.db.add(user_message)

        command_reply = self._handle_chat_command(project_id, conversation_id, text, created_by_member_id)
        if command_reply is not None:
            assistant_text = command_reply
            citations: list[dict[str, Any]] = []
            cards: list[dict[str, Any]] = []
        else:
            citations = self._retrieve_citations(project_id, text)
            context = self._project_context(project)
            recent_messages = self._recent_messages(project_id, conversation.id)
            assistant_text = self.assistant_agent.generate(
                user_prompt=text,
                project_context=context,
                recent_messages=recent_messages,
                evidence=citations,
            )
            if not assistant_text:
                assistant_text = self._compose_fallback_response(project, text, citations, context)
            cards = self._build_result_cards(project_id, text, context)

        assistant_message = ChatMessage(
            conversation_id=conversation.id,
            project_id=project_id,
            role="assistant",
            content=assistant_text,
            citations=citations,
            cards=cards,
            created_by_member_id=None,
        )
        self.db.add(assistant_message)

        if conversation.title == "New conversation":
            conversation.title = self._conversation_title_from_prompt(text)

        self.db.commit()
        self.db.refresh(user_message)
        self.db.refresh(assistant_message)
        return user_message, assistant_message

    def project_context_for_assistant(self, project_id: uuid.UUID) -> dict[str, object]:
        project = self._get_project(project_id)
        return self._project_context(project)

    def _handle_chat_command(
        self,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message: str,
        created_by_member_id: uuid.UUID | None,
    ) -> str | None:
        stripped = message.strip()
        if not stripped:
            return None

        confirm_match = re.fullmatch(r"(?i)(confirm|approve)(?:\s+([0-9a-f-]{36}|last))?", stripped)
        if confirm_match:
            token = confirm_match.group(2)
            proposal_id = self._resolve_proposal_token(project_id, conversation_id, token)
            if not proposal_id:
                return self._no_pending_message(project_id, conversation_id, "confirm")
            return self._confirm_proposal(project_id, conversation_id, proposal_id)

        cancel_match = re.fullmatch(r"(?i)(cancel|reject)(?:\s+([0-9a-f-]{36}|last))?", stripped)
        if cancel_match:
            token = cancel_match.group(2)
            proposal_id = self._resolve_proposal_token(project_id, conversation_id, token)
            if not proposal_id:
                return self._no_pending_message(project_id, conversation_id, "cancel")
            return self._cancel_proposal(project_id, conversation_id, proposal_id)

        parsed, extraction_message = self._parse_natural_language_action(project_id, stripped)
        if extraction_message is not None:
            return extraction_message
        if parsed is None:
            return None

        try:
            proposal = self._build_action_proposal(
                project_id=project_id,
                conversation_id=conversation_id,
                created_by_member_id=created_by_member_id,
                parsed=parsed,
            )
        except (ValidationError, NotFoundError) as exc:
            return f"{exc}\n{self._command_help()}"

        self.db.add(proposal)
        self.db.flush()
        return (
            f"Pending action created.\nProposal ID: {proposal.id}\n{proposal.summary}\n\n"
            f"Reply with `confirm {proposal.id}` to execute or `cancel {proposal.id}` to discard."
        )

    def _parse_natural_language_action(
        self, project_id: uuid.UUID, message: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            project_context = ProjectChatService(self.db).project_context_for_agent(project_id)
        except Exception:
            project_context = {"project_id": str(project_id)}

        extracted = self.action_extraction_agent.extract(user_prompt=message, project_context=project_context)
        if not extracted:
            if self._looks_like_action_request(message):
                detail = self.action_extraction_agent.last_error or "unknown extraction failure"
                logger.warning(
                    "NL action extraction failed for project=%s message=%r detail=%s",
                    project_id,
                    message[:200],
                    detail,
                )
                return (
                    None,
                    (
                        "I could not parse this action request with the LLM. "
                        f"{detail}. Verify Ollama is running at `{settings.ollama_base_url}` "
                        f"and model `{settings.ollama_model}` is available."
                    ),
                )
            return None, None
        if isinstance(extracted.get("actions"), list):
            batch_actions: list[dict[str, Any]] = []
            for item in extracted.get("actions", []):
                if not isinstance(item, dict):
                    continue
                action_type = str(item.get("action_type", "")).strip().lower()
                entity_type = str(item.get("entity_type", "")).strip().lower()
                if action_type not in {"create", "update"} or entity_type not in {
                    "project",
                    "work_package",
                    "task",
                    "deliverable",
                    "milestone",
                }:
                    continue
                fields = self._normalize_extracted_fields(item.get("fields", {}))
                if action_type == "update" and "target" not in fields and "code" in fields:
                    fields["target"] = fields["code"]
                self._apply_extraction_defaults(project_id, action_type, entity_type, fields)
                missing_fields = [part for part in item.get("missing_fields", []) if part]
                missing_fields = sorted(set(str(part).strip().lower() for part in missing_fields if str(part).strip()))
                if missing_fields:
                    return (
                        None,
                        "I can prepare this batch action, but I still need: "
                        + ", ".join(f"`{field}`" for field in missing_fields)
                        + ".",
                    )
                if fields:
                    batch_actions.append(
                        {"action_type": action_type, "entity_type": entity_type, "fields": fields}
                    )
            if batch_actions:
                return {"batch_actions": batch_actions}, None
            return None, None
        logger.info(
            "NL action extraction output project=%s action=%s entity=%s fields=%s missing=%s",
            project_id,
            extracted.get("action_type"),
            extracted.get("entity_type"),
            extracted.get("fields"),
            extracted.get("missing_fields"),
        )
        if not extracted.get("is_action_request"):
            return None, None

        action_type = str(extracted.get("action_type", "")).strip().lower()
        entity_type = str(extracted.get("entity_type", "")).strip().lower()
        if action_type not in {"create", "update"} or entity_type not in {
            "project",
            "work_package",
            "task",
            "deliverable",
            "milestone",
        }:
            return None, None

        fields = self._normalize_extracted_fields(extracted.get("fields", {}))
        if action_type == "update" and "target" not in fields and "code" in fields:
            fields["target"] = fields["code"]

        self._apply_extraction_defaults(project_id, action_type, entity_type, fields)

        missing_fields = [item for item in extracted.get("missing_fields", []) if item]
        missing_fields = sorted(set(str(item).strip().lower() for item in missing_fields if str(item).strip()))
        if not fields and not missing_fields:
            return None, None
        if missing_fields:
            return (
                None,
                "I can prepare this action, but I still need: "
                + ", ".join(f"`{field}`" for field in missing_fields)
                + ".",
            )

        return {"action_type": action_type, "entity_type": entity_type, "fields": fields}, None

    def _looks_like_action_request(self, message: str) -> bool:
        text = message.lower()
        has_action = any(token in text for token in ["add", "create", "update", "edit", "modify", "change"])
        has_entity = any(
            token in text
            for token in [
                "project",
                "settings",
                "reporting",
                "reporting period",
                "reporting date",
                "duration",
                "start date",
                "wp",
                "work package",
                "task",
                "deliverable",
                "milestone",
            ]
        )
        return has_action and has_entity

    def _normalize_extracted_fields(self, raw_fields: dict[str, Any]) -> dict[str, str]:
        aliases = {
            "leader_partner": "leader",
            "leader_partner_short_name": "leader",
            "responsible_person": "responsible",
            "responsible_person_name": "responsible",
            "responsible_email": "responsible",
            "wp_code": "wp",
            "wp_codes": "wps",
            "work_package": "wp",
            "work_packages": "wps",
            "target_code": "target",
            "reporting_periods": "reporting_dates",
            "reporting_period": "reporting_dates",
            "reporting_date": "reporting_dates",
            "duration": "duration_months",
            "project_duration": "duration_months",
        }
        fields: dict[str, str] = {}
        for key, value in raw_fields.items():
            normalized_key = aliases.get(str(key).strip().lower(), str(key).strip().lower())
            if not normalized_key:
                continue
            if value is None:
                continue
            if isinstance(value, list):
                token = ",".join(str(item).strip() for item in value if str(item).strip())
            else:
                token = str(value).strip()
            if not token:
                continue
            if normalized_key in {"start_month", "end_month", "due_month", "duration_months"}:
                month_match = re.fullmatch(r"(?i)m?(\d+)", token)
                if month_match:
                    token = month_match.group(1)
            fields[normalized_key] = token
        return fields

    def _apply_extraction_defaults(
        self,
        project_id: uuid.UUID,
        action_type: str,
        entity_type: str,
        fields: dict[str, str],
    ) -> None:
        if action_type != "create" or entity_type != "task":
            return

        wp_code = fields.get("wp")
        if not wp_code:
            return
        wp = self.db.scalar(
            select(WorkPackage).where(
                WorkPackage.project_id == project_id,
                WorkPackage.code.ilike(wp_code.strip()),
            )
        )
        if not wp:
            return
        if "start_month" not in fields:
            fields["start_month"] = str(wp.start_month)
        if "end_month" not in fields:
            fields["end_month"] = str(wp.end_month)

    def _parse_action_command(self, message: str) -> dict[str, Any] | None:
        match = re.match(
            r"(?i)^\s*(add|create|modify|update|edit|change)\s+"
            r"(project|wp|workpackage|work-package|task|deliverable|milestone)\b(.*)$",
            message,
        )
        if not match:
            return None

        verb = match.group(1).lower()
        entity_raw = match.group(2).lower()
        remainder = match.group(3).strip()
        if not remainder:
            raise ValidationError(self._command_help())

        action_type = "create" if verb in {"add", "create"} else "update"
        entity_map = {
            "project": "project",
            "wp": "work_package",
            "workpackage": "work_package",
            "work-package": "work_package",
            "task": "task",
            "deliverable": "deliverable",
            "milestone": "milestone",
        }
        entity_type = entity_map[entity_raw]
        fields = self._parse_key_values(remainder)
        return {"action_type": action_type, "entity_type": entity_type, "fields": fields}

    def _parse_key_values(self, raw: str) -> dict[str, str]:
        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            raise ValidationError("Invalid command format. Use key=value pairs and quote values with spaces.") from exc

        fields: dict[str, str] = {}
        for token in tokens:
            if "=" not in token:
                raise ValidationError(f"Invalid token `{token}`. Expected key=value.")
            key, value = token.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if not key:
                raise ValidationError(f"Invalid token `{token}`.")
            fields[key] = value
        return fields

    def _build_action_proposal(
        self,
        *,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        created_by_member_id: uuid.UUID | None,
        parsed: dict[str, Any],
    ) -> ChatActionProposal:
        if parsed.get("batch_actions"):
            return self._build_batch_action_proposal(
                project_id=project_id,
                conversation_id=conversation_id,
                created_by_member_id=created_by_member_id,
                batch_actions=parsed["batch_actions"],
            )

        action_type = parsed["action_type"]
        entity_type = parsed["entity_type"]
        fields = parsed["fields"]

        if entity_type == "project":
            payload, summary, target_code = self._proposal_for_project(project_id, action_type, fields)
        elif entity_type == "work_package":
            payload, summary, target_code = self._proposal_for_wp(project_id, action_type, fields)
        elif entity_type == "task":
            payload, summary, target_code = self._proposal_for_task(project_id, action_type, fields)
        elif entity_type == "deliverable":
            payload, summary, target_code = self._proposal_for_deliverable(project_id, action_type, fields)
        elif entity_type == "milestone":
            payload, summary, target_code = self._proposal_for_milestone(project_id, action_type, fields)
        else:
            raise ValidationError("Unsupported entity type.")

        return ChatActionProposal(
            conversation_id=conversation_id,
            project_id=project_id,
            requested_by_member_id=created_by_member_id,
            status="pending",
            action_type=action_type,
            entity_type=entity_type,
            target_code=target_code,
            summary=summary,
            action_payload=payload,
            result_json={},
            error_text=None,
        )

    def _build_batch_action_proposal(
        self,
        *,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        created_by_member_id: uuid.UUID | None,
        batch_actions: list[dict[str, Any]],
    ) -> ChatActionProposal:
        items: list[dict[str, Any]] = []
        summary_lines = ["Execute ordered batch:"]
        target_codes: list[str] = []
        pending_wp_codes = {
            item["fields"].get("code", "").strip().lower()
            for item in batch_actions
            if item.get("action_type") == "create" and item.get("entity_type") == "work_package"
        }
        for index, item in enumerate(batch_actions, start=1):
            action_type = item["action_type"]
            entity_type = item["entity_type"]
            fields = item["fields"]
            payload, summary, target_code = self._proposal_for_entity(
                project_id=project_id,
                action_type=action_type,
                entity_type=entity_type,
                fields=fields,
                allow_deferred_wp_refs=True,
                pending_wp_codes=pending_wp_codes,
            )
            items.append(payload)
            summary_lines.append(f"{index}. {summary}")
            if target_code:
                target_codes.append(target_code)
        return ChatActionProposal(
            conversation_id=conversation_id,
            project_id=project_id,
            requested_by_member_id=created_by_member_id,
            status="pending",
            action_type="batch",
            entity_type="batch",
            target_code=", ".join(target_codes[:6]) if target_codes else None,
            summary="\n".join(summary_lines),
            action_payload={"operation": "batch", "actions": items},
            result_json={},
            error_text=None,
        )

    def _proposal_for_entity(
        self,
        *,
        project_id: uuid.UUID,
        action_type: str,
        entity_type: str,
        fields: dict[str, str],
        allow_deferred_wp_refs: bool = False,
        pending_wp_codes: set[str] | None = None,
    ) -> tuple[dict, str, str | None]:
        if entity_type == "project":
            return self._proposal_for_project(project_id, action_type, fields)
        if entity_type == "work_package":
            return self._proposal_for_wp(project_id, action_type, fields)
        if entity_type == "task":
            return self._proposal_for_task(
                project_id,
                action_type,
                fields,
                allow_deferred_wp_refs=allow_deferred_wp_refs,
                pending_wp_codes=pending_wp_codes or set(),
            )
        if entity_type == "deliverable":
            return self._proposal_for_deliverable(project_id, action_type, fields)
        if entity_type == "milestone":
            return self._proposal_for_milestone(project_id, action_type, fields)
        raise ValidationError("Unsupported entity type.")

    def _proposal_for_project(
        self, project_id: uuid.UUID, action_type: str, fields: dict[str, str]
    ) -> tuple[dict, str, str | None]:
        if action_type != "update":
            raise ValidationError("Project actions currently support update only.")

        project = self._get_project(project_id)
        data: dict[str, Any] = {}

        if "code" in fields:
            data["code"] = fields["code"]
        if "title" in fields:
            data["title"] = fields["title"]
        if "description" in fields:
            data["description"] = fields["description"]
        if "start_date" in fields:
            data["start_date"] = self._project_date_field(project, fields, "start_date").isoformat()
        if "duration_months" in fields:
            data["duration_months"] = self._int_field(fields, "duration_months")
        if "reporting_dates" in fields:
            data["reporting_dates"] = [
                item.isoformat() for item in self._project_date_list_field(project, fields, "reporting_dates")
            ]

        if not data:
            raise ValidationError(
                "Project update requires at least one of: code, title, description, start_date, duration_months, reporting_dates."
            )

        summary_parts: list[str] = []
        if "code" in data:
            summary_parts.append(f"code={data['code']}")
        if "title" in data:
            summary_parts.append(f"title={data['title']}")
        if "start_date" in data:
            summary_parts.append(f"start_date={data['start_date']}")
        if "duration_months" in data:
            summary_parts.append(f"duration={data['duration_months']} months")
        if "reporting_dates" in data:
            summary_parts.append("reporting_dates=" + ", ".join(data["reporting_dates"]))
        if "description" in data and "title" not in data:
            summary_parts.append("description updated")

        payload = {
            "operation": "update",
            "entity_type": "project",
            "target_id": str(project.id),
            "target_code": project.code,
            "data": data,
        }
        summary = f"Update project {project.code}: " + "; ".join(summary_parts) + "."
        return payload, summary, project.code

    def _proposal_for_wp(self, project_id: uuid.UUID, action_type: str, fields: dict[str, str]) -> tuple[dict, str, str | None]:
        if action_type == "create":
            assignment = self._assignment_for_create(project_id, fields)
            code = self._required(fields, "code")
            title = self._required(fields, "title")
            start_month = self._int_field(fields, "start_month")
            end_month = self._int_field(fields, "end_month")
            payload = {
                "operation": "create",
                "entity_type": "work_package",
                "data": {
                    "code": code,
                    "title": title,
                    "description": fields.get("description"),
                    "start_month": start_month,
                    "end_month": end_month,
                    "assignment": assignment,
                },
            }
            summary = f"Create WP {code} ({title}) in M{start_month}-M{end_month}."
            return payload, summary, code

        target_code = self._required(fields, "target")
        wp = self._get_by_code(project_id, WorkPackage, target_code, "Work package")
        assignment = self._assignment_for_update(
            project_id, fields, wp.leader_organization_id, wp.responsible_person_id, wp_collaborators, "wp_id", wp.id
        )
        code = fields.get("code", wp.code)
        title = fields.get("title", wp.title)
        start_month = self._int_field(fields, "start_month", wp.start_month)
        end_month = self._int_field(fields, "end_month", wp.end_month)
        payload = {
            "operation": "update",
            "entity_type": "work_package",
            "target_id": str(wp.id),
            "target_code": wp.code,
            "data": {
                "code": code,
                "title": title,
                "description": fields.get("description", wp.description),
                "start_month": start_month,
                "end_month": end_month,
                "assignment": assignment,
            },
        }
        summary = f"Update WP {wp.code} -> {code} ({title}) in M{start_month}-M{end_month}."
        return payload, summary, wp.code

    def _proposal_for_task(
        self,
        project_id: uuid.UUID,
        action_type: str,
        fields: dict[str, str],
        *,
        allow_deferred_wp_refs: bool = False,
        pending_wp_codes: set[str] | None = None,
    ) -> tuple[dict, str, str | None]:
        if action_type == "create":
            assignment = self._assignment_for_create(project_id, fields)
            wp_code = self._required(fields, "wp")
            code = self._required(fields, "code")
            title = self._required(fields, "title")
            start_month = self._int_field(fields, "start_month")
            end_month = self._int_field(fields, "end_month")
            wp = None
            try:
                wp = self._get_by_code(project_id, WorkPackage, wp_code, "Work package")
            except NotFoundError:
                if not (allow_deferred_wp_refs and wp_code.strip().lower() in (pending_wp_codes or set())):
                    raise
            payload = {
                "operation": "create",
                "entity_type": "task",
                "data": {
                    "code": code,
                    "title": title,
                    "description": fields.get("description"),
                    "start_month": start_month,
                    "end_month": end_month,
                    "assignment": assignment,
                },
            }
            if wp:
                payload["data"]["wp_id"] = str(wp.id)
            else:
                payload["data"]["wp_code"] = wp_code
            summary = f"Create task {code} under {wp.code if wp else wp_code} in M{start_month}-M{end_month}."
            return payload, summary, code

        target_code = self._required(fields, "target")
        task = self._get_by_code(project_id, Task, target_code, "Task")
        wp = self.db.scalar(select(WorkPackage).where(WorkPackage.id == task.wp_id, WorkPackage.project_id == project_id))
        if not wp:
            raise NotFoundError("Parent work package not found for task.")
        assignment = self._assignment_for_update(
            project_id, fields, task.leader_organization_id, task.responsible_person_id, task_collaborators, "task_id", task.id
        )
        code = fields.get("code", task.code)
        title = fields.get("title", task.title)
        start_month = self._int_field(fields, "start_month", task.start_month)
        end_month = self._int_field(fields, "end_month", task.end_month)
        payload = {
            "operation": "update",
            "entity_type": "task",
            "target_id": str(task.id),
            "target_code": task.code,
            "data": {
                "code": code,
                "title": title,
                "description": fields.get("description", task.description),
                "start_month": start_month,
                "end_month": end_month,
                "assignment": assignment,
            },
        }
        summary = f"Update task {task.code} -> {code} ({title}) in WP {wp.code}."
        return payload, summary, task.code

    def _proposal_for_deliverable(
        self, project_id: uuid.UUID, action_type: str, fields: dict[str, str]
    ) -> tuple[dict, str, str | None]:
        if action_type == "create":
            assignment = self._assignment_for_create(project_id, fields)
            wp_ids, wp_codes = self._resolve_wp_list(project_id, fields, required=True)
            code = self._required(fields, "code")
            title = self._required(fields, "title")
            due_month = self._int_field(fields, "due_month")
            payload = {
                "operation": "create",
                "entity_type": "deliverable",
                "data": {
                    "wp_ids": [str(item) for item in wp_ids],
                    "code": code,
                    "title": title,
                    "description": fields.get("description"),
                    "due_month": due_month,
                    "assignment": assignment,
                },
            }
            summary = f"Create deliverable {code} due M{due_month} for WP(s): {', '.join(wp_codes)}."
            return payload, summary, code

        target_code = self._required(fields, "target")
        deliverable = self._get_by_code(project_id, Deliverable, target_code, "Deliverable")
        assignment = self._assignment_for_update(
            project_id,
            fields,
            deliverable.leader_organization_id,
            deliverable.responsible_person_id,
            deliverable_collaborators,
            "deliverable_id",
            deliverable.id,
        )
        existing_wp_ids = self._get_related_wps(deliverable_wps, "deliverable_id", deliverable.id)
        wp_ids = existing_wp_ids
        wp_codes = self._wp_codes_by_ids(existing_wp_ids)
        if "wp" in fields or "wps" in fields:
            wp_ids, wp_codes = self._resolve_wp_list(project_id, fields, required=True)

        code = fields.get("code", deliverable.code)
        title = fields.get("title", deliverable.title)
        due_month = self._int_field(fields, "due_month", deliverable.due_month)
        payload = {
            "operation": "update",
            "entity_type": "deliverable",
            "target_id": str(deliverable.id),
            "target_code": deliverable.code,
            "data": {
                "wp_ids": [str(item) for item in wp_ids],
                "code": code,
                "title": title,
                "description": fields.get("description", deliverable.description),
                "due_month": due_month,
                "assignment": assignment,
            },
        }
        summary = f"Update deliverable {deliverable.code} -> {code}, due M{due_month}, WP(s): {', '.join(wp_codes)}."
        return payload, summary, deliverable.code

    def _proposal_for_milestone(
        self, project_id: uuid.UUID, action_type: str, fields: dict[str, str]
    ) -> tuple[dict, str, str | None]:
        if action_type == "create":
            assignment = self._assignment_for_create(project_id, fields)
            wp_ids, wp_codes = self._resolve_wp_list(project_id, fields, required=False)
            code = self._required(fields, "code")
            title = self._required(fields, "title")
            due_month = self._int_field(fields, "due_month")
            payload = {
                "operation": "create",
                "entity_type": "milestone",
                "data": {
                    "wp_ids": [str(item) for item in wp_ids],
                    "code": code,
                    "title": title,
                    "description": fields.get("description"),
                    "due_month": due_month,
                    "assignment": assignment,
                },
            }
            wp_tail = f", WP(s): {', '.join(wp_codes)}" if wp_codes else ""
            summary = f"Create milestone {code} due M{due_month}{wp_tail}."
            return payload, summary, code

        target_code = self._required(fields, "target")
        milestone = self._get_by_code(project_id, Milestone, target_code, "Milestone")
        assignment = self._assignment_for_update(
            project_id,
            fields,
            milestone.leader_organization_id,
            milestone.responsible_person_id,
            milestone_collaborators,
            "milestone_id",
            milestone.id,
        )
        existing_wp_ids = self._get_related_wps(milestone_wps, "milestone_id", milestone.id)
        wp_ids = existing_wp_ids
        wp_codes = self._wp_codes_by_ids(existing_wp_ids)
        if "wp" in fields or "wps" in fields:
            wp_ids, wp_codes = self._resolve_wp_list(project_id, fields, required=False)

        code = fields.get("code", milestone.code)
        title = fields.get("title", milestone.title)
        due_month = self._int_field(fields, "due_month", milestone.due_month)
        payload = {
            "operation": "update",
            "entity_type": "milestone",
            "target_id": str(milestone.id),
            "target_code": milestone.code,
            "data": {
                "wp_ids": [str(item) for item in wp_ids],
                "code": code,
                "title": title,
                "description": fields.get("description", milestone.description),
                "due_month": due_month,
                "assignment": assignment,
            },
        }
        wp_tail = f", WP(s): {', '.join(wp_codes)}" if wp_codes else ""
        summary = f"Update milestone {milestone.code} -> {code}, due M{due_month}{wp_tail}."
        return payload, summary, milestone.code

    def _assignment_for_create(self, project_id: uuid.UUID, fields: dict[str, str]) -> dict[str, Any]:
        leader_token = self._required(fields, "leader")
        responsible_token = self._required(fields, "responsible")
        leader = self._resolve_partner(project_id, leader_token)
        responsible = self._resolve_responsible(project_id, leader.id, responsible_token)
        collaborators = self._resolve_collaborators(project_id, fields.get("collaborators"))
        return {
            "leader_organization_id": str(leader.id),
            "responsible_person_id": str(responsible.id),
            "collaborating_partner_ids": [str(item) for item in collaborators],
        }

    def _assignment_for_update(
        self,
        project_id: uuid.UUID,
        fields: dict[str, str],
        current_leader_id: uuid.UUID,
        current_responsible_id: uuid.UUID,
        collaborators_table,
        fk_name: str,
        entity_id: uuid.UUID,
    ) -> dict[str, Any]:
        leader_id = current_leader_id
        responsible_id = current_responsible_id

        if "leader" in fields:
            leader_id = self._resolve_partner(project_id, fields["leader"]).id
            if "responsible" not in fields:
                raise ValidationError("When changing leader, also provide responsible=...")

        if "responsible" in fields:
            responsible_id = self._resolve_responsible(project_id, leader_id, fields["responsible"]).id

        if "collaborators" in fields:
            collaborator_ids = self._resolve_collaborators(project_id, fields.get("collaborators"))
        else:
            collaborator_ids = self._get_collaborators(collaborators_table, fk_name, entity_id)

        return {
            "leader_organization_id": str(leader_id),
            "responsible_person_id": str(responsible_id),
            "collaborating_partner_ids": [str(item) for item in collaborator_ids],
        }

    def _confirm_proposal(self, project_id: uuid.UUID, conversation_id: uuid.UUID, proposal_id: uuid.UUID) -> str:
        proposal = self.db.scalar(
            select(ChatActionProposal).where(
                ChatActionProposal.id == proposal_id,
                ChatActionProposal.project_id == project_id,
                ChatActionProposal.conversation_id == conversation_id,
            )
        )
        if not proposal:
            return "Proposal not found in this conversation."
        if proposal.status == "applied":
            return f"Proposal {proposal.id} was already applied."
        if proposal.status == "cancelled":
            return f"Proposal {proposal.id} is cancelled."
        if proposal.status != "pending":
            return f"Proposal {proposal.id} is in status `{proposal.status}`."

        # Governance check before execution
        try:
            from app.agents.governance_agent import GovernanceAgent

            gov_action = {
                "action_type": proposal.action_payload.get("operation", ""),
                "entity_type": proposal.action_payload.get("entity_type", ""),
                "fields": proposal.action_payload.get("data", {}),
                "entity_id": proposal.action_payload.get("target_id"),
                "project_id": str(project_id),
                "reason": proposal.action_payload.get("reason", ""),
            }
            decision = GovernanceAgent().evaluate_action(gov_action, {}, self.db)
            if not decision.allowed:
                proposal.status = "failed"
                proposal.error_text = decision.reason
                refs = ", ".join(decision.policy_refs) if decision.policy_refs else ""
                return f"Governance policy blocked this action: {decision.reason}" + (f" [{refs}]" if refs else "")
            if decision.requires_approval:
                proposal.status = "needs_approval"
                return f"This action requires additional approval: {decision.reason}"
        except Exception:
            logger.warning("Governance check failed, proceeding anyway", exc_info=True)

        try:
            result = self._execute_payload(project_id, proposal.action_payload)
            proposal.status = "applied"
            proposal.result_json = result
            proposal.error_text = None

            # Notify proposal creator
            try:
                from app.services.notification_service import NotificationService
                from app.models.organization import TeamMember as TM
                conv = self.db.get(ChatConversation, proposal.conversation_id)
                if conv and conv.created_by_member_id:
                    member = self.db.get(TM, conv.created_by_member_id)
                    if member and member.user_account_id:
                        summary = result.get("code", proposal.target_code or "unknown")
                        NotificationService(self.db).notify(
                            user_id=member.user_account_id,
                            project_id=project_id,
                            title=f"Action applied: {proposal.entity_type} {summary}",
                            body=f"Your proposed {proposal.action_type} was confirmed and applied.",
                            link_type=proposal.entity_type,
                            link_id=uuid.UUID(result["id"]) if result.get("id") else None,
                        )
            except Exception:
                logger.warning("Failed to send proposal-applied notification", exc_info=True)

            if proposal.action_type == "batch":
                applied_codes = result.get("applied_codes", "")
                return f"Confirmed. Batch processed successfully: {applied_codes}."
            code = result.get("code", proposal.target_code or "")
            return f"Confirmed. {proposal.entity_type.replace('_', ' ').title()} `{code}` processed successfully."
        except (ValidationError, NotFoundError) as exc:
            proposal.status = "failed"
            proposal.error_text = str(exc)
            return f"Execution failed: {exc}"
        except Exception as exc:  # pragma: no cover
            proposal.status = "failed"
            proposal.error_text = str(exc)
            return f"Execution failed: {exc}"

    def _cancel_proposal(self, project_id: uuid.UUID, conversation_id: uuid.UUID, proposal_id: uuid.UUID) -> str:
        proposal = self.db.scalar(
            select(ChatActionProposal).where(
                ChatActionProposal.id == proposal_id,
                ChatActionProposal.project_id == project_id,
                ChatActionProposal.conversation_id == conversation_id,
            )
        )
        if not proposal:
            return "Proposal not found in this conversation."
        if proposal.status == "applied":
            return f"Proposal {proposal.id} was already applied and cannot be cancelled."
        if proposal.status == "cancelled":
            return f"Proposal {proposal.id} is already cancelled."
        proposal.status = "cancelled"
        return f"Proposal {proposal.id} cancelled."

    def _execute_payload(self, project_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, str]:
        if payload.get("operation") == "batch":
            return self._execute_batch_payload(project_id, payload)

        operation = payload["operation"]
        entity_type = payload["entity_type"]
        data = payload["data"]
        target_id = payload.get("target_id")

        with SessionLocal() as action_db:
            service = OnboardingService(action_db)
            entity = self._execute_single_payload(
                action_db=action_db,
                service=service,
                project_id=project_id,
                payload=payload,
                created_refs={"work_package": {}, "task": {}, "deliverable": {}, "milestone": {}},
            )
            return {"id": str(entity.id), "code": entity.code, "title": entity.title}

    def _execute_batch_payload(self, project_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, str]:
        actions = payload.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValidationError("Batch action payload is empty.")
        with SessionLocal() as action_db:
            service = OnboardingService(action_db)
            created_refs: dict[str, dict[str, uuid.UUID]] = {
                "work_package": {},
                "task": {},
                "deliverable": {},
                "milestone": {},
            }
            last_entity = None
            applied_codes: list[str] = []
            for item in actions:
                if not isinstance(item, dict):
                    raise ValidationError("Invalid batch action item.")
                last_entity = self._execute_single_payload(
                    action_db=action_db,
                    service=service,
                    project_id=project_id,
                    payload=item,
                    created_refs=created_refs,
                )
                created_refs.setdefault(item["entity_type"], {})[last_entity.code.strip().lower()] = last_entity.id
                applied_codes.append(last_entity.code)
            if not last_entity:
                raise ValidationError("Batch action payload is empty.")
            return {
                "id": str(last_entity.id),
                "code": last_entity.code,
                "title": last_entity.title,
                "applied_codes": ", ".join(applied_codes),
            }

    def _execute_single_payload(
        self,
        *,
        action_db,
        service: OnboardingService,
        project_id: uuid.UUID,
        payload: dict[str, Any],
        created_refs: dict[str, dict[str, uuid.UUID]],
    ):
        operation = payload["operation"]
        entity_type = payload["entity_type"]
        data = dict(payload["data"])
        target_id = payload.get("target_id")
        if entity_type == "task" and operation == "create" and "wp_id" not in data:
            wp_code = str(data.pop("wp_code", "")).strip()
            if not wp_code:
                raise ValidationError("Task creation payload is missing wp reference.")
            wp_id = created_refs.get("work_package", {}).get(wp_code.lower())
            if not wp_id:
                wp = action_db.scalar(
                    select(WorkPackage).where(
                        WorkPackage.project_id == project_id,
                        func.lower(WorkPackage.code) == wp_code.lower(),
                    )
                )
                if not wp:
                    raise NotFoundError(f"Work package with code `{wp_code}` not found in project.")
                wp_id = wp.id
            data["wp_id"] = str(wp_id)

        if entity_type == "project" and operation == "update":
            return service.update_project(project_id, ProjectUpdate(**data))
        if entity_type == "work_package" and operation == "create":
            return service.create_wp(project_id, WorkPackageCreate(**data))
        if entity_type == "work_package" and operation == "update":
            return service.update_wp(project_id, uuid.UUID(target_id), WorkPackageUpdate(**data))
        if entity_type == "task" and operation == "create":
            return service.create_task(project_id, TaskCreate(**data))
        if entity_type == "task" and operation == "update":
            return service.update_task(project_id, uuid.UUID(target_id), TaskUpdate(**data))
        if entity_type == "deliverable" and operation == "create":
            return service.create_deliverable(project_id, DeliverableCreate(**data))
        if entity_type == "deliverable" and operation == "update":
            return service.update_deliverable(project_id, uuid.UUID(target_id), DeliverableUpdate(**data))
        if entity_type == "milestone" and operation == "create":
            return service.create_milestone(project_id, MilestoneCreate(**data))
        if entity_type == "milestone" and operation == "update":
            return service.update_milestone(project_id, uuid.UUID(target_id), MilestoneUpdate(**data))
        raise ValidationError("Unsupported action payload.")

    def _build_result_cards(self, project_id: uuid.UUID, prompt: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        prompt_lower = prompt.lower()
        cards: list[dict[str, Any]] = []
        if any(term in prompt_lower for term in ["risk", "blocker"]):
            for item in context.get("open_risks", [])[:3]:
                cards.append({
                    "type": "risk",
                    "title": str(item.get("code") or "Risk"),
                    "body": f"{item.get('title', '')} · {item.get('probability', '')}/{item.get('impact', '')}",
                    "action_label": "Analyze",
                    "action_prompt": f"Analyze risk {item.get('code')} and propose mitigations, owners, and due months.",
                })
        if any(term in prompt_lower for term in ["delay", "late", "review", "deliverable"]):
            for item in context.get("review_gaps", [])[:3]:
                cards.append({
                    "type": "review_gap",
                    "title": str(item.get("code") or "Deliverable"),
                    "body": ", ".join(str(x) for x in item.get("issues", [])) or "review gap",
                    "action_label": "Fix",
                    "action_prompt": f"For deliverable {item.get('code')}, propose reviewer assignment and review due month.",
                })
            overdue = context.get("overdue_work", {})
            if isinstance(overdue, dict):
                for item in overdue.get("tasks", [])[:2]:
                    cards.append({
                        "type": "overdue_task",
                        "title": str(item.get("code") or "Task"),
                        "body": f"Ended M{item.get('end_month')} · {item.get('status')}",
                        "action_label": "Assess",
                        "action_prompt": (
                            f"Assess task {item.get('code')} and explain whether it can be closed now or what still blocks closure."
                        ),
                    })
                for item in overdue.get("work_packages", [])[:2]:
                    cards.append({
                        "type": "overdue_wp",
                        "title": str(item.get("code") or "WP"),
                        "body": f"Ended M{item.get('end_month')} · {item.get('status')}",
                        "action_label": "Assess",
                        "action_prompt": (
                            f"Assess work package {item.get('code')} and explain whether it can be closed now or which open tasks still block closure."
                        ),
                    })
        if any(term in prompt_lower for term in ["report", "snapshot", "status"]):
            cards.append({
                "type": "reporting",
                "title": "Reporting Snapshot",
                "body": (
                    f"{context.get('counts', {}).get('open_risks', 0)} open risks · "
                    f"{context.get('counts', {}).get('reviews_due_soon', 0)} reviews due soon · "
                    f"{context.get('counts', {}).get('overdue_tasks', 0)} overdue tasks"
                ),
                "action_label": "Expand",
                "action_prompt": "Prepare a full reporting snapshot with delivery, risks, meetings, and recent changes.",
            })
        if any(term in prompt_lower for term in ["meeting", "minutes", "transcript"]):
            for item in context.get("recent_meetings", [])[:2]:
                cards.append({
                    "type": "meeting",
                    "title": str(item.get("title") or "Meeting"),
                    "body": str(item.get("summary") or ""),
                    "action_label": "Extract Actions",
                    "action_prompt": f"From meeting {item.get('title')}, extract actions, risks, and decisions.",
                })
        if any(term in prompt_lower for term in ["change", "recent", "activity"]):
            for item in context.get("recent_activity", [])[:2]:
                label = str(item.get("code") or item.get("entity_type") or "Activity")
                cards.append({
                    "type": "activity",
                    "title": label,
                    "body": str(item.get("event_type") or ""),
                    "action_label": "Impact",
                    "action_prompt": f"Explain the impact of recent change {label} on delivery, risks, and reporting.",
                })
        return cards[:4]

    def _date_field(self, fields: dict[str, str], key: str, default: date | None = None) -> date:
        raw = fields.get(key)
        if raw is None:
            if default is None:
                raise ValidationError(f"`{key}` is required.")
            return default
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(f"`{key}` must be in YYYY-MM-DD format.") from exc

    def _date_list_field(self, fields: dict[str, str], key: str) -> list[date]:
        raw = self._required(fields, key)
        separators = [part.strip() for part in re.split(r"[;,]", raw) if part.strip()]
        if not separators:
            raise ValidationError(f"`{key}` must include at least one date in YYYY-MM-DD format.")
        values: list[date] = []
        for item in separators:
            try:
                values.append(date.fromisoformat(item))
            except ValueError as exc:
                raise ValidationError(f"`{key}` must use YYYY-MM-DD values separated by commas.") from exc
        return values

    def _project_date_field(self, project: Project, fields: dict[str, str], key: str, default: date | None = None) -> date:
        raw = fields.get(key)
        if raw is None:
            if default is None:
                raise ValidationError(f"`{key}` is required.")
            return default
        parsed = self._parse_flexible_project_date(project, raw)
        if parsed is None:
            raise ValidationError(
                f"`{key}` must be a valid date. Supported examples: `2026-12-31`, `31/12/2026`, `Dec 31 2026`, `M6`."
            )
        return parsed

    def _project_date_list_field(self, project: Project, fields: dict[str, str], key: str) -> list[date]:
        raw = self._required(fields, key)
        items = [part.strip() for part in re.split(r"(?:,|;|\band\b)", raw, flags=re.IGNORECASE) if part.strip()]
        if not items:
            raise ValidationError(f"`{key}` must include at least one date.")
        values: list[date] = []
        for item in items:
            parsed = self._parse_flexible_project_date(project, item)
            if parsed is None:
                raise ValidationError(
                    f"`{key}` contains an invalid date `{item}`. Supported examples: `2026-12-31`, `31/12/2026`, `Dec 31 2026`, `M6`."
                )
            values.append(parsed)
        return values

    def _parse_flexible_project_date(self, project: Project, raw: str) -> date | None:
        token = raw.strip()
        if not token:
            return None

        project_month_match = re.fullmatch(r"(?i)m\s*(\d{1,3})", token)
        if project_month_match:
            return self._project_month_to_date(project.start_date, int(project_month_match.group(1)))

        try:
            return date.fromisoformat(token)
        except ValueError:
            pass

        normalized = token.replace(".", "/").strip()
        for fmt in (
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%Y-%m-%d",
            "%d %B %Y",
            "%d %b %Y",
            "%B %d %Y",
            "%b %d %Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ):
            try:
                return datetime.strptime(normalized, fmt).date()
            except ValueError:
                continue
        return None

    def _project_month_to_date(self, start_date: date, project_month: int) -> date:
        if project_month < 1:
            raise ValidationError("Project month markers must be `M1` or higher.")
        month_index = (start_date.month - 1) + (project_month - 1)
        year = start_date.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, monthrange(year, month)[1])

    def _retrieve_citations(self, project_id: uuid.UUID, prompt: str) -> list[dict[str, Any]]:
        from app.agents.retrieval_agent import RetrievalAgent

        doc_refs = ProjectChatService(self.db).extract_document_references(project_id, prompt)
        cleaned_prompt = str(doc_refs["cleaned_prompt"])
        referenced_keys = [str(k) for k in doc_refs["document_keys"]] or None

        agent = RetrievalAgent(self.db)
        results = agent.retrieve(
            query=cleaned_prompt,
            project_id=project_id,
            top_k=MAX_CITATIONS + 2,
            referenced_document_keys=referenced_keys,
        )

        citations: list[dict[str, Any]] = []
        for r in results[:MAX_CITATIONS]:
            citations.append({
                "document_id": r.source_id,
                "document_key": r.source_key,
                "title": r.title,
                "version": r.version,
                "chunk_index": r.chunk_index,
                "snippet": self._snippet(r.content),
                "source_type": r.source_type,
            })
        return citations

    def _compose_fallback_response(
        self, project: Project, prompt: str, citations: list[dict], context: dict[str, object]
    ) -> str:
        counts = context["counts"]
        prompt_lower = prompt.lower()
        doc_refs = ProjectChatService(self.db).extract_document_references(project.id, prompt)

        lines = [
            f"Project {project.code}: {project.title}",
            (
                "Current structure: "
                f"{counts.get('wps', 0)} WPs, {counts.get('tasks', 0)} tasks, "
                f"{counts.get('deliverables', 0)} deliverables, {counts.get('milestones', 0)} milestones."
            ),
            (
                f"Knowledge base: {counts['documents']} documents, "
                f"{counts['indexed_documents']} indexed for retrieval."
            ),
        ]
        if doc_refs["titles"]:
            lines.append("Referenced documents: " + ", ".join(str(item) for item in doc_refs["titles"]) + ".")
        if doc_refs["unresolved_tokens"]:
            lines.append(
                "Unresolved document references: "
                + ", ".join(f"#{token}" for token in doc_refs["unresolved_tokens"])
                + "."
            )

        if any(term in prompt_lower for term in ["risk", "critical", "delay", "late", "slip"]):
            lines.append(
                "Risk view: validate due months against WP windows and check assignment coverage for all deliverables."
            )
        overdue_work = context.get("overdue_work", {})
        if isinstance(overdue_work, dict):
            overdue_wps = overdue_work.get("work_packages", [])
            overdue_tasks = overdue_work.get("tasks", [])
            if overdue_wps or overdue_tasks:
                parts: list[str] = []
                if overdue_wps:
                    parts.append(f"{len(overdue_wps)} overdue WPs")
                if overdue_tasks:
                    parts.append(f"{len(overdue_tasks)} overdue tasks")
                lines.append("Schedule alerts: " + ", ".join(parts) + ".")
                for item in [*overdue_wps[:2], *overdue_tasks[:3]][:4]:
                    lines.append(
                        f"- {item.get('code')}: ended M{item.get('end_month')} and is still `{item.get('status')}`."
                    )
        if any(term in prompt_lower for term in ["deliverable", "milestone", "task", "wp", "work package"]):
            lines.append("I can break this down by specific WP if you name the WP code.")
        if any(term in prompt_lower for term in ["document", "proposal", "agreement", "coherence"]):
            lines.append("Document coherence checks are available on indexed excerpts and deliverable references.")

        if citations:
            lines.append("Relevant evidence found in the project knowledge base.")
        else:
            lines.append("No indexed evidence matched this prompt yet. Reindex documents to improve grounded answers.")

        lines.append(self._command_help())
        return "\n".join(lines)

    def _project_context(self, project: Project) -> dict[str, object]:
        if (getattr(project, "project_kind", "funded") or "funded") == "teaching":
            return self._teaching_project_context(project)
        counts = self._project_counts(project.id, project)
        return {
            "project_id": str(project.id),
            "project_code": project.code,
            "project_title": project.title,
            "project_kind": getattr(project, "project_kind", "funded") or "funded",
            "start_date": project.start_date.isoformat(),
            "duration_months": project.duration_months,
            "reporting_dates": project.reporting_dates,
            "language": project.language,
            "coordinator_partner_id": str(project.coordinator_partner_id) if project.coordinator_partner_id else None,
            "coordinator_partner_name": self._resolve_partner_name(project.coordinator_partner_id),
            "principal_investigator_id": str(project.principal_investigator_id) if project.principal_investigator_id else None,
            "principal_investigator_name": self._resolve_member_name(project.principal_investigator_id),
            "counts": counts,
            "current_project_month": self._current_project_month(project),
            "upcoming_outputs": self._upcoming_outputs(project.id),
            "review_gaps": self._review_gaps(project.id),
            "overdue_work": self._overdue_work(project.id, project),
            "open_risks": self._open_risks(project.id),
            "recent_activity": self._recent_activity(project.id),
            "recent_meetings": self._recent_meetings(project.id),
            "command_help": self._command_help(),
            "proposal_sections": self._proposal_summary(project.id),
            "consortium": self._consortium_summary(project.id),
            "proposal_phase": self._detect_proposal_phase(project.id),
            "teaching_project": self._teaching_summary(project.id),
        }

    def _teaching_project_context(self, project: Project) -> dict[str, object]:
        teaching_summary = self._teaching_summary(project.id)
        return {
            "assistant_domain": "teaching",
            "project_id": str(project.id),
            "project_code": project.code,
            "project_title": project.title,
            "project_kind": getattr(project, "project_kind", "teaching") or "teaching",
            "project_status": project.status.value if hasattr(project.status, "value") else str(project.status),
            "language": project.language,
            "documents": {
                "total": int(
                    self.db.scalar(select(func.count()).select_from(ProjectDocument).where(ProjectDocument.project_id == project.id)) or 0
                ),
                "indexed": int(
                    self.db.scalar(
                        select(func.count())
                        .select_from(ProjectDocument)
                        .where(
                            ProjectDocument.project_id == project.id,
                            ProjectDocument.status == DocumentStatus.indexed.value,
                        )
                    )
                    or 0
                ),
            },
            "recent_activity": self._recent_activity(project.id),
            "teaching_project": teaching_summary,
        }

    def _teaching_summary(self, project_id: uuid.UUID) -> dict[str, object] | None:
        profile = self.db.scalar(select(TeachingProjectProfile).where(TeachingProjectProfile.project_id == project_id))
        if not profile:
            return None
        reports = self.db.scalars(
            select(TeachingProgressReport)
            .where(TeachingProgressReport.project_id == project_id)
            .order_by(TeachingProgressReport.report_date.desc().nullslast(), TeachingProgressReport.created_at.desc())
            .limit(4)
        ).all()
        students = self.db.scalars(
            select(TeachingProjectStudent).where(TeachingProjectStudent.project_id == project_id).order_by(TeachingProjectStudent.full_name.asc())
        ).all()
        blockers = self.db.scalars(
            select(TeachingProjectBlocker).where(TeachingProjectBlocker.project_id == project_id).order_by(TeachingProjectBlocker.created_at.desc())
        ).all()
        artifacts = self.db.scalars(
            select(TeachingProjectArtifact).where(TeachingProjectArtifact.project_id == project_id).order_by(TeachingProjectArtifact.required.desc(), TeachingProjectArtifact.label.asc())
        ).all()
        milestones = self.db.scalars(
            select(TeachingProjectMilestone).where(TeachingProjectMilestone.project_id == project_id).order_by(TeachingProjectMilestone.due_at.asc().nullslast())
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
            "blockers": [{"title": item.title, "severity": item.severity.value, "status": item.status.value} for item in blockers],
            "artifacts": [{"label": item.label, "type": item.artifact_type.value, "required": item.required, "status": item.status.value} for item in artifacts],
            "milestones": [{"label": item.label, "kind": item.kind, "status": item.status.value, "due_at": item.due_at.isoformat() if item.due_at else None} for item in milestones],
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

    def _recent_messages(self, project_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 8) -> list[dict[str, str]]:
        rows = self.db.scalars(
            select(ChatMessage)
            .where(ChatMessage.project_id == project_id, ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).all()
        ordered = list(reversed(list(rows)))
        return [{"role": row.role, "content": row.content} for row in ordered]

    def _resolve_partner_name(self, partner_id: uuid.UUID | None) -> str | None:
        if not partner_id:
            return None
        partner = self.db.scalar(select(PartnerOrganization).where(PartnerOrganization.id == partner_id))
        return partner.short_name if partner else None

    def _resolve_member_name(self, member_id: uuid.UUID | None) -> str | None:
        if not member_id:
            return None
        member = self.db.scalar(select(TeamMember).where(TeamMember.id == member_id))
        return member.full_name if member else None

    def _proposal_summary(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
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
        result = []
        for s in sections:
            max_chars = 800 if s.key.lower() in ("abstract", "summary") else 400
            content_snippet = (s.content or "")[:max_chars] or None
            result.append({
                "key": s.key,
                "title": s.title,
                "status": s.status,
                "required": s.required,
                "guidance": s.guidance,
                "content_snippet": content_snippet,
                "owner": self._resolve_member_name(s.owner_member_id),
                "reviewer": self._resolve_member_name(s.reviewer_member_id),
                "due_date": s.due_date.isoformat() if s.due_date else None,
                "linked_docs": int(doc_counts.get(s.id, 0)),
            })
        return result

    def _consortium_summary(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        partners = self.db.scalars(
            select(PartnerOrganization)
            .where(PartnerOrganization.project_id == project_id)
            .order_by(PartnerOrganization.short_name.asc())
        ).all()
        if not partners:
            return []
        partner_ids = [p.id for p in partners]
        member_counts: dict[uuid.UUID, int] = {}
        if partner_ids:
            member_counts = dict(
                self.db.execute(
                    select(TeamMember.organization_id, func.count(TeamMember.id))
                    .where(
                        TeamMember.project_id == project_id,
                        TeamMember.organization_id.in_(partner_ids),
                        TeamMember.is_active.is_(True),
                    )
                    .group_by(TeamMember.organization_id)
                ).all()
            )
        return [
            {
                "short_name": p.short_name,
                "legal_name": p.legal_name,
                "partner_type": p.partner_type,
                "country": p.country,
                "expertise": p.expertise,
                "active_members": int(member_counts.get(p.id, 0)),
            }
            for p in partners
        ]

    def _detect_proposal_phase(self, project_id: uuid.UUID) -> str:
        sections = self.db.scalars(
            select(ProjectProposalSection)
            .where(ProjectProposalSection.project_id == project_id)
            .order_by(ProjectProposalSection.position.asc())
        ).all()
        if not sections:
            return "pre_proposal"
        abstract = next((s for s in sections if s.key.lower() in ("abstract", "summary")), None)
        if abstract and not abstract.content:
            return "abstract_drafting"
        partners = self.db.scalars(
            select(PartnerOrganization).where(PartnerOrganization.project_id == project_id)
        ).all()
        if not partners:
            return "consortium_setup"
        wps = self.db.scalar(
            select(func.count()).select_from(WorkPackage).where(WorkPackage.project_id == project_id)
        ) or 0
        if int(wps) == 0:
            return "wbs_generation"
        return "section_writing"

    def _project_counts(self, project_id: uuid.UUID, project: Project | None = None) -> dict[str, int]:
        current_month = self._current_project_month(project) if project else None
        deliverables = self.db.scalars(select(Deliverable).where(Deliverable.project_id == project_id)).all()
        risks = self.db.scalars(select(ProjectRisk).where(ProjectRisk.project_id == project_id)).all()
        return {
            "wps": int(self.db.scalar(select(func.count()).select_from(WorkPackage).where(WorkPackage.project_id == project_id)) or 0),
            "tasks": int(self.db.scalar(select(func.count()).select_from(Task).where(Task.project_id == project_id)) or 0),
            "milestones": int(self.db.scalar(select(func.count()).select_from(Milestone).where(Milestone.project_id == project_id)) or 0),
            "deliverables": len(deliverables),
            "open_risks": len([item for item in risks if str(getattr(item.status, "value", item.status)) != "closed"]),
            "overdue_wps": len(self._overdue_work(project_id, project)["work_packages"]) if project else 0,
            "overdue_tasks": len(self._overdue_work(project_id, project)["tasks"]) if project else 0,
            "high_risks": len(
                [
                    item
                    for item in risks
                    if str(getattr(item.probability, "value", item.probability)) in {"high", "critical"}
                    or str(getattr(item.impact, "value", item.impact)) in {"high", "critical"}
                ]
            ),
            "deliverables_without_reviewer": len([item for item in deliverables if not item.review_owner_member_id]),
            "reviews_due_soon": len(
                [
                    item
                    for item in deliverables
                    if current_month and item.review_due_month is not None and current_month <= item.review_due_month <= current_month + 1
                ]
            ),
            "documents": int(
                self.db.scalar(select(func.count()).select_from(ProjectDocument).where(ProjectDocument.project_id == project_id)) or 0
            ),
            "indexed_documents": int(
                self.db.scalar(
                    select(func.count())
                    .select_from(ProjectDocument)
                    .where(
                        ProjectDocument.project_id == project_id,
                        ProjectDocument.status == DocumentStatus.indexed.value,
                    )
                )
                or 0
            ),
        }

    def _current_project_month(self, project: Project | None) -> int | None:
        if not project:
            return None
        today = date.today()
        start = project.start_date
        months = (today.year - start.year) * 12 + (today.month - start.month) + 1
        return max(1, months)

    def _upcoming_outputs(self, project_id: uuid.UUID, limit: int = 6) -> list[dict[str, Any]]:
        deliverables = self.db.scalars(
            select(Deliverable).where(Deliverable.project_id == project_id).order_by(Deliverable.due_month.asc(), Deliverable.code.asc()).limit(limit)
        ).all()
        milestones = self.db.scalars(
            select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.due_month.asc(), Milestone.code.asc()).limit(limit)
        ).all()
        rows = [
            {"kind": "deliverable", "code": item.code, "title": item.title, "due_month": item.due_month}
            for item in deliverables
        ] + [
            {"kind": "milestone", "code": item.code, "title": item.title, "due_month": item.due_month}
            for item in milestones
        ]
        rows.sort(key=lambda item: (int(item["due_month"]), str(item["code"])))
        return rows[:limit]

    def _review_gaps(self, project_id: uuid.UUID, limit: int = 6) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(Deliverable)
            .where(Deliverable.project_id == project_id)
            .order_by(Deliverable.due_month.asc(), Deliverable.code.asc())
        ).all()
        current_month = self._current_project_month(self._get_project(project_id))
        results: list[dict[str, Any]] = []
        for item in rows:
            issues: list[str] = []
            if not item.review_owner_member_id:
                issues.append("missing_reviewer")
            if item.review_due_month is None:
                issues.append("missing_review_due")
            elif current_month and item.review_due_month < current_month:
                issues.append("review_late")
            if not issues:
                continue
            results.append(
                {
                    "code": item.code,
                    "title": item.title,
                    "due_month": item.due_month,
                    "review_due_month": item.review_due_month,
                    "issues": issues,
                }
            )
            if len(results) >= limit:
                break
        return results

    def _open_risks(self, project_id: uuid.UUID, limit: int = 6) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(ProjectRisk)
            .where(ProjectRisk.project_id == project_id)
            .order_by(ProjectRisk.updated_at.desc(), ProjectRisk.code.asc())
            .limit(limit)
        ).all()
        return [
            {
                "code": item.code,
                "title": item.title,
                "status": item.status.value if hasattr(item.status, "value") else str(item.status),
                "probability": item.probability.value if hasattr(item.probability, "value") else str(item.probability),
                "impact": item.impact.value if hasattr(item.impact, "value") else str(item.impact),
                "due_month": item.due_month,
            }
            for item in rows
        ]


    def _recent_meetings(self, project_id: uuid.UUID, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(MeetingRecord).where(MeetingRecord.project_id == project_id).order_by(MeetingRecord.starts_at.desc()).limit(limit)
        ).all()
        return [
            {
                "title": item.title,
                "starts_at": item.starts_at.isoformat(),
                "source_type": item.source_type.value if hasattr(item.source_type, "value") else str(item.source_type),
                "participants": list(item.participants_json or []),
                "summary": self._snippet(item.content_text, 280),
            }
            for item in rows
        ]

    def _recent_activity(self, project_id: uuid.UUID, limit: int = 6) -> list[dict[str, Any]]:
        rows = self.db.scalars(
            select(AuditEvent).where(AuditEvent.project_id == project_id).order_by(AuditEvent.created_at.desc()).limit(limit)
        ).all()
        return [
            {
                "event_type": item.event_type,
                "entity_type": item.entity_type,
                "created_at": item.created_at.isoformat(),
                "reason": item.reason,
                "code": (item.after_json or {}).get("code") or (item.before_json or {}).get("code"),
                "title": (item.after_json or {}).get("title") or (item.before_json or {}).get("title"),
            }
            for item in rows
        ]

    def _overdue_work(self, project_id: uuid.UUID, project: Project) -> list[dict[str, Any]] | dict[str, list[dict[str, Any]]]:
        current_month = self._current_project_month(project)
        if current_month is None:
            return {"work_packages": [], "tasks": []}
        overdue_wps = self.db.scalars(
            select(WorkPackage).where(
                WorkPackage.project_id == project_id,
                WorkPackage.is_trashed.is_(False),
                WorkPackage.end_month < current_month,
                WorkPackage.execution_status != WorkExecutionStatus.closed,
            )
        ).all()
        overdue_tasks = self.db.scalars(
            select(Task).where(
                Task.project_id == project_id,
                Task.is_trashed.is_(False),
                Task.end_month < current_month,
                Task.execution_status != WorkExecutionStatus.closed,
            )
        ).all()
        return {
            "work_packages": [
                {"code": item.code, "title": item.title, "end_month": item.end_month, "status": item.execution_status.value}
                for item in overdue_wps[:8]
            ],
            "tasks": [
                {"code": item.code, "title": item.title, "end_month": item.end_month, "status": item.execution_status.value}
                for item in overdue_tasks[:12]
            ],
        }

    def _resolve_partner(self, project_id: uuid.UUID, token: str) -> PartnerOrganization:
        normalized = token.strip().lower()
        partner = self.db.scalar(
            select(PartnerOrganization).where(
                PartnerOrganization.project_id == project_id,
                func.lower(PartnerOrganization.short_name) == normalized,
            )
        )
        if not partner:
            raise NotFoundError(f"Partner `{token}` not found in project.")
        return partner

    def _resolve_responsible(self, project_id: uuid.UUID, leader_partner_id: uuid.UUID, token: str) -> TeamMember:
        cleaned = token.strip()
        if "@" in cleaned:
            member = self.db.scalar(
                select(TeamMember).where(
                    TeamMember.project_id == project_id,
                    TeamMember.organization_id == leader_partner_id,
                    func.lower(TeamMember.email) == cleaned.lower(),
                )
            )
        else:
            member = self.db.scalar(
                select(TeamMember).where(
                    TeamMember.project_id == project_id,
                    TeamMember.organization_id == leader_partner_id,
                    func.lower(TeamMember.full_name) == cleaned.lower(),
                )
            )
        if not member:
            raise NotFoundError(
                f"Responsible `{token}` not found in leader organization. Use full name or email from that partner."
            )
        return member

    def _resolve_collaborators(self, project_id: uuid.UUID, raw: str | None) -> list[uuid.UUID]:
        if raw is None:
            return []
        cleaned = raw.strip()
        if not cleaned:
            return []
        tokens = [item.strip() for item in cleaned.split(",") if item.strip()]
        collaborators: list[uuid.UUID] = []
        for token in tokens:
            collaborator = self._resolve_partner(project_id, token)
            if collaborator.id not in collaborators:
                collaborators.append(collaborator.id)
        return collaborators

    def _resolve_wp_list(self, project_id: uuid.UUID, fields: dict[str, str], required: bool) -> tuple[list[uuid.UUID], list[str]]:
        raw = fields.get("wps") or fields.get("wp")
        if not raw:
            if required:
                raise ValidationError("Provide wp=WP1 or wps=WP1,WP2.")
            return [], []
        tokens = [item.strip() for item in raw.split(",") if item.strip()]
        if not tokens and required:
            raise ValidationError("Provide at least one WP code.")
        wp_ids: list[uuid.UUID] = []
        wp_codes: list[str] = []
        for token in tokens:
            wp = self._get_by_code(project_id, WorkPackage, token, "Work package")
            if wp.id not in wp_ids:
                wp_ids.append(wp.id)
                wp_codes.append(wp.code)
        return wp_ids, wp_codes

    def _wp_codes_by_ids(self, wp_ids: list[uuid.UUID]) -> list[str]:
        if not wp_ids:
            return []
        rows = self.db.scalars(select(WorkPackage).where(WorkPackage.id.in_(wp_ids))).all()
        by_id = {row.id: row.code for row in rows}
        return [by_id[item] for item in wp_ids if item in by_id]

    def _get_by_code(self, project_id: uuid.UUID, model, code: str, label: str):
        entity = self.db.scalar(
            select(model).where(
                model.project_id == project_id,
                func.lower(model.code) == code.strip().lower(),
            )
        )
        if not entity:
            raise NotFoundError(f"{label} with code `{code}` not found in project.")
        return entity

    def _get_collaborators(self, table, fk_name: str, entity_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self.db.scalars(select(table.c.partner_id).where(table.c[fk_name] == entity_id)).all()
        return [item for item in rows]

    def _get_related_wps(self, table, fk_name: str, entity_id: uuid.UUID) -> list[uuid.UUID]:
        rows = self.db.scalars(select(table.c.wp_id).where(table.c[fk_name] == entity_id)).all()
        return [item for item in rows]

    def _required(self, fields: dict[str, str], key: str) -> str:
        value = fields.get(key)
        if value is None or value.strip() == "":
            raise ValidationError(f"Missing required field `{key}`.")
        return value.strip()

    def _int_field(self, fields: dict[str, str], key: str, default: int | None = None) -> int:
        raw = fields.get(key)
        if raw is None:
            if default is None:
                raise ValidationError(f"Missing required field `{key}`.")
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValidationError(f"Field `{key}` must be an integer.") from exc
        if value < 1:
            raise ValidationError(f"Field `{key}` must be >= 1.")
        return value

    def _validate_member(self, project_id: uuid.UUID, member_id: uuid.UUID | None) -> None:
        if not member_id:
            return
        found = self.db.scalar(
            select(TeamMember.id).where(TeamMember.project_id == project_id, TeamMember.id == member_id)
        )
        if not found:
            raise NotFoundError("Member not found in project.")

    def _get_project(self, project_id: uuid.UUID) -> Project:
        project = self.db.scalar(select(Project).where(Project.id == project_id))
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _get_conversation(self, project_id: uuid.UUID, conversation_id: uuid.UUID) -> ChatConversation:
        conversation = self.db.scalar(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.project_id == project_id,
            )
        )
        if not conversation:
            raise NotFoundError("Conversation not found in project.")
        return conversation

    def _query_tokens(self, text: str) -> list[str]:
        raw = re.split(r"[^a-zA-Z0-9]+", text.lower())
        dedup: list[str] = []
        for token in raw:
            if len(token) < 3:
                continue
            if token in dedup:
                continue
            dedup.append(token)
        return dedup

    def _resolve_proposal_token(
        self, project_id: uuid.UUID, conversation_id: uuid.UUID, token: str | None
    ) -> uuid.UUID | None:
        if not token or token.lower() == "last":
            proposal = self.db.scalar(
                select(ChatActionProposal)
                .where(
                    ChatActionProposal.project_id == project_id,
                    ChatActionProposal.conversation_id == conversation_id,
                    ChatActionProposal.status == "pending",
                )
                .order_by(ChatActionProposal.created_at.desc())
            )
            if proposal:
                return proposal.id
            # Fallback: latest pending in project, in case conversation context was switched in UI.
            proposal = self.db.scalar(
                select(ChatActionProposal)
                .where(
                    ChatActionProposal.project_id == project_id,
                    ChatActionProposal.status == "pending",
                )
                .order_by(ChatActionProposal.created_at.desc())
            )
            return proposal.id if proposal else None
        try:
            return uuid.UUID(token)
        except ValueError:
            raise ValidationError("Invalid proposal id. Use `confirm`, `cancel`, or a valid UUID.")

    def _no_pending_message(self, project_id: uuid.UUID, conversation_id: uuid.UUID, verb: str) -> str:
        latest = self.db.scalar(
            select(ChatActionProposal)
            .where(
                ChatActionProposal.project_id == project_id,
                ChatActionProposal.conversation_id == conversation_id,
            )
            .order_by(ChatActionProposal.created_at.desc())
        )
        if latest:
            tail = f"Latest proposal `{latest.id}` is `{latest.status}`."
            if latest.error_text:
                tail += f" Error: {latest.error_text}"
            return f"No pending proposal to {verb} in this conversation. {tail}"

        latest_project = self.db.scalar(
            select(ChatActionProposal)
            .where(ChatActionProposal.project_id == project_id)
            .order_by(ChatActionProposal.created_at.desc())
        )
        if latest_project:
            tail = f"Latest project proposal `{latest_project.id}` is `{latest_project.status}`."
            if latest_project.error_text:
                tail += f" Error: {latest_project.error_text}"
            return f"No pending proposal to {verb}. {tail}"

        return f"No pending proposal to {verb}. Start with an `add` or `update` command."

    def _snippet(self, content: str, max_len: int = 240) -> str:
        text = " ".join((content or "").split())
        if len(text) <= max_len:
            return text
        return f"{text[:max_len - 1].rstrip()}…"

    def _conversation_title_from_prompt(self, prompt: str) -> str:
        clean = " ".join(prompt.split())
        if not clean:
            return "New conversation"
        if len(clean) <= 56:
            return clean
        return f"{clean[:55].rstrip()}…"

    def _command_help(self) -> str:
        return (
            "Command format: `add|update <project|wp|task|deliverable|milestone> key=value ...`.\n"
            "Project settings can also be updated by natural language, for example: "
            "`update project duration_months=30 reporting_dates=2026-12-31,2027-12-31`.\n"
            "Create examples:\n"
            "- `add wp code=WP2 title=\"Data Platform\" start_month=1 end_month=12 leader=POLIBA responsible=\"Mario Rossi\" collaborators=QUALVIVE`\n"
            "- `add task wp=WP2 code=T2.1 title=\"Data ingestion\" start_month=2 end_month=6 leader=POLIBA responsible=\"Mario Rossi\"`\n"
            "- `add deliverable code=D2.1 title=\"Architecture\" due_month=8 wps=WP2 leader=POLIBA responsible=\"Mario Rossi\"`\n"
            "- `add milestone code=MS2 title=\"Pilot ready\" due_month=10 wps=WP2 leader=POLIBA responsible=\"Mario Rossi\"`\n"
            "Update examples:\n"
            "- `update wp target=WP2 end_month=10 collaborators=QUALVIVE`\n"
            "- `update task target=T2.1 end_month=7`\n"
            "- `update deliverable target=D2.1 due_month=9 wps=WP2,WP3`\n"
            "- `update milestone target=MS2 due_month=11`\n"
            "Every command creates a pending proposal. Execution only happens after confirmation.\n"
            "Confirm with `confirm` (latest pending), `confirm last`, or `confirm <proposal_id>`.\n"
            "Cancel with `cancel` (latest pending), `cancel last`, or `cancel <proposal_id>`."
        )
