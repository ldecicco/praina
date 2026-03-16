import json
import logging
import re
from typing import Any
from urllib import error, request

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatActionExtractionAgent:
    """
    Extracts structured project actions from free-form natural language.
    """

    def __init__(self) -> None:
        self.last_error: str | None = None

    def extract(self, *, user_prompt: str, project_context: dict[str, Any]) -> dict[str, Any] | None:
        self.last_error = None
        prompt = self._build_prompt(user_prompt=user_prompt, project_context=project_context)
        logger.info("Action extraction prompt (full):\n%s", prompt)

        raw = self._generate_with_ollama_chat(prompt, allow_compaction=True)
        if not raw:
            if not self.last_error:
                self._append_error("LLM did not return a response")
            return None

        payload = self._parse_json(raw)
        if not payload:
            self._append_error("LLM returned non-JSON output for action extraction")
            return None
        return self._normalize(payload)

    def _generate_with_ollama_chat(self, prompt: str, *, allow_compaction: bool) -> str:
        endpoint = settings.ollama_base_url.rstrip("/") + "/api/chat"
        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "chat_template_kwargs": {
                "enable_thinking": settings.ollama_enable_thinking,
            },
            "options": {"temperature": 0},
        }
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        thinking_parts: list[str] = []
        content_parts: list[str] = []
        last_done_reason = ""
        try:
            with request.urlopen(req, timeout=settings.action_extraction_http_timeout_seconds) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        self._append_error(f"Ollama chat stream returned invalid JSON chunk: {exc}")
                        logger.warning("Action extraction chat chunk decode failed: %s", exc)
                        return ""
                    api_error = chunk.get("error")
                    if api_error:
                        self._append_error(f"Ollama API error: {api_error}")
                        return ""
                    message = chunk.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str) and content:
                            content_parts.append(content)
                        thinking = message.get("thinking")
                        if isinstance(thinking, str) and thinking:
                            thinking_parts.append(thinking)
                    top_level_thinking = chunk.get("thinking")
                    if isinstance(top_level_thinking, str) and top_level_thinking:
                        thinking_parts.append(top_level_thinking)
                    if chunk.get("done"):
                        done_reason = chunk.get("done_reason")
                        if isinstance(done_reason, str):
                            last_done_reason = done_reason
        except (error.URLError, TimeoutError, OSError) as exc:
            self._append_error(f"Ollama chat extraction failed at {endpoint}: {exc}")
            logger.warning("Action extraction via Ollama chat failed: %s", exc)
            return ""

        full_content = "".join(content_parts).strip()
        full_thinking = "".join(thinking_parts).strip()
        logger.info(
            "Action extraction chat stream summary: done_reason=%s thinking_chars=%s content_chars=%s",
            last_done_reason or "",
            len(full_thinking),
            len(full_content),
        )
        if full_content:
            return full_content
        if full_thinking:
            json_from_thinking = self._extract_last_json_object(full_thinking)
            if json_from_thinking:
                return json_from_thinking
            if allow_compaction:
                compacted = self._compact_thinking_to_json(full_thinking)
                if compacted:
                    return compacted
        self._append_error(
            "Ollama chat stream produced no final content"
            + (f" (done_reason={last_done_reason})" if last_done_reason else "")
        )
        return ""

    def _compact_thinking_to_json(self, thinking: str) -> str:
        compact_prompt = (
            "Convert the following reasoning trace into the final structured JSON only.\n"
            "Return one valid JSON object and nothing else.\n"
            "If the reasoning describes multiple ordered actions, return `actions`.\n"
            f"Reasoning trace:\n{thinking}\n"
        )
        logger.info("Action extraction compaction prompt (full):\n%s", compact_prompt)
        return self._generate_with_ollama_chat(compact_prompt, allow_compaction=False)

    def _extract_last_json_object(self, text: str) -> str:
        matches = re.findall(r"\{.*\}", text, flags=re.DOTALL)
        if not matches:
            return ""
        for candidate in reversed(matches):
            snippet = candidate.strip()
            try:
                json.loads(snippet)
            except json.JSONDecodeError:
                continue
            return snippet
        return ""

    def _append_error(self, detail: str) -> None:
        detail = (detail or "").strip()
        if not detail:
            return
        if not self.last_error:
            self.last_error = detail
            return
        if detail in self.last_error:
            return
        self.last_error = f"{self.last_error}; {detail}"

    def _parse_json(self, raw: str) -> dict[str, Any] | None:
        text = raw.strip()
        if not text:
            return None

        # Remove optional fenced markdown wrapper if model emits one.
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            snippet = text[start : end + 1]
            try:
                data = json.loads(snippet)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                return None
        return None

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("actions"), list):
            actions: list[dict[str, Any]] = []
            for item in payload.get("actions", []):
                if not isinstance(item, dict):
                    continue
                normalized_item = self._normalize_single_action(item)
                if normalized_item["is_action_request"]:
                    actions.append(normalized_item)
            return {
                "is_action_request": len(actions) > 0,
                "actions": actions,
                "missing_fields": [str(item).strip().lower() for item in payload.get("missing_fields", []) if str(item).strip()],
                "confidence": self._safe_confidence(payload.get("confidence", 0)),
            }
        return self._normalize_single_action(payload)

    def _normalize_single_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        action_raw = str(payload.get("action_type", payload.get("action", "none"))).strip().lower()
        action_aliases = {
            "add": "create",
            "create": "create",
            "new": "create",
            "insert": "create",
            "update": "update",
            "edit": "update",
            "modify": "update",
            "change": "update",
        }
        action = action_aliases.get(action_raw, "none")

        entity = str(payload.get("entity_type", payload.get("entity", "none"))).strip().lower()
        entity = {
            "project settings": "project",
            "wp": "work_package",
            "workpackage": "work_package",
            "work-package": "work_package",
            "work package": "work_package",
            "tasks": "task",
            "deliverables": "deliverable",
            "milestones": "milestone",
        }.get(entity, entity)
        if entity not in {"project", "work_package", "task", "deliverable", "milestone"}:
            entity = "none"

        explicit_is_action = payload.get("is_action_request")
        inferred_is_action = action != "none" and entity != "none"
        if explicit_is_action is None:
            is_action = inferred_is_action
        else:
            is_action = bool(explicit_is_action) or inferred_is_action

        raw_fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
        key_aliases = {
            "leader_partner": "leader",
            "leader_partner_short_name": "leader",
            "responsible_person": "responsible",
            "responsible_person_name": "responsible",
            "responsible_email": "responsible",
            "work_package": "wp",
            "work_packages": "wps",
            "wp_code": "wp",
            "wp_codes": "wps",
            "target_code": "target",
        }
        fields: dict[str, str] = {}
        for key, value in raw_fields.items():
            raw_key = str(key).strip().lower()
            normalized_key = key_aliases.get(raw_key, raw_key)
            if normalized_key == "":
                continue
            if value is None:
                continue
            if isinstance(value, list):
                token = ",".join(str(item).strip() for item in value if str(item).strip())
            else:
                token = str(value).strip()
            if token:
                if normalized_key in {"start_month", "end_month", "due_month"}:
                    month_match = re.fullmatch(r"(?i)m?(\d+)", token)
                    if month_match:
                        token = month_match.group(1)
                fields[normalized_key] = token

        missing_raw = payload.get("missing_fields", [])
        missing_fields = [str(item).strip().lower() for item in missing_raw if str(item).strip()]

        return {
            "is_action_request": is_action,
            "action_type": action,
            "entity_type": entity,
            "fields": fields,
            "missing_fields": missing_fields,
            "confidence": self._safe_confidence(payload.get("confidence", 0)),
        }

    def _safe_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.0
        return max(0.0, min(1.0, confidence))

    def _build_prompt(self, *, user_prompt: str, project_context: dict[str, Any]) -> str:  # noqa: C901
        from app.agents.language_utils import language_instruction
        partners = [item.get("short_name") for item in project_context.get("partners", []) if item.get("short_name")]
        participants = [
            {
                "name": item.get("full_name"),
                "partner": item.get("partner_short_name"),
                "email": item.get("email"),
            }
            for item in project_context.get("participants", [])
        ]
        work_packages = [item.get("code") for item in project_context.get("work_packages", []) if item.get("code")]
        tasks = [item.get("code") for item in project_context.get("tasks", []) if item.get("code")]
        deliverables = [item.get("code") for item in project_context.get("deliverables", []) if item.get("code")]
        milestones = [item.get("code") for item in project_context.get("milestones", []) if item.get("code")]

        partner_entries = []
        for item in project_context.get("partners", []):
            entry: dict[str, Any] = {"short_name": item.get("short_name")}
            if item.get("expertise"):
                entry["expertise"] = item["expertise"]
            partner_entries.append(entry)

        compact_context = {
            "project_code": project_context.get("project_code"),
            "start_date": project_context.get("start_date"),
            "duration_months": project_context.get("duration_months"),
            "reporting_dates": project_context.get("reporting_dates"),
            "partners": partner_entries[:60],
            "participants": participants[:40],
            "work_packages": work_packages[:80],
            "tasks": tasks[:120],
            "deliverables": deliverables[:120],
            "milestones": milestones[:120],
        }

        schema = {
            "is_action_request": True,
            "action_type": "create|update|none",
            "entity_type": "project|work_package|task|deliverable|milestone|none",
            "fields": {
                "target": "entity code for updates",
                "wp": "single wp code",
                "wps": "comma-separated wp codes",
                "code": "new code",
                "title": "title",
                "description": "description",
                "start_date": "YYYY-MM-DD date for project",
                "duration_months": "integer month number for project",
                "reporting_dates": "comma-separated YYYY-MM-DD dates for project",
                "start_month": "integer month number",
                "end_month": "integer month number",
                "due_month": "integer month number",
                "leader": "partner short name",
                "responsible": "full name or email",
                "collaborators": "comma-separated partner short names",
            },
            "actions": ["ordered list of action objects using the same shape when the user asks for multiple changes"],
            "missing_fields": ["required fields that are missing"],
            "confidence": 0.0,
        }

        return (
            "Task: convert the user request into one JSON object for project mutations.\n"
            "Think briefly, then output the final JSON object.\n"
            "Output rules: JSON only, no markdown, no prose.\n"
            "Use `action_type` create/update and `entity_type` project/work_package/task/deliverable/milestone.\n"
            "Use `actions` for multiple ordered actions. Dependent actions must come later.\n"
            "Field mapping: `leader`=partner short name, `responsible`=person full name or email, "
            "`wp`=single WP code, `wps`=comma-separated WP codes, `M6` -> `6`, "
            "`reporting_dates`=comma-separated YYYY-MM-DD dates.\n"
            "If anything required is missing, list it in `missing_fields`.\n"
            "For project settings updates use `entity_type`=`project` and include only changed fields.\n"
            "Example single action:\n"
            "{\"is_action_request\":true,\"action_type\":\"create\",\"entity_type\":\"task\",\"fields\":{\"code\":\"T1.2\",\"title\":\"Architecture\",\"leader\":\"POLIBA\",\"responsible\":\"Gioacchino Manfredi\",\"wp\":\"WP1\"},\"missing_fields\":[],\"confidence\":0.92}\n"
            "Example project update:\n"
            "{\"is_action_request\":true,\"action_type\":\"update\",\"entity_type\":\"project\",\"fields\":{\"duration_months\":\"30\",\"reporting_dates\":\"2026-12-31,2027-12-31\"},\"missing_fields\":[],\"confidence\":0.91}\n"
            "Example batch:\n"
            "{\"is_action_request\":true,\"actions\":[{\"action_type\":\"create\",\"entity_type\":\"work_package\",\"fields\":{\"code\":\"WP2\",\"title\":\"Chatbot\",\"start_month\":\"6\",\"end_month\":\"12\",\"leader\":\"POLIBA\",\"responsible\":\"Saverio Mascolo\"}},{\"action_type\":\"create\",\"entity_type\":\"task\",\"fields\":{\"code\":\"T2.1\",\"title\":\"Chatbot design\",\"start_month\":\"6\",\"end_month\":\"8\",\"leader\":\"POLIBA\",\"responsible\":\"Gioacchino Manfredi\",\"wp\":\"WP2\"}}],\"missing_fields\":[],\"confidence\":0.93}\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=True)}\n"
            f"Project:\n{json.dumps(compact_context, ensure_ascii=True)}\n"
            f"User:\n{user_prompt}\n"
            + language_instruction(project_context.get("language"))
        )
