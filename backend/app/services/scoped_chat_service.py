from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.onboarding_service import NotFoundError, ValidationError


class ScopedChatService:
    def __init__(self, db: Session):
        self.db = db

    def list_messages(
        self,
        message_model: type,
        *,
        scope_field: str,
        scope_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[Any], int]:
        scope_column = getattr(message_model, scope_field)
        stmt = select(message_model).where(scope_column == scope_id).order_by(message_model.created_at.asc())
        total = int(self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        items = self.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
        return list(items), total

    def create_message(
        self,
        message_model: type,
        *,
        scope_field: str,
        scope_id: uuid.UUID,
        sender_user_id: uuid.UUID,
        content: str,
        reply_to_message_id: uuid.UUID | None = None,
    ) -> Any:
        text = content.strip()
        if not text:
            raise ValidationError("Message content cannot be empty.")
        if len(text) > 8000:
            raise ValidationError("Message content cannot exceed 8000 characters.")

        reply_to_id: uuid.UUID | None = None
        if reply_to_message_id:
          scope_column = getattr(message_model, scope_field)
          reply_target = self.db.scalar(
              select(message_model).where(message_model.id == reply_to_message_id, scope_column == scope_id)
          )
          if not reply_target:
              raise NotFoundError("Reply target not found.")
          reply_to_id = reply_target.id

        message = message_model(
            **{
                scope_field: scope_id,
                "sender_user_id": sender_user_id,
                "reply_to_message_id": reply_to_id,
                "content": text,
            }
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def toggle_reaction(
        self,
        message_model: type,
        reaction_model: type,
        *,
        scope_field: str,
        scope_id: uuid.UUID,
        message_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        emoji: str,
    ) -> Any:
        symbol = emoji.strip()
        if not symbol:
            raise ValidationError("Reaction emoji cannot be empty.")
        if len(symbol) > 32:
            raise ValidationError("Reaction emoji is too long.")

        scope_column = getattr(message_model, scope_field)
        target = self.db.scalar(
            select(message_model).where(message_model.id == message_id, scope_column == scope_id)
        )
        if not target:
            raise NotFoundError("Message not found.")

        existing = self.db.scalar(
            select(reaction_model).where(
                reaction_model.message_id == target.id,
                reaction_model.user_id == actor_user_id,
                reaction_model.emoji == symbol,
            )
        )
        if existing:
            self.db.delete(existing)
        else:
            self.db.add(reaction_model(message_id=target.id, user_id=actor_user_id, emoji=symbol))
        self.db.commit()
        self.db.refresh(target)
        return target

    def message_lookup(self, message_model: type, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
        if not message_ids:
            return {}
        rows = self.db.scalars(select(message_model).where(message_model.id.in_(message_ids))).all()
        return {item.id: item for item in rows}

    def reaction_summary_by_message(self, reaction_model: type, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
        if not message_ids:
            return {}
        rows = self.db.scalars(
            select(reaction_model)
            .where(reaction_model.message_id.in_(message_ids))
            .order_by(reaction_model.created_at.asc())
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
