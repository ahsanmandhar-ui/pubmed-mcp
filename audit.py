"""
Full-text / download audit trail helpers (Phase 2).

Extends the existing access.py path with explicit status, route and checksum.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional


# Allowed download / access statuses
STATUS_SUCCESS = "success"
STATUS_SKIPPED_PAYWALLED = "skipped_paywalled"
STATUS_FAILED = "failed"
STATUS_NOT_ATTEMPTED = "not_attempted"
STATUS_NO_OPEN_ACCESS = "no_open_access_found"
STATUS_LANDING_PAGE_ONLY = "open_access_landing_page_only"
STATUS_OPEN_ACCESS_PDF = "open_access_pdf"


def make_access_audit(
    pmid: str,
    *,
    access_status: str,
    route: Optional[str] = None,          # "pmc" | "unpaywall" | None
    download_status: str = STATUS_NOT_ATTEMPTED,
    file_path: Optional[str] = None,
    checksum_sha256: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a single-record access / download audit entry.

    Example
    -------
    {
      "pmid": "12345678",
      "access_status": "open_access_pdf",
      "route": "pmc",
      "download_status": "success",
      "file_path": "/home/user/pubmed_pdfs/12345678.pdf",
      "checksum_sha256": "abc...",
      "error": null
    }
    """
    entry: Dict[str, Any] = {
        "pmid": pmid,
        "access_status": access_status,
        "route": route,
        "download_status": download_status,
        "file_path": file_path,
        "checksum_sha256": checksum_sha256,
        "error": error,
    }
    return entry


def sha256_file(path: str) -> str:
    """Compute SHA-256 of a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize_audit(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Produce a short summary of an audit list."""
    counts: Dict[str, int] = {}
    for e in entries:
        st = e.get("download_status") or e.get("access_status") or "unknown"
        counts[st] = counts.get(st, 0) + 1
    return {
        "total": len(entries),
        "by_status": counts,
        "entries": entries,
    }