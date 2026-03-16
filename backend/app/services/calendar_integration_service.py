from __future__ import annotations

import json
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import error, request
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.calendar_import import CalendarImportBatch
from app.core.config import settings
from app.models.calendar_integration import CalendarIntegration, CalendarProvider, CalendarSyncStatus
from app.models.meeting import MeetingRecord, MeetingSourceType
from app.models.project import Project
from app.services.meeting_ingestion_service import MeetingIngestionService
from app.services.onboarding_service import NotFoundError, ValidationError


class CalendarIntegrationService:
    MICROSOFT_SCOPES = ["offline_access", "openid", "profile", "email", "User.Read", "Calendars.Read"]

    def __init__(self, db: Session):
        self.db = db

    def list_integrations(self, project_id) -> list[CalendarIntegration]:
        self._get_project(project_id)
        return list(
            self.db.scalars(
                select(CalendarIntegration)
                .where(CalendarIntegration.project_id == project_id)
                .order_by(CalendarIntegration.provider.asc())
            ).all()
        )

    def start_microsoft365_connect(self, project_id) -> str:
        self._require_microsoft_config()
        integration = self._get_or_create_integration(project_id, CalendarProvider.microsoft365)
        integration.oauth_state = secrets.token_urlsafe(24)
        integration.last_error = None
        self.db.commit()
        query = urllib.parse.urlencode(
            {
                "client_id": settings.microsoft_client_id,
                "response_type": "code",
                "redirect_uri": settings.microsoft_redirect_uri,
                "response_mode": "query",
                "scope": " ".join(self.MICROSOFT_SCOPES),
                "state": integration.oauth_state,
            }
        )
        return f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/authorize?{query}"

    def complete_microsoft365_callback(self, code: str, state: str) -> CalendarIntegration:
        if not code.strip() or not state.strip():
            raise ValidationError("OAuth callback is missing code or state.")
        integration = self.db.scalar(
            select(CalendarIntegration).where(
                CalendarIntegration.provider == CalendarProvider.microsoft365,
                CalendarIntegration.oauth_state == state.strip(),
            )
        )
        if not integration:
            raise ValidationError("OAuth state is invalid or expired.")
        token_payload = self._exchange_microsoft_code(code.strip())
        integration.access_token = str(token_payload.get("access_token") or "").strip() or None
        integration.refresh_token = str(token_payload.get("refresh_token") or "").strip() or integration.refresh_token
        expires_in = int(token_payload.get("expires_in") or 3600)
        integration.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60))
        integration.oauth_state = None
        integration.sync_status = CalendarSyncStatus.connected
        integration.last_error = None
        profile = self._microsoft_get_json("https://graph.microsoft.com/v1.0/me", integration.access_token or "")
        integration.connected_account_email = (
            str(profile.get("mail") or "").strip()
            or str(profile.get("userPrincipalName") or "").strip()
            or integration.connected_account_email
        )
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def sync_microsoft365(self, project_id) -> tuple[CalendarIntegration, int, int]:
        integration = self._get_or_create_integration(project_id, CalendarProvider.microsoft365)
        if not integration.refresh_token and not integration.access_token:
            raise ValidationError("Microsoft 365 calendar is not connected.")
        access_token = self._ensure_microsoft_access_token(integration)
        integration.sync_status = CalendarSyncStatus.syncing
        integration.last_error = None
        self.db.commit()

        now = datetime.now(timezone.utc)
        start_at = now - timedelta(days=settings.calendar_sync_past_days)
        end_at = now + timedelta(days=settings.calendar_sync_future_days)
        query = urllib.parse.urlencode(
            {
                "startDateTime": start_at.isoformat(),
                "endDateTime": end_at.isoformat(),
                "$top": "200",
                "$orderby": "start/dateTime",
            }
        )
        payload = self._microsoft_get_json(f"https://graph.microsoft.com/v1.0/me/calendarView?{query}", access_token)
        imported = 0
        updated = 0
        for raw in payload.get("value", []):
            if not isinstance(raw, dict):
                continue
            created, changed = self._upsert_meeting_from_microsoft_event(project_id, raw)
            imported += int(created)
            updated += int(changed)

        integration.sync_status = CalendarSyncStatus.connected
        integration.last_synced_at = datetime.now(timezone.utc)
        integration.last_error = None
        self.db.commit()
        self.db.refresh(integration)
        return integration, imported, updated

    def import_ics(self, project_id, raw_content: str) -> tuple[int, int]:
        return self.import_ics_file(project_id, "calendar.ics", raw_content)

    def import_ics_file(self, project_id, filename: str, raw_content: str) -> tuple[int, int]:
        self._get_project(project_id)
        text = (raw_content or "").strip()
        if not text:
            raise ValidationError("The .ics file is empty.")
        events = self._parse_ics_events(text)
        if not events:
            raise ValidationError("No calendar events were found in the .ics file.")
        batch = self._get_or_create_import_batch(project_id, filename)
        imported = 0
        updated = 0
        for event in events:
            created, changed = self._upsert_meeting_from_ics_event(project_id, event, batch.id)
            imported += int(created)
            updated += int(changed)
        batch.imported_count = imported
        batch.updated_count = updated
        self.db.commit()
        return imported, updated

    def list_import_batches(self, project_id) -> list[CalendarImportBatch]:
        self._get_project(project_id)
        return list(
            self.db.scalars(
                select(CalendarImportBatch)
                .where(CalendarImportBatch.project_id == project_id)
                .order_by(CalendarImportBatch.updated_at.desc(), CalendarImportBatch.filename.asc())
            ).all()
        )

    def delete_import_batch(self, project_id, batch_id) -> None:
        self._get_project(project_id)
        batch = self.db.scalar(
            select(CalendarImportBatch).where(
                CalendarImportBatch.project_id == project_id,
                CalendarImportBatch.id == batch_id,
            )
        )
        if not batch:
            raise NotFoundError("Imported .ics file not found.")
        self.db.delete(batch)
        self.db.commit()

    def _upsert_meeting_from_microsoft_event(self, project_id, raw: dict[str, Any]) -> tuple[bool, bool]:
        event_id = str(raw.get("id") or "").strip()
        subject = str(raw.get("subject") or "").strip()
        start_value = self._parse_graph_datetime(raw.get("start"))
        if not event_id or not subject or start_value is None:
            return False, False
        participants: list[str] = []
        for attendee in raw.get("attendees", []):
            if not isinstance(attendee, dict):
                continue
            email_address = attendee.get("emailAddress") or {}
            label = str(email_address.get("name") or "").strip() or str(email_address.get("address") or "").strip()
            if label:
                participants.append(label)
        preview = str(raw.get("bodyPreview") or "").strip()
        source_url = str(raw.get("webLink") or "").strip() or None
        content_text = preview or "Imported from Microsoft 365 calendar."
        record = self.db.scalar(
            select(MeetingRecord).where(
                MeetingRecord.project_id == project_id,
                MeetingRecord.external_calendar_event_id == event_id,
            )
        )
        created = False
        changed = False
        if not record:
            record = MeetingRecord(
                project_id=project_id,
                title=subject,
                starts_at=start_value,
                source_type=MeetingSourceType.minutes,
                source_url=source_url,
                participants_json=participants,
                content_text=content_text,
                external_calendar_event_id=event_id,
                indexing_status="pending",
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            MeetingIngestionService(self.db).index_meeting(record)
            return True, False

        changed = any(
            [
                record.title != subject,
                record.starts_at != start_value,
                record.source_url != source_url,
                list(record.participants_json or []) != participants,
                record.content_text != content_text,
            ]
        )
        if changed:
            record.title = subject
            record.starts_at = start_value
            record.source_url = source_url
            record.participants_json = participants
            record.content_text = content_text
            self.db.commit()
            self.db.refresh(record)
            MeetingIngestionService(self.db).index_meeting(record)
        return created, changed

    def _ensure_microsoft_access_token(self, integration: CalendarIntegration) -> str:
        if integration.access_token and integration.token_expires_at and integration.token_expires_at > datetime.now(timezone.utc):
            return integration.access_token
        if not integration.refresh_token:
            raise ValidationError("Microsoft 365 refresh token is missing.")
        token_payload = self._refresh_microsoft_token(integration.refresh_token)
        integration.access_token = str(token_payload.get("access_token") or "").strip() or None
        integration.refresh_token = str(token_payload.get("refresh_token") or "").strip() or integration.refresh_token
        expires_in = int(token_payload.get("expires_in") or 3600)
        integration.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60))
        integration.sync_status = CalendarSyncStatus.connected
        integration.last_error = None
        self.db.commit()
        return integration.access_token or ""

    def _upsert_meeting_from_ics_event(self, project_id, event: dict[str, Any], batch_id) -> tuple[bool, bool]:
        uid = str(event.get("uid") or "").strip()
        title = str(event.get("summary") or "").strip()
        starts_at = event.get("starts_at")
        if not uid or not title or starts_at is None:
            return False, False
        participants = event.get("participants", [])
        description_parts = [part for part in [event.get("description"), event.get("location"), event.get("organizer")] if part]
        content_text = "\n\n".join(description_parts).strip() or "Imported from .ics calendar file."
        source_url = event.get("url")
        record = self.db.scalar(
            select(MeetingRecord).where(
                MeetingRecord.project_id == project_id,
                MeetingRecord.external_calendar_event_id == uid,
            )
        )
        if not record:
            record = MeetingRecord(
                project_id=project_id,
                title=title,
                starts_at=starts_at,
                source_type=MeetingSourceType.minutes,
                source_url=source_url,
                participants_json=participants,
                content_text=content_text,
                external_calendar_event_id=uid,
                import_batch_id=batch_id,
                indexing_status="pending",
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            MeetingIngestionService(self.db).index_meeting(record)
            return True, False
        changed = any(
            [
                record.title != title,
                record.starts_at != starts_at,
                record.source_url != source_url,
                list(record.participants_json or []) != participants,
                record.content_text != content_text,
            ]
        )
        if changed:
            record.title = title
            record.starts_at = starts_at
            record.source_url = source_url
            record.participants_json = participants
            record.content_text = content_text
            record.import_batch_id = batch_id
            self.db.commit()
            self.db.refresh(record)
            MeetingIngestionService(self.db).index_meeting(record)
        return False, changed

    def _exchange_microsoft_code(self, code: str) -> dict[str, Any]:
        return self._microsoft_token_request(
            {
                "client_id": settings.microsoft_client_id or "",
                "client_secret": settings.microsoft_client_secret or "",
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.microsoft_redirect_uri or "",
            }
        )

    def _refresh_microsoft_token(self, refresh_token: str) -> dict[str, Any]:
        return self._microsoft_token_request(
            {
                "client_id": settings.microsoft_client_id or "",
                "client_secret": settings.microsoft_client_secret or "",
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "redirect_uri": settings.microsoft_redirect_uri or "",
            }
        )

    def _microsoft_token_request(self, payload: dict[str, str]) -> dict[str, Any]:
        endpoint = f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/token"
        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        req = request.Request(endpoint, data=encoded, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValidationError(f"Microsoft token exchange failed: {detail or exc.reason}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ValidationError(f"Microsoft token exchange failed: {exc}") from exc

    def _microsoft_get_json(self, url: str, access_token: str) -> dict[str, Any]:
        req = request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ValidationError(f"Microsoft Graph request failed: {detail or exc.reason}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ValidationError(f"Microsoft Graph request failed: {exc}") from exc

    def _get_or_create_integration(self, project_id, provider: CalendarProvider) -> CalendarIntegration:
        self._get_project(project_id)
        integration = self.db.scalar(
            select(CalendarIntegration).where(
                CalendarIntegration.project_id == project_id,
                CalendarIntegration.provider == provider,
            )
        )
        if integration:
            return integration
        integration = CalendarIntegration(
            project_id=project_id,
            provider=provider,
            sync_status=CalendarSyncStatus.disconnected,
        )
        self.db.add(integration)
        self.db.commit()
        self.db.refresh(integration)
        return integration

    def _get_or_create_import_batch(self, project_id, filename: str) -> CalendarImportBatch:
        cleaned = filename.strip() or "calendar.ics"
        batch = self.db.scalar(
            select(CalendarImportBatch).where(
                CalendarImportBatch.project_id == project_id,
                CalendarImportBatch.filename == cleaned,
            )
        )
        if batch:
            return batch
        batch = CalendarImportBatch(project_id=project_id, filename=cleaned)
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def _get_project(self, project_id) -> Project:
        project = self.db.get(Project, project_id)
        if not project:
            raise NotFoundError("Project not found.")
        return project

    def _require_microsoft_config(self) -> None:
        if not settings.microsoft_client_id or not settings.microsoft_client_secret or not settings.microsoft_redirect_uri:
            raise ValidationError("Microsoft 365 OAuth is not configured.")

    def _parse_graph_datetime(self, payload: Any) -> datetime | None:
        if not isinstance(payload, dict):
            return None
        raw = str(payload.get("dateTime") or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _parse_ics_events(self, raw_content: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in self._unfold_ics_lines(raw_content):
            if line == "BEGIN:VEVENT":
                current = {}
                continue
            if line == "END:VEVENT":
                if current:
                    events.append(self._normalize_ics_event(current))
                current = None
                continue
            if current is None or ":" not in line:
                continue
            raw_key, value = line.split(":", 1)
            current.setdefault(raw_key, []).append(value)
        return events

    def _normalize_ics_event(self, raw_event: dict[str, list[str]]) -> dict[str, Any]:
        starts_key, starts_value = self._first_ics_field(raw_event, "DTSTART")
        tzid = self._extract_ics_param(starts_key, "TZID") if starts_key else None
        attendees = []
        for key, values in raw_event.items():
            if not key.startswith("ATTENDEE"):
                continue
            for value in values:
                cn = self._extract_ics_param(key, "CN")
                token = cn or value.replace("mailto:", "").replace("MAILTO:", "").strip()
                if token:
                    attendees.append(token)
        organizer_key, organizer_value = self._first_ics_field(raw_event, "ORGANIZER")
        organizer = None
        if organizer_key or organizer_value:
            organizer = self._extract_ics_param(organizer_key or "", "CN") or (organizer_value or "").replace("mailto:", "").replace("MAILTO:", "").strip() or None
        return {
            "uid": self._first_ics_value(raw_event, "UID"),
            "summary": self._first_ics_value(raw_event, "SUMMARY"),
            "description": self._first_ics_value(raw_event, "DESCRIPTION"),
            "location": self._first_ics_value(raw_event, "LOCATION"),
            "url": self._first_ics_value(raw_event, "URL"),
            "organizer": organizer,
            "participants": attendees,
            "starts_at": self._parse_ics_datetime(starts_value, tzid),
        }

    def _unfold_ics_lines(self, raw_content: str) -> list[str]:
        lines = raw_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        unfolded: list[str] = []
        for line in lines:
            if line.startswith((" ", "\t")) and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line.strip())
        return [line for line in unfolded if line]

    def _first_ics_field(self, raw_event: dict[str, list[str]], prefix: str) -> tuple[str | None, str | None]:
        for key, values in raw_event.items():
            if key == prefix or key.startswith(f"{prefix};"):
                if values:
                    return key, self._decode_ics_text(values[0])
        return None, None

    def _first_ics_value(self, raw_event: dict[str, list[str]], prefix: str) -> str | None:
        _, value = self._first_ics_field(raw_event, prefix)
        return value

    def _extract_ics_param(self, raw_key: str, name: str) -> str | None:
        parts = raw_key.split(";")
        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key.upper() == name.upper():
                return value.strip('"')
        return None

    def _parse_ics_datetime(self, value: str | None, tzid: str | None) -> datetime | None:
        token = (value or "").strip()
        if not token:
            return None
        formats = ["%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"]
        parsed: datetime | None = None
        for fmt in formats:
            try:
                parsed = datetime.strptime(token, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
        if token.endswith("Z"):
            return parsed.replace(tzinfo=timezone.utc)
        if tzid:
            try:
                return parsed.replace(tzinfo=ZoneInfo(tzid))
            except Exception:
                pass
        return parsed.replace(tzinfo=timezone.utc)

    def _decode_ics_text(self, value: str) -> str:
        return (
            value.replace("\\n", "\n")
            .replace("\\N", "\n")
            .replace("\\,", ",")
            .replace("\\;", ";")
            .replace("\\\\", "\\")
            .strip()
        )
