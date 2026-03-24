from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.llm.base import LLMTextProvider


@lru_cache
def get_text_provider() -> LLMTextProvider:
    if settings.text_inference_provider == "codex":
        from app.llm.codex import CodexTextProvider

        return CodexTextProvider()
    from app.llm.ollama import OllamaTextProvider

    return OllamaTextProvider()
