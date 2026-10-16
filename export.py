"""
Bibliographic exporters for pubmed-mcp (Phase 2).

Rules
-----
- Never invent values.
- Missing fields are omitted or marked explicitly according to the target format.
- All exporters accept either a list of record dicts or will be called after a fetch.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional


def _get(record: Dict[str, Any], key: str, default: str = "") -> str:
    """Safely extract a plain string from either legacy or provenance-style records."""
    val = record.get(key)
    if val is None:
        return default
    if isinstance(val, dict):
        # provenance field shape: {"value": ..., "status": ...}
        inner = val.get("value")
        if inner is None:
            return default
        if isinstance(inner, list):
            return "; ".join(str(x) for x in inner)
        return str(inner)
    if isinstance(val, list):
        return "; ".join(str(x) for x in val)
    return str(val)


def _authors_list(record: Dict[str, Any]) -> List[str]:
    val = record.get("authors")
    if val is None:
        return []
    if isinstance(val, dict):
        inner = val.get("value") or []
        return list(inner) if isinstance(inner, list) else [str(inner)]
    if isinstance(val, list):
        return [str(a) for a in val]
    return [str(val)]


# ---------------------------------------------------------------------------
# RIS
# ---------------------------------------------------------------------------

def to_ris(records: List[Dict[str, Any]]) -> str:
    """
    Export records to RIS format (EndNote / Zotero / Covidence compatible).

    TY  - JOUR
    PMID- 12345678
    TI  - Title
    AU  - Author1
    AU  - Author2
    JO  - Journal
    PY  - 2024
    DO  - 10.xxxx
    AB  - Abstract
    UR  - https://pubmed.ncbi.nlm.nih.gov/12345678/
    ER  -
    """
    lines: List[str] = []
    for rec in records:
        lines.append("TY  - JOUR")
        pmid = _get(rec, "pmid")
        if pmid:
            lines.append(f"PMID- {pmid}")
        title = _get(rec, "title")
        if title:
            lines.append(f"TI  - {title}")
        for au in _authors_list(rec):
            lines.append(f"AU  - {au}")
        journal = _get(rec, "journal")
        if journal:
            lines.append(f"JO  - {journal}")
        pub_date = _get(rec, "pub_date")
        if pub_date:
            # best-effort year extraction
            year = pub_date.split()[0] if pub_date else ""
            if year.isdigit():
                lines.append(f"PY  - {year}")
            lines.append(f"DA  - {pub_date}")
        doi = _get(rec, "doi")
        if doi and doi != "Data not provided in PubMed abstract":
            lines.append(f"DO  - {doi}")
        abstract = _get(rec, "abstract")
        if abstract and abstract != "Data not provided in PubMed abstract":
            lines.append(f"AB  - {abstract}")
        url = _get(rec, "url")
        if url:
            lines.append(f"UR  - {url}")
        lines.append("ER  - ")
        lines.append("")  # blank line between records
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

def _bibtex_key(record: Dict[str, Any]) -> str:
    pmid = _get(record, "pmid") or "unknown"
    authors = _authors_list(record)
    first = "anon"
    if authors:
        first = authors[0].split()[-1].lower()
        first = "".join(c for c in first if c.isalnum())
    year = ""
    pub_date = _get(record, "pub_date")
    if pub_date:
        year = pub_date.split()[0]
    return f"{first}{year}_{pmid}"


def to_bibtex(records: List[Dict[str, Any]]) -> str:
    """Export records to BibTeX (@article)."""
    blocks: List[str] = []
    for rec in records:
        key = _bibtex_key(rec)
        lines = [f"@article{{{key},"]
        title = _get(rec, "title")
        if title:
            lines.append(f"  title = {{{title}}},")
        authors = _authors_list(rec)
        if authors:
            lines.append(f"  author = {{{' and '.join(authors)}}},")
        journal = _get(rec, "journal")
        if journal:
            lines.append(f"  journal = {{{journal}}},")
        pub_date = _get(rec, "pub_date")
        if pub_date:
            year = pub_date.split()[0]
            if year.isdigit():
                lines.append(f"  year = {{{year}}},")
        doi = _get(rec, "doi")
        if doi and "Data not provided" not in doi:
            lines.append(f"  doi = {{{doi}}},")
        pmid = _get(rec, "pmid")
        if pmid:
            lines.append(f"  pmid = {{{pmid}}},")
        abstract = _get(rec, "abstract")
        if abstract and "Data not provided" not in abstract:
            # escape braces lightly
            safe = abstract.replace("{", "\\{").replace("}", "\\}")
            lines.append(f"  abstract = {{{safe}}},")
        url = _get(rec, "url")
        if url:
            lines.append(f"  url = {{{url}}},")
        lines.append("}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "pmid", "title", "authors", "journal", "pub_date",
    "doi", "pmcid", "publication_types", "has_retraction_notice",
    "abstract", "url",
]


def to_csv(records: List[Dict[str, Any]]) -> str:
    """Export records to CSV (UTF-8). Missing fields become empty cells."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for rec in records:
        row = {
            "pmid": _get(rec, "pmid"),
            "title": _get(rec, "title"),
            "authors": "; ".join(_authors_list(rec)),
            "journal": _get(rec, "journal"),
            "pub_date": _get(rec, "pub_date"),
            "doi": _get(rec, "doi"),
            "pmcid": _get(rec, "pmcid"),
            "publication_types": _get(rec, "publication_types"),
            "has_retraction_notice": str(rec.get("has_retraction_notice", False)),
            "abstract": _get(rec, "abstract"),
            "url": _get(rec, "url"),
        }
        # clean sentinel strings to empty for CSV convenience
        for k, v in row.items():
            if v == "Data not provided in PubMed abstract":
                row[k] = ""
        writer.writerow(row)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def to_json(records: List[Dict[str, Any]], *, pretty: bool = True) -> str:
    """Export records as JSON. Preserves full provenance structure if present."""
    if pretty:
        return json.dumps(records, indent=2, ensure_ascii=False)
    return json.dumps(records, ensure_ascii=False)