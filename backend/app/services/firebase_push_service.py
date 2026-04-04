"""Firebase Cloud Messaging delivery helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:  # pragma: no cover - dependency may be absent in some dev envs
    firebase_admin = None
    credentials = None
    messaging = None


@dataclass(slots=True)
class PushSendFailure:
    token: str
    code: str | None = None
    message: str | None = None

    @property
    def should_disable_token(self) -> bool:
        code = (self.code or "").strip().lower()
        message = (self.message or "").strip().lower()
        if code in {"registration-token-not-registered", "unregistered"}:
            return True
        return "not registered" in message or "unregistered" in message or "requested entity was not found" in message


@dataclass(slots=True)
class PushSendResult:
    success_count: int
    failure_count: int
    failures: list[PushSendFailure]


class FirebasePushService:
    _app = None
    _lock: Lock = Lock()

    def is_configured(self) -> bool:
        return bool(self._credentials_path()) and firebase_admin is not None and credentials is not None and messaging is not None

    def send_notification(
        self,
        *,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> PushSendResult:
        cleaned_tokens = [token.strip() for token in tokens if token and token.strip()]
        if not cleaned_tokens or not self.is_configured():
            if not cleaned_tokens:
                logger.info("firebase push skipped: no tokens")
            else:
                logger.warning("firebase push skipped: service not configured")
            return PushSendResult(success_count=0, failure_count=0, failures=[])

        app = self._get_app()
        if app is None:
            logger.warning("firebase push skipped: app initialization failed")
            return PushSendResult(success_count=0, failure_count=0, failures=[])

        notification = messaging.Notification(title=title[:120], body=body[:240] if body else "")
        failures: list[PushSendFailure] = []
        success_count = 0
        failure_count = 0

        for start in range(0, len(cleaned_tokens), 500):
            batch = cleaned_tokens[start : start + 500]
            logger.info("firebase push sending batch_size=%s title=%s", len(batch), title[:120])
            message = messaging.MulticastMessage(
                tokens=batch,
                notification=notification,
                data={key: value for key, value in (data or {}).items() if value is not None},
                android=messaging.AndroidConfig(priority="high"),
            )
            try:
                response = messaging.send_each_for_multicast(message, app=app)
            except Exception:
                logger.warning("Firebase push send failed for batch of %s tokens", len(batch), exc_info=True)
                failure_count += len(batch)
                failures.extend(PushSendFailure(token=token, code="batch-send-failed", message="Batch send failed.") for token in batch)
                continue

            success_count += response.success_count
            failure_count += response.failure_count
            logger.info(
                "firebase push batch result success=%s failure=%s",
                response.success_count,
                response.failure_count,
            )
            for token, send_response in zip(batch, response.responses):
                if send_response.success:
                    continue
                exc = send_response.exception
                code = getattr(exc, "code", None)
                message_text = str(exc) if exc else "Unknown FCM send failure."
                logger.warning(
                    "firebase push token failure token_prefix=%s code=%s message=%s",
                    token[:16],
                    code,
                    message_text,
                )
                failures.append(PushSendFailure(token=token, code=code, message=message_text))

        return PushSendResult(success_count=success_count, failure_count=failure_count, failures=failures)

    def _get_app(self):
        if firebase_admin is None or credentials is None:
            return None
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is not None:
                return self._app
            cred_path = self._credentials_path()
            if not cred_path:
                return None
            try:
                cred = credentials.Certificate(str(cred_path))
                options = {"projectId": settings.firebase_project_id} if (settings.firebase_project_id or "").strip() else None
                self._app = firebase_admin.initialize_app(cred, options=options)
            except ValueError:
                # Firebase app may already exist in long-lived dev reload scenarios.
                self._app = firebase_admin.get_app()
            except Exception:
                logger.warning("Failed to initialize Firebase Admin SDK", exc_info=True)
                return None
            return self._app

    def _credentials_path(self) -> Path | None:
        raw = (settings.firebase_credentials_path or "").strip()
        if not raw:
            return None
        raw_path = Path(raw)
        candidates: list[Path]
        if raw_path.is_absolute():
            candidates = [raw_path]
        else:
            backend_root = Path(__file__).resolve().parents[2]
            candidates = [(Path.cwd() / raw_path), (backend_root / raw_path)]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        logger.warning("Firebase credentials file does not exist: %s", raw)
        return None
