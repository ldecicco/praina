from __future__ import annotations

import json
import re
import unicodedata
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.factory import get_text_provider
from app.llm.json_utils import parse_json_object
from app.models.proposal import ProposalCallBrief, ProposalCallLibraryDocument, ProposalCallLibraryDocumentChunk
from app.services.embedding_service import EmbeddingService
from app.services.onboarding_service import NotFoundError, ValidationError

TOKEN_RE = re.compile(r"[\w]{3,}", flags=re.IGNORECASE | re.UNICODE)
MAX_RETRIEVED_CHUNKS = 10
MAX_SEMANTIC_CANDIDATES = 24
NEIGHBOR_WINDOW = 1

CALL_QA_SYSTEM_PROMPT = """
You answer questions about a funding call using only the provided evidence chunks.

Return ONLY valid JSON with this exact shape:
{
  "answer": "",
  "grounded": true,
  "used_citation_indexes": [],
  "insufficient_reason": null
}

Rules:
- Use only the provided evidence.
- Never invent facts, eligibility rules, deadlines, budgets, or requirements.
- If the evidence is insufficient, say so directly in the answer and set grounded to false.
- Use used_citation_indexes to reference the evidence items that support the answer.
- If the answer is explicitly stated in the evidence, answer directly and do not default to insufficient.
- Prefer quoting or tightly paraphrasing the exact evidence instead of making broad interpretations.
- Keep the answer concise and factual.
""".strip()


@dataclass
class CallCitation:
    library_entry_id: str
    document_id: str
    document_title: str
    chunk_index: int
    content: str
    snippet: str
    score: float
    lexical_score: float = 0.0
    vector_score: float = 0.0
    combined_score: float = 0.0


