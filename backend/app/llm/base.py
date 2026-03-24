from __future__ import annotations

from typing import Protocol


class LLMTextProvider(Protocol):
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        timeout: int = 60,
    ) -> str:
        """Send messages and return the text response. Returns empty string on failure."""
        ...

