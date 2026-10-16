"""
Citation chasing helpers for pubmed-mcp (Phase 4).

Europe PMC provides reference lists and citing articles for many records.
This module only surfaces what the source actually returns and records
coverage notes. It never invents citations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def make_citation_result(
    source_pmid: str,
    *,
    references: Optional[List[Dict[str, Any]]] = None,
    citing_articles: Optional[List[Dict[str, Any]]] = None,
    references_available: bool = False,
    citing_available: bool = False,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Standard shape for a citation-chase result.
    """
    return {
        "source_pmid": source_pmid,
        "references_available": references_available,
        "citing_articles_available": citing_available,
        "reference_count": len(references or []),
        "citing_count": len(citing_articles or []),
        "references": references or [],
        "citing_articles": citing_articles or [],
        "notes": notes or (
            "Citation data is only included when the upstream source supplies it. "
            "Absence of data does not mean the paper has no references."
        ),
    }


# Placeholder for the actual Europe PMC reference / citation endpoints.
# Real implementation will call:
#   GET /MED/{pmid}/references
#   GET /MED/{pmid}/citations
# and normalize each hit with the same provenance schema.