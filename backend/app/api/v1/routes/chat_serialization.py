from __future__ import annotations

import uuid
from collections.abc import Callable


def build_scoped_chat_message_payload(
    *,
    item,
    get_display_name: Callable[[uuid.UUID], str],
    reaction_map: dict[uuid.UUID, list[dict]] | None = None,
    reply_lookup: dict[uuid.UUID, object] | None = None,
    fallback_reply_lookup: Callable[[list[uuid.UUID]], dict[uuid.UUID, object]] | None = None,
) -> dict:
    reply_item = None
    if item.reply_to_message_id and reply_lookup is not None:
        reply_item = reply_lookup.get(item.reply_to_message_id)
    if item.reply_to_message_id and reply_item is None and fallback_reply_lookup is not None:
        reply_item = fallback_reply_lookup([item.reply_to_message_id]).get(item.reply_to_message_id)

    reply_payload = None
    if reply_item:
        reply_payload = {
            "id": str(reply_item.id),
            "sender_user_id": str(reply_item.sender_user_id),
            "sender_display_name": get_display_name(reply_item.sender_user_id),
            "content": reply_item.content,
            "deleted_at": reply_item.deleted_at,
            "created_at": reply_item.created_at,
        }

    return {
        "sender_user_id": str(item.sender_user_id),
        "sender_display_name": get_display_name(item.sender_user_id),
        "content": item.content,
        "reply_to_message_id": str(item.reply_to_message_id) if item.reply_to_message_id else None,
        "reply_to_message": reply_payload,
        "reactions": (reaction_map or {}).get(item.id, []),
        "edited_at": item.edited_at,
        "deleted_at": item.deleted_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
