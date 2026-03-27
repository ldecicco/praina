"""Telegram delivery helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramSendResult:
    ok: bool
    error_message: str | None = None


@dataclass(slots=True)
class TelegramUpdateMatch:
    chat_id: str
    username: str | None = None
    first_name: str | None = None


class TelegramService:
    def is_configured(self) -> bool:
        return bool((settings.telegram_bot_token or "").strip())

    def send_message(self, chat_id: str, text: str, *, parse_mode: str | None = None) -> bool:
        return self.send_message_result(chat_id, text, parse_mode=parse_mode).ok

    def find_chat_by_code(self, code: str) -> TelegramUpdateMatch | None:
        token = (settings.telegram_bot_token or "").strip()
        normalized = code.strip().upper()
        if not token or not normalized:
            return None
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"limit": 100, "timeout": 0},
                )
                response.raise_for_status()
        except Exception:
            logger.warning("Telegram getUpdates failed", exc_info=True)
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        results = payload.get("result")
        if not isinstance(results, list):
            return None
        for item in reversed(results):
            message = item.get("message") if isinstance(item, dict) else None
            if not isinstance(message, dict):
                continue
            text = message.get("text")
            if not isinstance(text, str):
                continue
            if normalized not in text.upper():
                continue
            chat = message.get("chat")
            from_user = message.get("from")
            if not isinstance(chat, dict):
                continue
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            username = None
            first_name = None
            if isinstance(from_user, dict):
                username_value = from_user.get("username")
                first_name_value = from_user.get("first_name")
                if isinstance(username_value, str):
                    username = username_value
                if isinstance(first_name_value, str):
                    first_name = first_name_value
            return TelegramUpdateMatch(chat_id=str(chat_id), username=username, first_name=first_name)
        return None

    def send_message_result(self, chat_id: str, text: str, *, parse_mode: str | None = None) -> TelegramSendResult:
        token = (settings.telegram_bot_token or "").strip()
        if not token:
            return TelegramSendResult(ok=False, error_message="Telegram bot token is not configured.")
        if not chat_id:
            return TelegramSendResult(ok=False, error_message="Telegram chat id is required.")
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "disable_web_page_preview": True,
                        **({"parse_mode": parse_mode} if parse_mode else {}),
                    },
                )
                if response.is_success:
                    return TelegramSendResult(ok=True)
                error_message = self._extract_error_message(response)
                logger.warning("Telegram sendMessage failed: %s", error_message)
                return TelegramSendResult(ok=False, error_message=error_message)
        except Exception as exc:
            logger.warning("Telegram sendMessage failed", exc_info=True)
            return TelegramSendResult(ok=False, error_message=str(exc) or "Telegram request failed.")

    def _extract_error_message(self, response: httpx.Response) -> str:
        default_message = f"Telegram request failed with status {response.status_code}."
        try:
            payload = response.json()
        except Exception:
            return default_message
        if isinstance(payload, dict):
            description = payload.get("description")
            if isinstance(description, str) and description.strip():
                return description.strip()
        return default_message
