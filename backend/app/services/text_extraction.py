"""Shared text extraction and chunking utilities.

Extracted from DocumentIngestionService so they can be reused by
MeetingIngestionService and any future ingestion pipelines.
"""

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


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
