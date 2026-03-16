from __future__ import annotations

from datetime import date
from typing import Any

from app.agents.chat_action_extraction_agent import ChatActionExtractionAgent


class MeetingActionExtractionAgent(ChatActionExtractionAgent):
    def extract(self, *, meeting_content: str, project_context: dict[str, Any]) -> dict[str, Any] | None:
        self.last_error = None
        content = meeting_content.strip()
        if not content:
            self._append_error("Meeting content is empty.")
            return None
        prompt = self._build_prompt(meeting_content=content, project_context=project_context)
        raw = self._generate_with_ollama_chat(prompt, allow_compaction=True)
        if not raw:
            if not self.last_error:
                self._append_error("LLM did not return a response")
            return None
        payload = self._parse_json(raw)
        if not payload:
            self._append_error("LLM returned non-JSON output for meeting extraction")
            return None
        return self._normalize(payload)

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = str(payload.get("summary") or "").strip() or None
        action_items: list[dict[str, Any]] = []
        for item in payload.get("action_items", []):
            if not isinstance(item, dict):
                continue
            description = str(item.get("description") or "").strip()
            if not description:
                continue
            due_date = self._normalize_due_date(item.get("due_date"))
            priority = str(item.get("priority") or "normal").strip().lower()
            if priority not in {"low", "normal", "high", "urgent"}:
                priority = "normal"
            assignee_name = str(item.get("assignee_name") or "").strip() or None
            action_items.append(
                {
                    "description": description,
                    "assignee_name": assignee_name,
                    "due_date": due_date,
                    "priority": priority,
                }
            )
        return {"summary": summary, "action_items": action_items}

    def _normalize_due_date(self, value: Any) -> str | None:
        token = str(value or "").strip()
        if not token:
            return None
        try:
            return date.fromisoformat(token).isoformat()
        except ValueError:
            return None

    def _build_prompt(self, *, meeting_content: str, project_context: dict[str, Any]) -> str:
        compact_context = {
            "project_code": project_context.get("project_code"),
            "project_title": project_context.get("project_title"),
            "partners": [item.get("short_name") for item in project_context.get("partners", [])[:40]],
            "participants": [
                {
                    "full_name": item.get("full_name"),
                    "partner_short_name": item.get("partner_short_name"),
                    "role": item.get("role"),
                }
                for item in project_context.get("participants", [])[:60]
            ],
            "work_packages": [item.get("code") for item in project_context.get("work_packages", [])[:80]],
            "tasks": [item.get("code") for item in project_context.get("tasks", [])[:120]],
            "deliverables": [item.get("code") for item in project_context.get("deliverables", [])[:120]],
            "milestones": [item.get("code") for item in project_context.get("milestones", [])[:120]],
        }
        schema = {
            "summary": "2-4 sentences",
            "action_items": [
                {
                    "description": "required",
                    "assignee_name": "optional free-text person name",
                    "due_date": "optional YYYY-MM-DD",
                    "priority": "low|normal|high|urgent",
                }
            ],
        }
        from app.agents.language_utils import language_instruction

        return (
            "You extract structured action items from project meeting notes.\n"
            "Return one JSON object only. No markdown. No commentary.\n"
            "Write the summary in 2-4 sentences covering decisions, blockers, and next steps.\n"
            "Include only concrete action items that someone should follow up on.\n"
            "If an assignee or due date is unclear, omit it.\n"
            "Use only these priorities: low, normal, high, urgent.\n\n"
            f"PROJECT CONTEXT:\n{compact_context}\n\n"
            f"OUTPUT SCHEMA:\n{schema}\n\n"
            f"MEETING CONTENT:\n{meeting_content}\n"
            + language_instruction(project_context.get("language"))
        )
