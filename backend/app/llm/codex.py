from __future__ import annotations

import json
import logging
import subprocess

from app.core.config import settings

logger = logging.getLogger(__name__)


def _format_messages(messages: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for item in messages:
        role = str(item.get("role") or "user").upper()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role}:\n{content}")
    return "\n\n".join(parts).strip()


class CodexTextProvider:
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        timeout: int = 60,
    ) -> str:
        prompt = _format_messages(messages)
        if not prompt:
            return ""
        prompt_preview = "\n---\n".join(
            f"[{m.get('role', 'user')}] {(m.get('content') or '')[:500]}"
            for m in messages
        )
        logger.info(
            "LLM request  model=%s timeout=%ds messages=%d\n%s",
            settings.codex_model, timeout, len(messages), prompt_preview,
        )
        effective_timeout = max(1, min(timeout, settings.codex_timeout_seconds))
        try:
            result = subprocess.run(
                [
                    "codex",
                    "exec",
                    "--json",
                    "--skip-git-repo-check",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "-m",
                    settings.codex_model,
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Codex text generation failed: %s", exc)
            return ""

        messages_out: list[str] = []
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "agent_message":
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                messages_out.append(text.strip())
        if messages_out:
            output = "\n\n".join(messages_out).strip()
            logger.info("LLM response model=%s length=%d chars", settings.codex_model, len(output))
            return output
        if result.returncode != 0:
            logger.warning("Codex exited with code %s: %s", result.returncode, (result.stderr or "").strip())
        logger.info("LLM response model=%s length=0 chars (empty)", settings.codex_model)
        return ""
