import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatActionProposal, ChatConversation
from app.services.chat_service import ChatService
from app.services.onboarding_service import ValidationError

ROOM_CONVERSATION_TITLE_PREFIX = "__project_chat_room__"


class ProjectChatOpsService:
    def __init__(self, db: Session):
        self.db = db
        self.chat_service = ChatService(db)

    def handle_mentioned_message(
        self,
        *,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        sender_user_id: uuid.UUID,
        prompt: str,
        project_context: dict,
    ) -> str | None:
        text = prompt.strip()
        if not text:
            return "Please provide a request after `@bot`."

        try:
            confirm_reply = self._maybe_handle_confirmation(project_id, room_id, text)
        except ValidationError as exc:
            self.db.rollback()
            return str(exc)
        if confirm_reply is not None:
            return confirm_reply

        parsed, extraction_message = self.chat_service._parse_natural_language_action(project_id, text)
        if extraction_message is not None:
            return extraction_message
        if parsed is None:
            return None

        conversation_id = self._ensure_room_conversation(project_id, room_id)
        try:
            proposal = self.chat_service._build_action_proposal(
                project_id=project_id,
                conversation_id=conversation_id,
                created_by_member_id=None,
                parsed=parsed,
            )
        except ValidationError as exc:
            self.db.rollback()
            return f"I could not prepare a valid action proposal: {exc}"

        self.db.add(proposal)
        self.db.commit()
        self.db.refresh(proposal)
        return (
            f"Pending action created.\nProposal ID: {proposal.id}\n{proposal.summary}\n\n"
            f"Reply with `@bot confirm {proposal.id}` to execute or `@bot cancel {proposal.id}` to discard."
        )

    def _maybe_handle_confirmation(self, project_id: uuid.UUID, room_id: uuid.UUID, prompt: str) -> str | None:
        stripped = prompt.strip()
        confirm_match = re.fullmatch(r"(?i)(confirm|approve)(?:\s+([0-9a-f-]{36}|last))?", stripped)
        if confirm_match:
            token = confirm_match.group(2)
            return self._confirm(project_id, room_id, token)

        cancel_match = re.fullmatch(r"(?i)(cancel|reject)(?:\s+([0-9a-f-]{36}|last))?", stripped)
        if cancel_match:
            token = cancel_match.group(2)
            return self._cancel(project_id, room_id, token)

        return None

    def _confirm(self, project_id: uuid.UUID, room_id: uuid.UUID, token: str | None) -> str:
        conversation_id = self._room_conversation_id(project_id, room_id)
        if not conversation_id:
            return "No pending proposal to confirm in this room."
        proposal_id = self._resolve_room_proposal_token(project_id, conversation_id, token)
        if not proposal_id:
            return "No pending proposal to confirm in this room."
        reply = self.chat_service._confirm_proposal(project_id, conversation_id, proposal_id)
        self.db.commit()
        return reply

    def _cancel(self, project_id: uuid.UUID, room_id: uuid.UUID, token: str | None) -> str:
        conversation_id = self._room_conversation_id(project_id, room_id)
        if not conversation_id:
            return "No pending proposal to cancel in this room."
        proposal_id = self._resolve_room_proposal_token(project_id, conversation_id, token)
        if not proposal_id:
            return "No pending proposal to cancel in this room."
        reply = self.chat_service._cancel_proposal(project_id, conversation_id, proposal_id)
        self.db.commit()
        return reply

    def _resolve_room_proposal_token(
        self,
        project_id: uuid.UUID,
        conversation_id: uuid.UUID,
        token: str | None,
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
            return proposal.id if proposal else None
        try:
            proposal_id = uuid.UUID(token)
        except ValueError:
            raise ValidationError("Invalid proposal id. Use `@bot confirm`, `@bot cancel`, or a valid UUID.")

        proposal = self.db.scalar(
            select(ChatActionProposal).where(
                ChatActionProposal.id == proposal_id,
                ChatActionProposal.project_id == project_id,
                ChatActionProposal.conversation_id == conversation_id,
            )
        )
        return proposal.id if proposal else None

    def _room_conversation_id(self, project_id: uuid.UUID, room_id: uuid.UUID) -> uuid.UUID | None:
        title = f"{ROOM_CONVERSATION_TITLE_PREFIX}{room_id}"
        conversation = self.db.scalar(
            select(ChatConversation)
            .where(
                ChatConversation.project_id == project_id,
                ChatConversation.title == title,
            )
            .order_by(ChatConversation.created_at.desc())
        )
        return conversation.id if conversation else None

    def _ensure_room_conversation(self, project_id: uuid.UUID, room_id: uuid.UUID) -> uuid.UUID:
        current = self._room_conversation_id(project_id, room_id)
        if current:
            return current
        conversation = ChatConversation(
            project_id=project_id,
            title=f"{ROOM_CONVERSATION_TITLE_PREFIX}{room_id}",
            created_by_member_id=None,
        )
        self.db.add(conversation)
        self.db.flush()
        return conversation.id
