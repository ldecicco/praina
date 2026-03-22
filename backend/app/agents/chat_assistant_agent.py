import json
import logging
from typing import Any
from urllib import error, request

from app.core.config import settings

logger = logging.getLogger(__name__)


class ChatAssistantAgent:
    """
    Project-grounded assistant.
    Runtime strategy:
    1) Direct Ollama chat API
    2) Agno + Ollama model
    3) Empty string (caller applies deterministic fallback)
    """

    def generate(
        self,
        *,
        user_prompt: str,
        project_context: dict[str, Any],
        recent_messages: list[dict[str, str]],
        evidence: list[dict[str, Any]],
    ) -> str:
        prompt = self._build_prompt(
            user_prompt=user_prompt,
            project_context=project_context,
            recent_messages=recent_messages,
            evidence=evidence,
        )
        logger.info("Assistant generation prompt (full):\n%s", prompt)

        response = self._generate_with_ollama_chat(prompt, allow_compaction=True)
        if response:
            return response

        response = self._generate_with_agno(prompt)
        if response:
            return response

        return ""

    def _generate_with_agno(self, prompt: str) -> str:
        try:
            from agno.agent import Agent  # type: ignore
            from agno.models.ollama import Ollama  # type: ignore
        except Exception:
            return ""

        try:
            model = Ollama(
                id=settings.ollama_model,
                host=settings.ollama_base_url,
                options={"temperature": settings.assistant_temperature},
            )
            agent = Agent(model=model)
            result = agent.run(prompt)
        except Exception:
            return ""

        if isinstance(result, str):
            return result.strip()
        content = getattr(result, "content", None)
        if isinstance(content, str):
            return content.strip()
        return str(result).strip() if result is not None else ""

    def _generate_with_ollama_chat(self, prompt: str, *, allow_compaction: bool) -> str:
        endpoint = settings.ollama_base_url.rstrip("/") + "/api/chat"
        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "chat_template_kwargs": {
                "enable_thinking": settings.ollama_enable_thinking,
            },
            "options": {"temperature": settings.assistant_temperature},
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
            with request.urlopen(req, timeout=settings.assistant_http_timeout_seconds) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning("Assistant chat chunk decode failed: %s", exc)
                        return ""
                    api_error = chunk.get("error")
                    if api_error:
                        logger.warning("Assistant chat Ollama API error: %s", api_error)
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
            logger.warning("Assistant generation via Ollama chat failed: %s", exc)
            return ""

        full_content = "".join(content_parts).strip()
        full_thinking = "".join(thinking_parts).strip()
        logger.info(
            "Assistant chat stream summary: done_reason=%s thinking_chars=%s content_chars=%s",
            last_done_reason or "",
            len(full_thinking),
            len(full_content),
        )
        if full_content:
            return full_content
        if full_thinking and allow_compaction:
            return self._compact_thinking_to_answer(full_thinking)
        return ""

    def _compact_thinking_to_answer(self, thinking: str) -> str:
        compact_prompt = (
            "Convert the following reasoning trace into the final user-facing answer only.\n"
            "Do not include reasoning steps.\n"
            "Stay grounded in the evidence already considered.\n"
            f"Reasoning trace:\n{thinking}\n"
        )
        logger.info("Assistant compaction prompt (full):\n%s", compact_prompt)
        return self._generate_with_ollama_chat(compact_prompt, allow_compaction=False)

    def _build_prompt(
        self,
        *,
        user_prompt: str,
        project_context: dict[str, Any],
        recent_messages: list[dict[str, str]],
        evidence: list[dict[str, Any]],
    ) -> str:
        history_lines = [
            f"{item.get('role', 'unknown').upper()}: {item.get('content', '')[:600]}"
            for item in recent_messages
        ]
        evidence_lines = [
            (
                f"- [{idx + 1}] {item.get('title', 'Untitled')} (v{item.get('version', 0)}, "
                f"chunk {item.get('chunk_index', 0)}): {item.get('snippet', '')}"
            )
            for idx, item in enumerate(evidence)
        ]

        from app.agents.language_utils import language_instruction

        system_rules = (
            "You are an assistant for AI-first project management and supervision. "
            "Stay grounded in provided project context and evidence. "
            "If evidence is insufficient, state that clearly and ask a targeted follow-up. "
            "Be concise and operational. "
            "When project context includes overdue work, review gaps, open risks, or upcoming outputs, use those concrete items instead of generic alerts. "
            "If the user asks for status, delays, risks, reporting, or next actions, prioritize: overdue tasks, overdue work packages, deliverables with missing review setup, high risks, and the nearest reporting date. "
            "For each alert, explain why it matters using the provided project data."
            + language_instruction(project_context.get("language"))
        )

        proposal_phase = project_context.get("proposal_phase")
        if project_context.get("proposal_sections") and proposal_phase:
            phase_guidance = {
                "abstract_drafting": (
                    " The project is in abstract drafting phase. Help the user iteratively develop the project abstract. "
                    "Ask about objectives, innovation, expected impact, and methodology. Suggest improvements."
                ),
                "consortium_setup": (
                    " The abstract exists. Encourage the user to add consortium partners with their expertise and capabilities. "
                    "Suggest partner profiles that would strengthen the proposal."
                ),
                "wbs_generation": (
                    " The consortium is set up. Propose a work breakdown structure (WPs, tasks, deliverables, milestones) "
                    "aligned with the abstract. Assign WP/task leadership by matching partner expertise to work package topics."
                ),
                "section_writing": (
                    " Help draft proposal sections. Reference the abstract and WBS for consistency. "
                    "Use the section guidance to understand what each section requires."
                ),
            }
            extra = phase_guidance.get(proposal_phase, "")
            if extra:
                system_rules += extra

        if project_context.get("project_kind") == "teaching" or project_context.get("teaching_project"):
            system_rules += (
                " The project is a university teaching project. Treat it as a supervision domain, not as a funded consortium project. "
                "Prioritize blockers, missing artifacts, weak progress signals, supervision history, meeting context, meeting transcripts when available, and oral examination preparation. "
                "Do not assume consortium, proposal, call, partner, PI, work-package, task, deliverable, or funding structures unless they are explicitly present in the provided context. "
                "When asked for an oral examination, separate technical questions, validation questions, and weak-point questions. "
                "If asked for an assessment, give an evidence-backed analysis and keep final grading human-owned."
            )

        return (
            f"{system_rules}\n\n"
            f"PROJECT CONTEXT:\n{json.dumps(project_context, ensure_ascii=True)}\n\n"
            f"RECENT CONVERSATION:\n{chr(10).join(history_lines) if history_lines else '- (none)'}\n\n"
            f"EVIDENCE SNIPPETS:\n{chr(10).join(evidence_lines) if evidence_lines else '- (none)'}\n\n"
            f"USER QUESTION:\n{user_prompt}\n\n"
            "Write the final answer. If you use evidence, reference it as [1], [2], etc."
        )
