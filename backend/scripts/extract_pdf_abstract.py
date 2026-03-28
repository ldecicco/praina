#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.text_extraction import extract_pdf_abstract_details, extract_pdf_pages_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect heuristic PDF abstract extraction from the first pages.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--pages", type=int, default=2, help="Number of initial pages to inspect (default: 2)")
    parser.add_argument(
        "--show-source",
        action="store_true",
        help="Print the extracted source text from the inspected pages before the abstract payload",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    pdf_path = Path(args.pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    source_text = extract_pdf_pages_text(pdf_path, max_pages=args.pages)
    result = extract_pdf_abstract_details(pdf_path, max_pages=args.pages)

    if args.show_source:
        print("=== SOURCE TEXT ===")
        print(source_text)
        print()

    print(
        json.dumps(
            {
                "pdf_path": str(pdf_path),
                "pages_considered": max(1, args.pages),
                "source_text_length": len(source_text),
                "abstract_found": bool(result.abstract),
                "confidence": round(result.confidence, 3),
                "used_end_marker": result.used_end_marker,
                "stopped_on_intro_like_marker": result.stopped_on_intro_like_marker,
                "candidate_length": result.candidate_length,
                "abstract": result.abstract or None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
