"""Minimal BibTeX parser — no external dependencies.

Handles standard .bib entries: @article, @inproceedings, @book, @misc, etc.
Extracts title, author, year, journal/booktitle, doi, url, abstract.
"""

from __future__ import annotations

import re


def parse_bibtex(raw: str) -> list[dict]:
    """Parse a BibTeX string and return a list of reference dicts.

    Each dict has keys: title, authors (list[str]), year (int|None),
    venue (str|None), doi (str|None), url (str|None), abstract (str|None),
    entry_type (str), cite_key (str).
    """
    entries: list[dict] = []
    # Match each @type{key, ... } block (handles nested braces)
    for m in re.finditer(r"@(\w+)\s*\{([^,]*),", raw):
        entry_type = m.group(1).lower()
        cite_key = m.group(2).strip()
        start = m.end()
        body = _extract_braced_body(raw, start)
        if body is None:
            continue
        fields = _parse_fields(body)
        entries.append(_fields_to_ref(entry_type, cite_key, fields))
    return entries


def _extract_braced_body(raw: str, start: int) -> str | None:
    """Extract content from ``start`` to the matching closing ``}`` of the entry."""
    depth = 1
    i = start
    while i < len(raw) and depth > 0:
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return raw[start : i - 1]


def _parse_fields(body: str) -> dict[str, str]:
    """Parse ``key = {value}`` or ``key = "value"`` or ``key = number`` pairs."""
    fields: dict[str, str] = {}
    # Regex for key = ...
    pos = 0
    while pos < len(body):
        # Find next key
        km = re.search(r"(\w[\w-]*)\s*=\s*", body[pos:])
        if km is None:
            break
        key = km.group(1).lower()
        val_start = pos + km.end()
        value, end = _parse_value(body, val_start)
        fields[key] = value
        pos = end
    return fields


def _parse_value(body: str, start: int) -> tuple[str, int]:
    """Parse a BibTeX field value starting at ``start``. Returns (value, end_pos)."""
    # Skip whitespace
    i = start
    while i < len(body) and body[i] in " \t\n\r":
        i += 1
    if i >= len(body):
        return ("", i)

    ch = body[i]
    if ch == "{":
        # Braced value
        depth = 1
        i += 1
        val_start = i
        while i < len(body) and depth > 0:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
            i += 1
        value = body[val_start : i - 1]
    elif ch == '"':
        # Quoted value
        i += 1
        val_start = i
        while i < len(body) and body[i] != '"':
            i += 1
        value = body[val_start:i]
        i += 1  # skip closing quote
    else:
        # Bare number or macro
        val_start = i
        while i < len(body) and body[i] not in ",}\n":
            i += 1
        value = body[val_start:i].strip()

    # Skip trailing comma/whitespace
    while i < len(body) and body[i] in " \t\n\r,":
        i += 1
    return (value, i)


def _parse_authors(raw_author: str) -> list[str]:
    """Split BibTeX ``author`` field by `` and `` and normalise names."""
    parts = re.split(r"\s+and\s+", raw_author, flags=re.IGNORECASE)
    authors: list[str] = []
    for p in parts:
        name = re.sub(r"\s+", " ", p.strip().strip("{}"))
        if not name:
            continue
        # Convert "Last, First" → "First Last"
        if "," in name:
            segments = name.split(",", 1)
            name = f"{segments[1].strip()} {segments[0].strip()}"
        authors.append(name)
    return authors


def _fields_to_ref(entry_type: str, cite_key: str, fields: dict[str, str]) -> dict:
    """Convert parsed fields into a normalised reference dict."""
    title = _clean(fields.get("title", ""))
    authors = _parse_authors(fields.get("author", ""))
    year_str = fields.get("year", "")
    year = int(year_str) if year_str.isdigit() else None
    venue = _clean(
        fields.get("journal", "")
        or fields.get("booktitle", "")
        or fields.get("publisher", "")
    )
    doi = _clean(fields.get("doi", ""))
    url = _clean(fields.get("url", ""))
    abstract = _clean(fields.get("abstract", ""))

    return {
        "title": title or cite_key,
        "authors": authors,
        "year": year,
        "venue": venue or None,
        "doi": doi or None,
        "url": url or None,
        "abstract": abstract or None,
        "entry_type": entry_type,
        "cite_key": cite_key,
    }


def _clean(val: str) -> str:
    """Remove surrounding braces and collapse whitespace."""
    val = val.strip().strip("{}")
    return re.sub(r"\s+", " ", val).strip()
