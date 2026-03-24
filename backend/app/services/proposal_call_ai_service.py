from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.llm.factory import get_text_provider
from app.llm.json_utils import parse_json_object
from app.services.onboarding_service import ValidationError
from app.services.text_extraction import chunk_text

CALL_FIELD_KEYS = [
    "call_title",
    "funder_name",
    "programme_name",
    "reference_code",
    "submission_deadline",
    "source_url",
    "summary",
    "eligibility_notes",
    "budget_notes",
    "scoring_notes",
    "requirements_text",
]

CALL_EXTRACTION_SYSTEM_PROMPT = """
You extract structured funding call data from source text.

Return ONLY valid JSON with this exact shape:
{
  "call_title": null,
  "funder_name": null,
  "programme_name": null,
  "reference_code": null,
  "submission_deadline": null,
  "source_url": null,
  "summary": null,
  "eligibility_notes": null,
  "budget_notes": null,
  "scoring_notes": null,
  "requirements_text": null
}

Rules:
- Use ISO date format YYYY-MM-DD for submission_deadline when known, else null.
- Extract only information explicitly present or strongly implied in the source text.
- Keep summary concise.
- Put long-form requirement lists into requirements_text.
- Do not invent URLs or deadlines.
- If a field is not supported by the chunk, return null for that field.
""".strip()

CALL_REDUCE_SYSTEM_PROMPT = """
You consolidate partial funding call extractions into one final structured record.

Return ONLY valid JSON with this exact shape:
{
  "call_title": null,
  "funder_name": null,
  "programme_name": null,
  "reference_code": null,
  "submission_deadline": null,
  "source_url": null,
  "summary": null,
  "eligibility_notes": null,
  "budget_notes": null,
  "scoring_notes": null,
  "requirements_text": null
}

Rules:
- Merge information conservatively.
- Prefer more specific values over generic ones.
- Keep submission_deadline in ISO date format YYYY-MM-DD when known, else null.
- Combine complementary notes for eligibility, budget, scoring, and requirements instead of dropping them.
- Do not invent values that are not supported by the partial extractions.
""".strip()

logger = logging.getLogger(__name__)


class ProposalCallAIService:
    def __init__(self) -> None:
        self.provider = get_text_provider()

    def extract_call_fields(
        self,
        text: str,
        source_url: str | None = None,
        progress_callback: callable | None = None,
        stream_callback: callable | None = None,
    ) -> dict[str, Any]:
        chunks = self.build_chunks(text)
        partials: list[dict[str, Any]] = []

        for index, chunk in enumerate(chunks, start=1):
            partial = self._extract_chunk_fields(
                chunk,
                source_url=source_url,
                chunk_index=index,
                chunk_count=len(chunks),
                stream_callback=stream_callback,
            )
            if partial:
                partials.append(partial)
            if progress_callback:
                progress_callback(index, len(chunks))

        if not partials:
            raise ValidationError("Call extraction did not return any usable data. Try again or enter the call manually.")
        if len(partials) == 1:
            return partials[0]
        return self._reduce_partial_fields(partials, source_url=source_url, stream_callback=stream_callback)

    def build_chunks(self, text: str) -> list[str]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return []
        raw_chunks = chunk_text(cleaned)
        merged_chunks: list[str] = []
        current = ""
        for chunk in raw_chunks:
            if not current:
                current = chunk
                continue
            if len(current) + len(chunk) + 2 <= 6000:
                current = f"{current}\n\n{chunk}"
            else:
                merged_chunks.append(current)
                current = chunk
        if current:
            merged_chunks.append(current)
        return merged_chunks[:12]

    def _extract_chunk_fields(
        self,
        chunk_text_value: str,
        *,
        source_url: str | None,
        chunk_index: int,
        chunk_count: int,
        stream_callback: callable | None = None,
    ) -> dict[str, Any]:
        raw = self._chat(
            system=CALL_EXTRACTION_SYSTEM_PROMPT,
            user=(
                "Extract the funding call fields from this source chunk.\n"
                f"Source URL: {source_url or '-'}\n"
                f"Chunk: {chunk_index}/{chunk_count}\n"
                f"Source Text:\n{chunk_text_value}"
            ),
            stream_callback=stream_callback,
        )
        return self._parse_json_payload(raw)

    def _reduce_partial_fields(
        self,
        partials: list[dict[str, Any]],
        *,
        source_url: str | None,
        stream_callback: callable | None = None,
    ) -> dict[str, Any]:
        partial_payload = json.dumps(
            [
                {key: partial.get(key) for key in CALL_FIELD_KEYS}
                for partial in partials
            ],
            ensure_ascii=True,
        )
        raw = self._chat(
            system=CALL_REDUCE_SYSTEM_PROMPT,
            user=(
                "Merge these partial funding call extractions into one final call record.\n"
                f"Source URL: {source_url or '-'}\n"
                f"Partial Extractions:\n{partial_payload}"
            ),
            stream_callback=stream_callback,
        )
        return self._parse_json_payload(raw)

    def _chat(self, *, system: str, user: str, stream_callback: callable | None = None) -> str:
        try:
            raw = self.provider.generate(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=settings.call_extraction_http_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Call extraction timed out against active provider: %s", exc)
            raise ValidationError("Call extraction timed out. Try again, use a smaller PDF, or extract the call manually.") from exc
        raw = (raw or "").strip()
        if stream_callback and raw:
            stream_callback(raw)
        if not raw:
            raise ValidationError("Call extraction returned an empty response.")
        return raw

    def _parse_json_payload(self, raw: str) -> dict[str, Any]:
        parsed = parse_json_object(raw)
        if parsed is None:
            logger.warning("Call extraction returned invalid JSON")
            raise ValidationError("Call extraction returned an invalid response. Try again or enter the call manually.")
        return {key: parsed.get(key) for key in CALL_FIELD_KEYS}