class ProposalCallQAService:
    def __init__(self, db: Session):
        self.db = db
        self.provider = get_text_provider()
        self.embedding_service = EmbeddingService(db)

    def answer_question(self, project_id: uuid.UUID, question: str) -> tuple[dict[str, Any], list[CallCitation]]:
        brief = self.db.scalar(select(ProposalCallBrief).where(ProposalCallBrief.project_id == project_id))
        if not brief or not brief.source_call_id:
            raise ValidationError("No repository call is linked to this project.")

        question_text = (question or "").strip()
        if not question_text:
            raise ValidationError("Question cannot be empty.")

        citations = self._retrieve_call_citations(brief.source_call_id, question_text)
        if not citations:
            return {
                "answer": "I could not find supporting evidence in the indexed call documents for that question.",
                "grounded": False,
                "used_citation_indexes": [],
                "insufficient_reason": "No relevant source chunks were found.",
            }, []

        try:
            answer = self._grounded_answer(question_text, citations)
        except ValidationError as exc:
            answer = self._direct_evidence_fallback(citations, str(exc))
        used_indexes = [
            index
            for index in answer.get("used_citation_indexes", [])
            if isinstance(index, int) and 0 <= index < len(citations)
        ]
        if not used_indexes and citations:
            used_indexes = [0]
        answer["used_citation_indexes"] = used_indexes
        if not answer.get("grounded") and citations:
            fallback = self._extractive_fallback(question_text, citations)
            if fallback:
                answer = fallback
        return answer, citations

    def _retrieve_call_citations(self, library_entry_id: uuid.UUID, question: str) -> list[CallCitation]:
        query_tokens = self._tokens(question)
        normalized_question = self._normalize_text(question)
        if not query_tokens:
            raise ValidationError("Question is too vague to retrieve supporting evidence.")

        active_docs = self.db.scalars(
            select(ProposalCallLibraryDocument).where(
                ProposalCallLibraryDocument.library_entry_id == library_entry_id,
                ProposalCallLibraryDocument.status == "active",
            )
        ).all()
        if not active_docs:
            raise NotFoundError("No active source documents are available for this call.")

        active_doc_ids = [doc.id for doc in active_docs]
        chunk_rows = self.db.execute(
            select(ProposalCallLibraryDocumentChunk, ProposalCallLibraryDocument)
            .join(ProposalCallLibraryDocument, ProposalCallLibraryDocumentChunk.document_id == ProposalCallLibraryDocument.id)
            .where(
                ProposalCallLibraryDocument.library_entry_id == library_entry_id,
                ProposalCallLibraryDocument.status == "active",
                ProposalCallLibraryDocument.indexing_status == "indexed",
            )
            .order_by(ProposalCallLibraryDocument.created_at.asc(), ProposalCallLibraryDocumentChunk.chunk_index.asc())
        ).all()
        if not chunk_rows:
            if active_doc_ids:
                raise ValidationError("Call documents are not indexed yet. Re-index the documents and try again.")
            raise ValidationError("No source documents are available for this call.")

        lexical_scores: dict[str, float] = {}
        phrase_scores: dict[str, float] = {}
        chunk_lookup: dict[str, tuple[ProposalCallLibraryDocumentChunk, ProposalCallLibraryDocument]] = {}
        chunk_by_doc_and_index: dict[tuple[str, int], tuple[ProposalCallLibraryDocumentChunk, ProposalCallLibraryDocument]] = {}
        doc_freq: Counter[str] = Counter()
        chunk_tokens: dict[str, list[str]] = {}
        normalized_chunk_text: dict[str, str] = {}

        for chunk, document in chunk_rows:
            chunk_id = str(chunk.id)
            tokens = self._tokens(chunk.content or "")
            if not tokens:
                continue
            chunk_lookup[chunk_id] = (chunk, document)
            chunk_by_doc_and_index[(str(document.id), int(chunk.chunk_index))] = (chunk, document)
            chunk_tokens[chunk_id] = tokens
            normalized_chunk_text[chunk_id] = self._normalize_text(chunk.content or "")
            token_set = set(tokens)
            for token in set(query_tokens):
                if token in token_set:
                    doc_freq[token] += 1

        total_chunks = max(1, len(chunk_tokens))
        idf = {
            token: max(1.0, (total_chunks + 1) / (doc_freq.get(token, 0) + 1))
            for token in set(query_tokens)
        }

        query_token_set = set(query_tokens)
        for chunk_id, tokens in chunk_tokens.items():
            token_counts = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                score += token_counts.get(token, 0) * idf.get(token, 1.0)
            overlap = len(query_token_set & set(tokens))
            if overlap:
                score += overlap * 0.75
            if score > 0:
                lexical_scores[chunk_id] = score

        if normalized_question and len(normalized_question) >= 16:
            for chunk_id, text in normalized_chunk_text.items():
                if normalized_question in text:
                    phrase_scores[chunk_id] = max(phrase_scores.get(chunk_id, 0.0), 1.0)
            for (doc_id, chunk_index), (chunk, _document) in chunk_by_doc_and_index.items():
                next_neighbor = chunk_by_doc_and_index.get((doc_id, chunk_index + 1))
                if not next_neighbor:
                    continue
                next_chunk, _ = next_neighbor
                combined_text = f"{self._normalize_text(chunk.content or '')} {self._normalize_text(next_chunk.content or '')}".strip()
                if normalized_question in combined_text:
                    phrase_scores[str(chunk.id)] = max(phrase_scores.get(str(chunk.id), 0.0), 0.8)
                    phrase_scores[str(next_chunk.id)] = max(phrase_scores.get(str(next_chunk.id), 0.0), 0.8)

        vector_scores: dict[str, float] = {}
        try:
            question_embedding = self.embedding_service.embed_texts([question])[0]
            cosine_distance = ProposalCallLibraryDocumentChunk.embedding.cosine_distance(question_embedding)
            vector_rows = self.db.execute(
                select(ProposalCallLibraryDocumentChunk, (1 - cosine_distance).label("similarity"))
                .join(ProposalCallLibraryDocument, ProposalCallLibraryDocumentChunk.document_id == ProposalCallLibraryDocument.id)
                .where(
                    ProposalCallLibraryDocument.library_entry_id == library_entry_id,
                    ProposalCallLibraryDocument.status == "active",
                    ProposalCallLibraryDocument.indexing_status == "indexed",
                    ProposalCallLibraryDocumentChunk.embedding.isnot(None),
                )
                .order_by(cosine_distance)
                .limit(MAX_SEMANTIC_CANDIDATES)
            ).all()
            for chunk, similarity in vector_rows:
                vector_scores[str(chunk.id)] = max(0.0, float(similarity or 0.0))
        except Exception:
            vector_scores = {}

        max_lexical = max(lexical_scores.values(), default=0.0) or 1.0
        scored_chunks: list[tuple[float, ProposalCallLibraryDocumentChunk, ProposalCallLibraryDocument]] = []
        for chunk_id, (chunk, document) in chunk_lookup.items():
            phrase = phrase_scores.get(chunk_id, 0.0)
            lexical = lexical_scores.get(chunk_id, 0.0) / max_lexical
            vector = vector_scores.get(chunk_id, 0.0)
            combined = phrase * 2.0 + lexical * 0.5 + vector * 0.25
            if combined <= 0:
                continue
            scored_chunks.append(
                (
                    combined,
                    chunk,
                    document,
                )
            )

        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        selected_keys: set[tuple[str, int]] = set()
        expanded: list[CallCitation] = []
        for score, chunk, document in scored_chunks[:MAX_RETRIEVED_CHUNKS]:
            doc_key = str(document.id)
            for offset in range(-NEIGHBOR_WINDOW, NEIGHBOR_WINDOW + 1):
                neighbor_key = (doc_key, int(chunk.chunk_index) + offset)
                if neighbor_key in selected_keys:
                    continue
                neighbor = chunk_by_doc_and_index.get(neighbor_key)
                if not neighbor:
                    continue
                neighbor_chunk, neighbor_doc = neighbor
                selected_keys.add(neighbor_key)
                expanded.append(
                    CallCitation(
                        library_entry_id=str(neighbor_doc.library_entry_id),
                        document_id=str(neighbor_doc.id),
                        document_title=neighbor_doc.original_filename,
                        chunk_index=neighbor_chunk.chunk_index,
                        content=neighbor_chunk.content or "",
                        snippet=self._snippet(neighbor_chunk.content),
                        score=score - (abs(offset) * 0.05),
                        lexical_score=(phrase_scores.get(str(chunk.id), 0.0) * 2.0) + lexical_scores.get(str(chunk.id), 0.0),
                        vector_score=vector_scores.get(str(chunk.id), 0.0),
                        combined_score=score,
                    )
                )
                if len(expanded) >= MAX_RETRIEVED_CHUNKS:
                    break
            if len(expanded) >= MAX_RETRIEVED_CHUNKS:
                break
        return expanded

    def _grounded_answer(self, question: str, citations: list[CallCitation]) -> dict[str, Any]:
        evidence_lines = []
        for index, citation in enumerate(citations):
            evidence_lines.append(
                f"[{index}] {citation.document_title} chunk {citation.chunk_index}\n{citation.content}"
            )
        raw = self._chat_json(
            CALL_QA_SYSTEM_PROMPT,
            (
                f"Question:\n{question}\n\n"
                "Evidence:\n"
                + "\n\n".join(evidence_lines)
            ),
        )
        if not isinstance(raw, dict):
            raise ValidationError("Call QA returned an invalid response.")
        answer = {
            "answer": str(raw.get("answer") or "").strip() or "I could not produce a grounded answer from the available evidence.",
            "grounded": bool(raw.get("grounded")),
            "used_citation_indexes": raw.get("used_citation_indexes") or [],
            "insufficient_reason": str(raw.get("insufficient_reason")).strip() if raw.get("insufficient_reason") else None,
        }
        if not answer["grounded"] and citations:
            retry = self._chat_json(
                CALL_QA_SYSTEM_PROMPT,
                (
                    f"Question:\n{question}\n\n"
                    "The previous answer was too conservative. Re-check the same evidence carefully.\n"
                    "If the answer is explicitly present in any chunk, answer it directly and cite those chunks.\n\n"
                    "Evidence:\n"
                    + "\n\n".join(evidence_lines)
                ),
            )
            if isinstance(retry, dict) and retry.get("grounded"):
                answer = {
                    "answer": str(retry.get("answer") or "").strip() or answer["answer"],
                    "grounded": True,
                    "used_citation_indexes": retry.get("used_citation_indexes") or [],
                    "insufficient_reason": str(retry.get("insufficient_reason")).strip() if retry.get("insufficient_reason") else None,
                }
        return answer

    def _extractive_fallback(self, question: str, citations: list[CallCitation]) -> dict[str, Any] | None:
        system = """
You answer a funding call question only from the provided evidence.

Return ONLY valid JSON:
{
  "answer": "",
  "grounded": true,
  "used_citation_indexes": []
}

Rules:
- Do not refuse if the answer is explicitly present in the evidence.
- Use only the retrieved evidence.
- Keep the answer short and concrete.
- Cite the chunks that directly support the answer.
""".strip()
        evidence_lines = []
        for index, citation in enumerate(citations[:4]):
            evidence_lines.append(f"[{index}] {citation.document_title} chunk {citation.chunk_index}\n{citation.content}")
        try:
            raw = self._chat_json(
                system,
                f"Question:\n{question}\n\nEvidence:\n" + "\n\n".join(evidence_lines),
            )
        except ValidationError:
            return None
        if not isinstance(raw, dict):
            return None
        answer = str(raw.get("answer") or "").strip()
        indexes = [i for i in (raw.get("used_citation_indexes") or []) if isinstance(i, int) and 0 <= i < len(citations[:4])]
        if not answer or not indexes:
            return None
        return {
            "answer": answer,
            "grounded": True,
            "used_citation_indexes": indexes,
            "insufficient_reason": None,
        }

    def _direct_evidence_fallback(self, citations: list[CallCitation], reason: str | None = None) -> dict[str, Any]:
        if not citations:
            return {
                "answer": "I could not find supporting evidence in the indexed call documents for that question.",
                "grounded": False,
                "used_citation_indexes": [],
                "insufficient_reason": reason or "No relevant source chunks were found.",
            }
        citation = citations[0]
        answer = f"I could not complete answer generation in time. Most relevant evidence: {citation.snippet}"
        return {
            "answer": answer,
            "grounded": True,
            "used_citation_indexes": [0],
            "insufficient_reason": reason or "Answer generation timed out.",
        }

    def _chat_json(self, system: str, user: str) -> dict[str, Any]:
        try:
            raw = self.provider.generate(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=settings.call_qa_http_timeout_seconds,
            )
        except TimeoutError as exc:
            raise ValidationError("Call QA timed out while generating the answer.") from exc
        except Exception as exc:
            raise ValidationError("Call QA request failed.") from exc
        parsed = parse_json_object(raw)
        if parsed is None:
            raise ValidationError("Call QA returned an invalid payload.")
        return parsed

    def _tokens(self, text: str) -> list[str]:
        normalized = self._normalize_text(text or "")
        return [match.group(0).lower() for match in TOKEN_RE.finditer(normalized) if len(match.group(0)) >= 3]

    def _snippet(self, text: str, max_len: int = 320) -> str:
        compact = " ".join((text or "").split())
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 1].rstrip() + "…"

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return stripped.lower()
