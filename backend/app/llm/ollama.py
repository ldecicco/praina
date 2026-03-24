from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error, request

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaTextProvider:
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        timeout: int = 60,
    ) -> str:
        return self._generate(messages, temperature=temperature, timeout=timeout, allow_compaction=True)

    def _generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        timeout: int,
        allow_compaction: bool,
    ) -> str:
        endpoint = settings.ollama_base_url.rstrip("/") + "/api/chat"
        payload: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": messages,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": settings.ollama_enable_thinking},
            "options": {"temperature": temperature},
        }
        req = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        thinking_parts: list[str] = []
        content_parts: list[str] = []
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    api_error = chunk.get("error")
                    if api_error:
                        logger.warning("Ollama API error: %s", api_error)
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
        except (json.JSONDecodeError, error.URLError, TimeoutError, OSError) as exc:
            logger.warning("Ollama text generation failed: %s", exc)
            return ""

        content = "".join(content_parts).strip()
        if content:
            return content
        thinking = "".join(thinking_parts).strip()
        if thinking and allow_compaction:
            compact_prompt = (
                "Convert the following reasoning trace into the final user-facing answer only.\n"
                "Do not include reasoning steps.\n"
                "Return only the final answer.\n\n"
                f"{thinking}"
            )
            return self._generate(
                [{"role": "user", "content": compact_prompt}],
                temperature=temperature,
                timeout=timeout,
                allow_compaction=False,
            )
        return ""

