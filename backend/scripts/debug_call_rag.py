#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models.proposal import (  # noqa: E402
    ProposalCallBrief,
    ProposalCallLibraryDocument,
    ProposalCallLibraryDocumentChunk,
)


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def tokenize(value: str) -> list[str]:
    normalized = normalize_text(value)
    return [token for token in normalized.replace("/", " ").replace("-", " ").split() if len(token) >= 3]


def centered_snippet(text: str, query: str, radius: int = 180) -> tuple[int, str]:
    normalized_text = normalize_text(text)
    normalized_query = normalize_text(query)
    if not normalized_query:
        compact = " ".join((text or "").split())
        return -1, compact[: radius * 2]
    offset = normalized_text.find(normalized_query)
    compact = " ".join((text or "").split())
    if offset < 0:
        return -1, compact[: radius * 2]
    start = max(0, offset - radius)
    end = min(len(compact), offset + len(normalized_query) + radius)
    snippet = compact[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(compact):
        snippet = snippet + "…"
    return offset, snippet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect call-document extraction, chunks, and retrieval readiness.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project-id", help="Project ID whose linked call should be inspected.")
    group.add_argument("--call-id", help="Call library entry ID to inspect directly.")
    parser.add_argument("--text", help="Sentence or question to search in extracted text and indexed chunks.")
    parser.add_argument("--top", type=int, default=8, help="How many top chunk matches to print.")
    return parser


def resolve_call_id(session, project_id: str | None, call_id: str | None) -> str:
    if call_id:
        return call_id
    brief = session.scalar(select(ProposalCallBrief).where(ProposalCallBrief.project_id == project_id))
    if not brief or not brief.source_call_id:
        raise SystemExit(f"No linked repository call found for project {project_id}.")
    return str(brief.source_call_id)


def print_documents(session, call_id: str) -> list[ProposalCallLibraryDocument]:
    docs = session.scalars(
        select(ProposalCallLibraryDocument)
        .where(ProposalCallLibraryDocument.library_entry_id == call_id)
        .order_by(ProposalCallLibraryDocument.created_at.asc())
    ).all()
    if not docs:
        raise SystemExit(f"No call documents found for call {call_id}.")

    print(f"\nCall: {call_id}")
    print("\nDocuments")
    for doc in docs:
        chunk_count = int(
            session.scalar(
                select(func.count())
                .select_from(ProposalCallLibraryDocumentChunk)
                .where(ProposalCallLibraryDocumentChunk.document_id == doc.id)
            )
            or 0
        )
        embedded_count = int(
            session.scalar(
                select(func.count())
                .select_from(ProposalCallLibraryDocumentChunk)
                .where(
                    ProposalCallLibraryDocumentChunk.document_id == doc.id,
                    ProposalCallLibraryDocumentChunk.embedding.isnot(None),
                )
            )
            or 0
        )
        extracted_len = len(doc.extracted_text or "")
        print(
            f"- {doc.original_filename}\n"
            f"  id={doc.id}\n"
            f"  category={doc.category} status={doc.status} indexing_status={doc.indexing_status}\n"
            f"  extracted_len={extracted_len} chunks={chunk_count} embedded={embedded_count}\n"
            f"  indexed_at={doc.indexed_at} error={doc.ingestion_error or '-'}"
        )
    return docs


def search_text(session, docs: list[ProposalCallLibraryDocument], text: str, top: int) -> None:
    normalized_query = normalize_text(text)
    query_tokens = tokenize(text)
    print("\nSearch")
    print(f"text={text}")
    print(f"normalized={normalized_query}")
    print(f"tokens={query_tokens}")

    extracted_hits = []
    chunk_hits = []
    lexical_hits = []

    for doc in docs:
        extracted = doc.extracted_text or ""
        normalized_extracted = normalize_text(extracted)
        if normalized_query and normalized_query in normalized_extracted:
            extracted_hits.append(doc)

        rows = session.execute(
            select(ProposalCallLibraryDocumentChunk)
            .where(ProposalCallLibraryDocumentChunk.document_id == doc.id)
            .order_by(ProposalCallLibraryDocumentChunk.chunk_index)
        ).scalars().all()

        for chunk in rows:
            normalized_chunk = normalize_text(chunk.content or "")
            if normalized_query and normalized_query in normalized_chunk:
                chunk_hits.append((doc, chunk))

            if query_tokens:
                token_counts = Counter(tokenize(chunk.content or ""))
                score = sum(token_counts.get(token, 0) for token in query_tokens)
                if score > 0:
                    lexical_hits.append((score, doc, chunk))

    print(f"extracted_text_hits={len(extracted_hits)}")
    for doc in extracted_hits[:top]:
        print(f"  extracted_text match: {doc.original_filename} ({doc.id})")

    print(f"chunk_exact_hits={len(chunk_hits)}")
    for doc, chunk in chunk_hits[:top]:
        offset, snippet = centered_snippet(chunk.content or "", text)
        print(f"  chunk match: {doc.original_filename} chunk={chunk.chunk_index} offset={offset} snippet={snippet}")

    lexical_hits.sort(key=lambda item: item[0], reverse=True)
    print(f"top_lexical_hits={min(len(lexical_hits), top)}")
    for score, doc, chunk in lexical_hits[:top]:
        snippet = (chunk.content or "").replace("\n", " ")[:240]
        print(f"  lexical score={score} file={doc.original_filename} chunk={chunk.chunk_index} snippet={snippet}")


def main() -> None:
    args = build_parser().parse_args()
    session = SessionLocal()
    try:
        call_id = resolve_call_id(session, args.project_id, args.call_id)
        docs = print_documents(session, call_id)
        if args.text:
            search_text(session, docs, args.text, args.top)
    finally:
        session.close()


if __name__ == "__main__":
    main()
