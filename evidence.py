"""
Structured Evidence Table builder for pubmed-mcp (Phase 3).

Strict rules
------------
- Only extract what is explicitly present in the retrieved text.
- Every cell carries value + status + optional source quote.
- Never invent sample size, effect estimates, study design, or PICO elements.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Extraction statuses
STATUS_EXTRACTED = "extracted"
STATUS_NOT_REPORTED = "not_reported"      # text was available but the element is absent
STATUS_NOT_RETRIEVED = "not_retrieved"    # we never got the abstract / full text
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_PARSE_ERROR = "parse_error"


def _cell(value: Any, status: str, source_quote: Optional[str] = None) -> Dict[str, Any]:
    cell: Dict[str, Any] = {
        "value": value,
        "status": status,
    }
    if source_quote:
        cell["source_quote"] = source_quote
    return cell


def _get_plain(record: Dict[str, Any], key: str) -> Optional[str]:
    """Pull a plain string from either legacy or provenance-style record."""
    val = record.get(key)
    if val is None:
        return None
    if isinstance(val, dict):
        inner = val.get("value")
        if inner is None:
            return None
        if isinstance(inner, list):
            return "; ".join(str(x) for x in inner)
        return str(inner)
    if isinstance(val, list):
        return "; ".join(str(x) for x in val)
    return str(val)


def _has_abstract(record: Dict[str, Any]) -> bool:
    abs_ = _get_plain(record, "abstract")
    if not abs_:
        return False
    if abs_ == "Data not provided in PubMed abstract":
        return False
    return True


# Very conservative keyword helpers — only flag when language is clear.
# These are hints for the human reviewer, never authoritative labels.

_DESIGN_PATTERNS = [
    (re.compile(r"\brandomi[sz]ed\s+controlled\s+trial\b", re.I), "randomized controlled trial"),
    (re.compile(r"\bRCT\b"), "randomized controlled trial"),
    (re.compile(r"\bsystematic\s+review\b", re.I), "systematic review"),
    (re.compile(r"\bmeta-?analysis\b", re.I), "meta-analysis"),
    (re.compile(r"\bcohort\s+study\b", re.I), "cohort study"),
    (re.compile(r"\bcase-?control\b", re.I), "case-control study"),
    (re.compile(r"\bcross-?sectional\b", re.I), "cross-sectional study"),
    (re.compile(r"\bcase\s+report\b", re.I), "case report"),
    (re.compile(r"\bcase\s+series\b", re.I), "case series"),
]

_SAMPLE_SIZE_RE = re.compile(
    r"(?:n\s*=\s*|N\s*=\s*|sample\s+size\s+of\s+|enrolled\s+)(\d{1,6})\b",
    re.I,
)


def _hint_study_design(text: str) -> Dict[str, Any]:
    for pat, label in _DESIGN_PATTERNS:
        m = pat.search(text)
        if m:
            return _cell(label, STATUS_EXTRACTED, source_quote=m.group(0))
    return _cell(None, STATUS_NOT_REPORTED)


def _hint_sample_size(text: str) -> Dict[str, Any]:
    m = _SAMPLE_SIZE_RE.search(text)
    if m:
        try:
            n = int(m.group(1))
            return _cell(n, STATUS_EXTRACTED, source_quote=m.group(0))
        except ValueError:
            pass
    return _cell(None, STATUS_NOT_REPORTED)


def build_evidence_row(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build one evidence-table row from a single PubMed record.

    Only uses title + abstract + publication_types + retraction flag.
    No external inference.
    """
    pmid = _get_plain(record, "pmid") or ""
    title = _get_plain(record, "title") or ""
    abstract = _get_plain(record, "abstract") or ""
    has_abs = _has_abstract(record)

    # Combine title + abstract for simple pattern matching
    searchable = f"{title}\n{abstract}" if has_abs else title

    pub_types = record.get("publication_types")
    if isinstance(pub_types, dict):
        pub_types_val = pub_types.get("value") or []
        pub_types_status = pub_types.get("status", STATUS_EXTRACTED)
    else:
        pub_types_val = pub_types if isinstance(pub_types, list) else ([] if not pub_types else [str(pub_types)])
        pub_types_status = STATUS_EXTRACTED if pub_types_val else STATUS_NOT_REPORTED

    row: Dict[str, Any] = {
        "pmid": _cell(pmid, STATUS_EXTRACTED if pmid else STATUS_NOT_RETRIEVED),
        "title": _cell(title, STATUS_EXTRACTED if title else STATUS_NOT_RETRIEVED),
        "publication_types": _cell(pub_types_val, pub_types_status),
        "study_design_hint": _hint_study_design(searchable) if searchable else _cell(None, STATUS_NOT_RETRIEVED),
        # Sample size is reported in the abstract/methods, never in the title.
        # Without the abstract we cannot responsibly claim a value or even confirm absence.
        "sample_size": _hint_sample_size(abstract) if has_abs else _cell(None, STATUS_NOT_RETRIEVED),
        "has_retraction_notice": _cell(
            bool(record.get("has_retraction_notice", False)),
            STATUS_EXTRACTED,
        ),
        "abstract_available": _cell(has_abs, STATUS_EXTRACTED),
        # Placeholders that stay not_reported / not_retrieved until full-text support improves
        "population_hint": _cell(None, STATUS_NOT_REPORTED if has_abs else STATUS_NOT_RETRIEVED),
        "intervention_hint": _cell(None, STATUS_NOT_REPORTED if has_abs else STATUS_NOT_RETRIEVED),
        "comparator_hint": _cell(None, STATUS_NOT_REPORTED if has_abs else STATUS_NOT_RETRIEVED),
        "outcome_hint": _cell(None, STATUS_NOT_REPORTED if has_abs else STATUS_NOT_RETRIEVED),
        "extraction_notes": _cell(
            "Hints are conservative keyword matches from title/abstract only. Human review required."
            if has_abs else "Abstract not available; limited extraction possible.",
            STATUS_EXTRACTED,
        ),
    }
    return row


def build_evidence_table(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a complete evidence table from a list of records."""
    rows = [build_evidence_row(r) for r in records]
    return {
        "schema_version": "0.1",
        "row_count": len(rows),
        "rows": rows,
        "notes": [
            "All hints are derived only from title and abstract text.",
            "No values are invented. 'not_reported' means the element was not found in the available text.",
            "Human review is required before using any hint in a systematic review.",
        ],
    }


def evidence_table_to_csv(table: Dict[str, Any]) -> str:
    """Flatten the evidence table into a simple CSV for spreadsheet use."""
    import csv
    import io

    fieldnames = [
        "pmid", "title", "publication_types", "study_design_hint",
        "sample_size", "has_retraction_notice", "abstract_available",
        "population_hint", "intervention_hint", "comparator_hint", "outcome_hint",
        "extraction_notes",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in table.get("rows", []):
        flat = {}
        for col in fieldnames:
            cell = row.get(col, {})
            val = cell.get("value")
            status = cell.get("status", "")
            if val is None:
                flat[col] = f"[{status}]"
            elif isinstance(val, list):
                flat[col] = "; ".join(str(x) for x in val)
            else:
                flat[col] = str(val)
        writer.writerow(flat)
    return buf.getvalue()