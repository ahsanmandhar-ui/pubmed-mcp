"""
Europe PMC client stub for pubmed-mcp (Phase 4).

Design rules
------------
- Map every record into the same provenance-aware schema used for PubMed.
- Never invent fields.
- Preserve original source and all available identifiers.
- Rate-limit politely; Europe PMC asks for an email in the User-Agent.
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Dict, List, Optional

import requests

# Europe PMC REST base
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 1000


class EuropePmcError(Exception):
    pass


class EuropePmcClient:
    """Minimal, rate-aware Europe PMC client."""

    def __init__(self, email: Optional[str] = None, timeout: float = 30.0):
        self.email = email or "pubmed-access-mcp"
        self.timeout = timeout
        self._last_call = 0.0
        self._min_interval = 0.2  # be polite

    def _throttle(self) -> None:
        wait = self._last_call + self._min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def search(
        self,
        query: str,
        page_size: int = DEFAULT_PAGE_SIZE,
        cursor_mark: str = "*",
    ) -> Dict[str, Any]:
        """
        Run a Europe PMC search.
        Returns the raw JSON payload (caller normalizes).
        """
        self._throttle()
        params = {
            "query": query,
            "format": "json",
            "pageSize": min(max(page_size, 1), MAX_PAGE_SIZE),
            "cursorMark": cursor_mark,
            "resultType": "core",
        }
        headers = {"User-Agent": f"pubmed-access-mcp/0.4 ({self.email})"}
        resp = requests.get(f"{EPMC_BASE}/search", params=params, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise EuropePmcError(f"Europe PMC search failed: HTTP {resp.status_code}")
        return resp.json()

    def get_by_id(self, ext_id: str, source: str = "MED") -> Dict[str, Any]:
        """
        Fetch a single record by external ID (usually PMID with source=MED).
        """
        self._throttle()
        headers = {"User-Agent": f"pubmed-access-mcp/0.4 ({self.email})"}
        url = f"{EPMC_BASE}/{source}/{ext_id}/json"
        resp = requests.get(url, headers=headers, timeout=self.timeout)
        if resp.status_code != 200:
            raise EuropePmcError(f"Europe PMC get failed: HTTP {resp.status_code}")
        return resp.json()


def normalize_epmc_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map a Europe PMC core result into a provenance-friendly shape.

    This is deliberately conservative: only fields that are clearly present
    are marked extracted; everything else is not_returned.
    """
    # Import here to avoid circular issues if provenance moves
    try:
        from provenance import field, STATUS_DIRECTLY_SOURCED, STATUS_NOT_RETURNED, make_record_provenance
    except ImportError:
        # fallback minimal shape
        def field(v, s, **kw):
            return {"value": v, "status": s}
        STATUS_DIRECTLY_SOURCED = "directly_sourced"
        STATUS_NOT_RETURNED = "not_returned_by_ncbi"
        def make_record_provenance(**kw):
            return kw

    pmid = raw.get("pmid") or raw.get("id")
    title = raw.get("title")
    abstract = raw.get("abstractText")
    doi = raw.get("doi")
    pmcid = raw.get("pmcid")
    journal = (raw.get("journalInfo") or {}).get("journal", {}).get("title") if isinstance(raw.get("journalInfo"), dict) else None
    authors = []
    for a in raw.get("authorList", {}).get("author", []) or []:
        full = a.get("fullName") or f"{a.get('lastName', '')} {a.get('firstName', '')}".strip()
        if full:
            authors.append(full)

    pub_year = raw.get("pubYear")

    record = {
        "pmid": field(pmid, STATUS_DIRECTLY_SOURCED if pmid else STATUS_NOT_RETURNED),
        "title": field(title, STATUS_DIRECTLY_SOURCED if title else STATUS_NOT_RETURNED),
        "authors": field(authors, STATUS_DIRECTLY_SOURCED if authors else STATUS_NOT_RETURNED),
        "journal": field(journal, STATUS_DIRECTLY_SOURCED if journal else STATUS_NOT_RETURNED),
        "pub_date": field(str(pub_year) if pub_year else None, STATUS_DIRECTLY_SOURCED if pub_year else STATUS_NOT_RETURNED),
        "doi": field(doi, STATUS_DIRECTLY_SOURCED if doi else STATUS_NOT_RETURNED),
        "pmcid": field(pmcid, STATUS_DIRECTLY_SOURCED if pmcid else STATUS_NOT_RETURNED),
        "abstract": field(abstract, STATUS_DIRECTLY_SOURCED if abstract else STATUS_NOT_RETURNED),
        "source": "Europe PMC",
        "europepmc_id": raw.get("id"),
        "provenance": make_record_provenance(
            utility="europepmc_search",
            pmid=str(pmid) if pmid else None,
        ),
    }
    return record