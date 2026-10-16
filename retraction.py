"""
Retraction / correction monitoring helpers (Phase 4).

Builds on the existing has_retraction_notice / has_erratum_notice flags
and adds an explicit “last checked” audit trail so a reviewer can
distinguish “verified clean” from “not yet re-checked”.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional


def make_retraction_check_result(
    pmid: str,
    *,
    has_retraction_notice: bool,
    has_erratum_notice: bool = False,
    comments_corrections: Optional[List[Dict[str, Any]]] = None,
    checked_at: Optional[str] = None,
    source: str = "NCBI PubMed",
) -> Dict[str, Any]:
    return {
        "pmid": pmid,
        "has_retraction_notice": has_retraction_notice,
        "has_erratum_notice": has_erratum_notice,
        "comments_corrections": comments_corrections or [],
        "checked_at": checked_at or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": source,
        "status": (
            "retraction_found" if has_retraction_notice
            else "erratum_found" if has_erratum_notice
            else "no_notice_found"
        ),
    }


def summarize_retraction_checks(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"retraction_found": 0, "erratum_found": 0, "no_notice_found": 0}
    for r in results:
        st = r.get("status", "no_notice_found")
        counts[st] = counts.get(st, 0) + 1
    return {
        "total_checked": len(results),
        "by_status": counts,
        "results": results,
    }