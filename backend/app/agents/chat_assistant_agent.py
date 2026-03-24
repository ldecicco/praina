import json
import logging
from typing import Any

from app.core.config import settings
from app.llm.factory import get_text_provider

logger = logging.getLogger(__name__)


class ChatAssistantAgent:
    """
    Project-grounded assistant.
    Runtime strategy:
    1) Active text provider
    2) Empty string (caller applies deterministic fallback)
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
        return get_text_provider().generate(
            [{"role": "user", "content": prompt}],
            temperature=settings.assistant_temperature,
            timeout=settings.assistant_http_timeout_seconds,
        )

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

        if project_context.get("resources"):
            system_rules += (
                " Resource and equipment usage may affect project execution. "
                "When the context includes equipment requirements, bookings, downtime, conflicts, or blocker-days, use those as concrete operational evidence. "
                "Treat cancelled bookings as historical context, not active constraints, unless the user explicitly asks for history."
            )

        return (
            f"{system_rules}\n\n"
            f"PROJECT CONTEXT:\n{json.dumps(project_context, ensure_ascii=True)}\n\n"
            f"RECENT CONVERSATION:\n{chr(10).join(history_lines) if history_lines else '- (none)'}\n\n"
            f"EVIDENCE SNIPPETS:\n{chr(10).join(evidence_lines) if evidence_lines else '- (none)'}\n\n"
            f"USER QUESTION:\n{user_prompt}\n\n"
            "Write the final answer. If you use evidence, reference it as [1], [2], etc."
        )
