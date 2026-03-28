"""Shared text extraction and chunking utilities.

Extracted from DocumentIngestionService so they can be reused by
MeetingIngestionService and any future ingestion pipelines.
"""

import zipfile
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

ABSTRACT_START_RE = re.compile(
    r"(?is)\babstract\b\s*(?:[:.\-]|\u2014|\u2013)?\s*"
)
ABSTRACT_END_PATTERNS = (
    re.compile(r"(?im)^\s*(keywords?|index terms?)\s*[:.\-]"),
    re.compile(r"(?im)^\s*ccs concepts?\s*[:.\-]"),
    re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*)\s+(introduction|background|related work|method|methods|methodology)\b"),
    re.compile(r"(?im)^\s*(?:[ivx]+)\.?\s+(introduction|background|related work|method|methods|methodology)\b"),
    re.compile(r"(?im)^\s*(introduction|background|related work|method|methods|methodology)\s*$"),
)
ABSTRACT_INLINE_END_PATTERNS = (
    re.compile(r"(?i)\b(?:keywords?|index terms?|ccs concepts?)\b\s*[:.\-]"),
    re.compile(r"(?i)(?:^|\s)(?:\d+(?:\.\d+)?|[ivx]+)\.?\s+introduction\b"),
)
HEADING_BLOCK_RE = re.compile(
    r"(?i)^(?:\d+(?:\.\d+)?|[ivx]+)\.?\s+(?:introduction|background|related work|method|methods|methodology|results|discussion|conclusion)\b|^(?:introduction|background|related work|method|methods|methodology|results|discussion|conclusion)$"
)
ABSTRACT_HEADING_ONLY_RE = re.compile(r"(?i)^\s*abstract\s*(?:[:.\-]|\u2014|\u2013)?\s*$")
ABSTRACT_INLINE_RE = re.compile(r"(?i)^\s*abstract\s*(?:[:.\-]|\u2014|\u2013)\s*(.+)$")
GENERIC_SECTION_RE = re.compile(
    r"(?i)^(?:\d+(?:\.\d+)?|[ivx]+)\.?\s+.+$|^(?:introduction|background|related work|method|methods|methodology|results|discussion|conclusion|keywords?|index terms?|ccs concepts?)\b.*$"
)


@dataclass
class PdfAbstractExtractionResult:
    abstract: str
    confidence: float
    source_text: str
    used_end_marker: bool
    stopped_on_intro_like_marker: bool
    candidate_length: int


def extract_text(file_path: Path, mime_type: str) -> str:
    """Extract plain text from a file based on its MIME type or extension."""
    if not file_path.exists():
        raise FileNotFoundError("Document file not found in storage.")
    raw = file_path.read_bytes()
    if not raw:
        return ""

    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or file_path.suffix.lower() == ".docx":
        return extract_docx_text(file_path)
    if mime_type == "application/pdf" or file_path.suffix.lower() == ".pdf":
        return extract_pdf_text(file_path)

    text_like = mime_type.startswith("text/") or file_path.suffix.lower() in {
        ".txt",
        ".md",
        ".json",
        ".csv",
        ".xml",
        ".yaml",
        ".yml",
        ".html",
        ".log",
    }
    if text_like:
        return raw.decode("utf-8", errors="ignore").strip()

    if b"\x00" in raw:
        return ""
    return raw.decode("utf-8", errors="ignore").strip()


def extract_docx_text(file_path: Path) -> str:
    """Extract text from a .docx file."""
    try:
        with zipfile.ZipFile(file_path) as archive:
            xml_bytes = archive.read("word/document.xml")
    except KeyError:
        return ""
    except zipfile.BadZipFile:
        return ""

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines: list[str] = []
    for paragraph in root.findall(".//w:p", ns):
        parts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def extract_pdf_text(file_path: Path) -> str:
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(str(file_path))
    except Exception:
        return ""

    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            pages.append(text)
    return "\n".join(pages).strip()


def extract_pdf_pages_text(file_path: Path, max_pages: int = 1) -> str:
    """Extract text from the first ``max_pages`` pages of a PDF."""
    try:
        reader = PdfReader(str(file_path))
    except Exception:
        return ""

    pages: list[str] = []
    for page in reader.pages[: max(1, max_pages)]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            pages.append(text)
    return "\n\n".join(pages).strip()


