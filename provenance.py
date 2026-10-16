"""
Evidence Provenance Ledger for pubmed-mcp.

Design rules
------------
- Never invent values.
- Every field that reaches the caller must declare its status.
- Secrets (API keys, tokens) are never stored in provenance objects.
"""

from __future__ import annotations

import datetime
import hashlib
from typing import Any, Dict, List, Optional, Union

# Allowed status values — keep this set small and explicit
STATUS_DIRECTLY_SOURCED = "directly_sourced"
STATUS_TRANSFORMED = "transformed"          # e.g. whitespace normalized, section labels preserved
STATUS_UNAVAILABLE = "unavailable"          # field present but empty / blank in source
STATUS_NOT_RETURNED = "not_returned_by_ncbi"
STATUS_PARSE_ERROR = "parse_error"
STATUS_NOT_APPLICABLE = "not_applicable"

ALLOWED_STATUSES = {
    STATUS_DIRECTLY_SOURCED,
    STATUS_TRANSFORMED,
    STATUS_UNAVAILABLE,
    STATUS_NOT_RETURNED,
    STATUS_PARSE_ERROR,
    STATUS_NOT_APPLICABLE,
}

SERVER_VERSION = "0.3.1"
SCHEMA_VERSION = "1.1"        # provenance ledger schema


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def field(
    value: Any,
    status: str,
    *,
    source: str = "NCBI PubMed",
    pmid: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a single field entry for the provenance ledger.

    Example
    -------
    {
      "value": "Some title",
      "status": "directly_sourced",
      "source": "NCBI PubMed",
      "pmid": "12345678",
      "retrieved_at": "2026-10-17T00:00:00+00:00"
    }
    """
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status {status!r}; must be one of {sorted(ALLOWED_STATUSES)}")

    entry: Dict[str, Any] = {
        "value": value,
        "status": status,
        "source": source,
        "retrieved_at": utc_now(),
    }
    if pmid is not None:
        entry["pmid"] = pmid
    if note:
        entry["note"] = note
    return entry


def make_record_provenance(
    *,
    utility: str,
    pmid: Optional[str] = None,
    request_params: Optional[Dict[str, Any]] = None,
    response_hash: Optional[str] = None,
    parser_version: str = SCHEMA_VERSION,
) -> Dict[str, Any]:
    """Top-level provenance block attached to a whole record or search result."""
    prov: Dict[str, Any] = {
        "provider": "NCBI PubMed",
        "database": "pubmed",
        "utility": utility,
        "timestamp": utc_now(),
        "server_version": SERVER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "parser_version": parser_version,
    }
    if pmid:
        prov["pmid"] = pmid
    if request_params is not None:
        # caller must already have sanitized secrets
        prov["request_parameters"] = request_params
    if response_hash:
        prov["response_hash"] = {
            "algorithm": "sha256",
            "value": response_hash,
        }
    return prov


def sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Remove any secret-looking keys before storing in provenance."""
    blocked = {"api_key", "apikey", "password", "token", "secret", "authorization"}
    return {k: v for k, v in params.items() if k.lower() not in blocked}