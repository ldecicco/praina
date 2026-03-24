from __future__ import annotations

import json
import re
from typing import Any


def strip_json_fences(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_json_object(raw: str) -> str:
    text = strip_json_fences(raw)
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return text
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not fence_match:
        return ""
    snippet = fence_match.group(0).strip()
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return ""
    return snippet if isinstance(parsed, dict) else ""


def parse_json_object(raw: str) -> dict[str, Any] | None:
    snippet = extract_json_object(raw)
    if not snippet:
        return None
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None