def extract_pdf_abstract(file_path: Path, max_pages: int = 2) -> str:
    """Extract a likely abstract from the first pages of a PDF using layout-aware heuristics."""
    return extract_pdf_abstract_details(file_path, max_pages=max_pages).abstract


def extract_pdf_abstract_details(file_path: Path, max_pages: int = 2) -> PdfAbstractExtractionResult:
    """Return the extracted abstract plus confidence and boundary diagnostics."""
    text = extract_pdf_pages_text(file_path, max_pages=max_pages)
    if not text:
        return PdfAbstractExtractionResult("", 0.0, "", False, False, 0)

    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"(?<=\w)-\n(?=\w)", "", cleaned)
    cleaned = cleaned.strip()

    raw_lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    abstract_line_index: int | None = None
    inline_abstract_start = ""
    for index, line in enumerate(raw_lines[:80]):
        inline_match = ABSTRACT_INLINE_RE.match(line)
        if inline_match:
            abstract_line_index = index
            inline_abstract_start = inline_match.group(1).strip()
            break
        if ABSTRACT_HEADING_ONLY_RE.match(line):
            abstract_line_index = index
            break

    if abstract_line_index is None:
        return PdfAbstractExtractionResult("", 0.0, cleaned, False, False, 0)

    candidate_lines: list[str] = []
    if inline_abstract_start:
        candidate_lines.append(inline_abstract_start)

    for line in raw_lines[abstract_line_index + 1 :]:
        normalized = " ".join(line.split())
        if not normalized:
            if candidate_lines:
                break
            continue
        if ABSTRACT_HEADING_ONLY_RE.match(normalized):
            continue
        if any(pattern.match(normalized) for pattern in ABSTRACT_END_PATTERNS):
            break
        if any(pattern.search(normalized) and pattern.search(normalized).start() == 0 for pattern in ABSTRACT_INLINE_END_PATTERNS):
            break
        if candidate_lines and GENERIC_SECTION_RE.match(normalized):
            break
        candidate_lines.append(normalized)
        if sum(len(item.split()) for item in candidate_lines) >= 260:
            break
        if sum(len(item) for item in candidate_lines) >= 2200:
            break

    if not candidate_lines:
        return PdfAbstractExtractionResult("", 0.0, cleaned, False, False, 0)

    candidate = " ".join(candidate_lines).strip()
    used_end_marker = False
    stopped_on_intro_like_marker = False
    end_positions = [match.start() for pattern in ABSTRACT_END_PATTERNS for match in [pattern.search(candidate)] if match]
    if end_positions:
        candidate = candidate[: min(end_positions)].strip()
        used_end_marker = True

    inline_positions = [
        match.start()
        for pattern in ABSTRACT_INLINE_END_PATTERNS
        for match in [pattern.search(candidate)]
        if match and match.start() > 120
    ]
    if inline_positions:
        candidate = candidate[: min(inline_positions)].strip()
        used_end_marker = True
        stopped_on_intro_like_marker = True

    candidate = re.sub(r"\s+", " ", candidate).strip(" -:\n\t")
    word_count = len(candidate.split())
    if word_count > 260:
        candidate = " ".join(candidate.split()[:260]).strip()
        stopped_on_intro_like_marker = True
    if len(candidate) > 2200:
        candidate = candidate[:2200].rsplit(" ", 1)[0].strip()
        stopped_on_intro_like_marker = True

    if len(candidate) < 80 or word_count < 25:
        return PdfAbstractExtractionResult("", 0.12, cleaned, used_end_marker, stopped_on_intro_like_marker, len(candidate))

    confidence = 0.58
    if inline_abstract_start or abstract_line_index is not None:
        confidence += 0.12
    if used_end_marker:
        confidence += 0.18
    if 80 <= len(candidate) <= 1800 and 25 <= word_count <= 220:
        confidence += 0.14
    if stopped_on_intro_like_marker or re.search(r"(?i)\bintroduction\b", candidate[:120]):
        confidence -= 0.12
    if re.search(r"(?i)\bintroduction\b", candidate[-220:]):
        confidence -= 0.18
    confidence = max(0.0, min(confidence, 0.98))

    return PdfAbstractExtractionResult(
        abstract=candidate,
        confidence=confidence,
        source_text=cleaned,
        used_end_marker=used_end_marker,
        stopped_on_intro_like_marker=stopped_on_intro_like_marker,
        candidate_length=len(candidate),
    )


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks for indexing."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + CHUNK_SIZE, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks
