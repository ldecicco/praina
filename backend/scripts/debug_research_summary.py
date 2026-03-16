#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import ProjectDocument
from app.models.research import ResearchReference
from app.services.onboarding_service import NotFoundError
from app.services.research_ai_service import (
    FINAL_SYNTHESIS_SYSTEM_PROMPT,
    MAP_SUMMARY_SYSTEM_PROMPT,
    REDUCE_SUMMARY_SYSTEM_PROMPT,
    ResearchAIService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug the research reference summarization pipeline.")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--reference-id", required=True, help="Research reference UUID")
    parser.add_argument(
        "--run-llm",
        action="store_true",
        help="Run map/reduce/final LLM steps. Without this flag the script prints deterministic pipeline inputs only.",
    )
    return parser


def print_json(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def print_chunks(title: str, chunks: list[Any]) -> None:
    print(f"\n=== {title} ({len(chunks)}) ===")
    for chunk in chunks:
        print(
            json.dumps(
                {
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "role": chunk.role,
                    "score": round(chunk.score, 4),
                    "position_bucket": chunk.position_bucket,
                    "reasons": sorted(chunk.reasons),
                    "content_preview": chunk.content[:300],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


def print_llm_prompt(step: str, system_prompt: str, user_prompt: str) -> None:
    print(f"\n=== LLM prompt [{step}] ===")
    print("System:")
    print(system_prompt)
    print("\nUser:")
    print(user_prompt)


def main() -> int:
    args = build_parser().parse_args()
    project_id = uuid.UUID(args.project_id)
    reference_id = uuid.UUID(args.reference_id)

    with SessionLocal() as db:
        svc = ResearchAIService(db)
        reference = db.scalar(
            select(ResearchReference).where(
                ResearchReference.project_id == project_id,
                ResearchReference.id == reference_id,
            )
        )
        if not reference:
            print("Reference not found.", file=sys.stderr)
            return 1

        document = None
        if reference.document_key:
            document = db.scalar(
                select(ProjectDocument).where(
                    ProjectDocument.project_id == project_id,
                    ProjectDocument.document_key == reference.document_key,
                )
            )

        print_json(
            "REFERENCE",
            {
                "id": str(reference.id),
                "title": reference.title,
                "authors": reference.authors or [],
                "year": reference.year,
                "document_key": str(reference.document_key) if reference.document_key else None,
                "has_abstract": bool(reference.abstract),
                "document_found": bool(document),
            },
        )

        if not document:
            if reference.abstract:
                print_json("ABSTRACT_FALLBACK_INPUT", {"abstract": reference.abstract})
                if args.run_llm:
                    final_payload = svc._summarize_abstract_only(reference)
                    print_json("FINAL_OUTPUT", final_payload)
                return 0
            print("No linked document and no abstract available.", file=sys.stderr)
            return 1

        queries = svc.build_summary_queries(
            {
                "title": reference.title,
                "authors": reference.authors or [],
                "abstract": reference.abstract,
                "metadata": document.metadata_json or {},
            }
        )
        print_json("SUMMARY_QUERIES", queries)

        selected_chunks = svc.retrieve_summary_chunks(document.id, queries, per_query_k=5)
        print_chunks("SELECTED_CHUNKS", selected_chunks)

        map_groups = svc._group_summary_chunks(selected_chunks)
        print_json(
            "MAP_INPUT_GROUPS",
            [
                [
                    {
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "role": chunk.role,
                        "content": chunk.content,
                    }
                    for chunk in group
                ]
                for group in map_groups
            ],
        )
        for index, group in enumerate(map_groups, start=1):
            chunk_payload = [
                {
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "role": chunk.role,
                    "content": chunk.content,
                }
                for chunk in group
            ]
            map_user_prompt = (
                "Extract grounded academic notes from these chunks.\n"
                "Focus on contribution, method, experimental setup, results, limitations, and conclusion when present.\n"
                "Chunks:\n"
                f"{json.dumps(chunk_payload, ensure_ascii=False)}"
            )
            print_llm_prompt(f"MAP {index}", MAP_SUMMARY_SYSTEM_PROMPT, map_user_prompt)

        if not args.run_llm:
            print("\nLLM steps skipped. Re-run with --run-llm to execute map/reduce/final synthesis.")
            return 0

        try:
            map_outputs = svc.summarize_chunk_map(selected_chunks)
            print_json("MAP_OUTPUTS", map_outputs)

            reduce_user_prompt = (
                "Consolidate these grounded academic notes into a structured evidence inventory.\n"
                f"Notes:\n{json.dumps(map_outputs, ensure_ascii=False)}"
            )
            print_llm_prompt("REDUCE", REDUCE_SUMMARY_SYSTEM_PROMPT, reduce_user_prompt)
            reduced = svc._chat_json(REDUCE_SUMMARY_SYSTEM_PROMPT, reduce_user_prompt)
            print_json("REDUCED_OUTPUT", reduced)

            final_user_prompt = (
                "Generate the final grounded academic-paper summary JSON.\n"
                f"Reduced evidence:\n{json.dumps(reduced, ensure_ascii=False)}"
            )
            print_llm_prompt("FINAL", FINAL_SYNTHESIS_SYSTEM_PROMPT, final_user_prompt)
            final_output = svc._chat_json(FINAL_SYNTHESIS_SYSTEM_PROMPT, final_user_prompt)
            print_json("FINAL_OUTPUT", final_output)
        except NotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Pipeline failed: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
