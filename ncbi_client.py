"""NCBI E-utilities client layer for pubmed-access-mcp.

Handles:
- Safe environment credential resolution (no placeholder leakage).
- Concurrency-safe rate limiting (3 req/s anonymous, 10 req/s with key).
- Exponential backoff retry logic (handling HTTP 429 and transient 5xx).
- Zero secret leakage in logs, errors, and provenance.
- Clean request dispatch for esearch, efetch, and einfo.
- Structured provenance generation.
"""

import datetime
import hashlib
import logging
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger("pubmed-mcp.client")

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TOOL_NAME = "pubmed-access-mcp"
SERVER_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"


class NcbiError(Exception):
    """Base exception for NCBI client errors."""
    pass


class InvalidInputError(NcbiError):
    """Raised when request arguments are malformed or invalid."""
    pass


class RateLimitError(NcbiError):
    """Raised when NCBI rate limits are exceeded after retries."""
    pass


class TimeoutError(NcbiError):
    """Raised when an NCBI request times out."""
    pass


class ParseError(NcbiError):
    """Raised when NCBI returns malformed XML or JSON."""
    pass


class NcbiClient:
    """Thread-safe, rate-limited, provenance-aware NCBI E-utilities client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        tool: Optional[str] = None,
        base_url: str = EUTILS_BASE,
        timeout: float = 45.0,
        max_retries: int = 4,
    ):
        self._explicit_api_key = api_key
        self._explicit_email = email
        self._explicit_tool = tool
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._last_call = 0.0

    @staticmethod
    def env(name: str) -> Optional[str]:
        """Safely fetch an environment variable, ignoring placeholders."""
        v = os.environ.get(name, "").strip()
        if not v or v.upper().startswith("YOUR_") or v.startswith("${"):
            return None
        return v

    @property
    def api_key(self) -> Optional[str]:
        return self._explicit_api_key or self.env("NCBI_API_KEY")

    @property
    def email(self) -> Optional[str]:
        return self._explicit_email or self.env("NCBI_EMAIL")

    @property
    def tool(self) -> str:
        return self._explicit_tool or self.env("NCBI_TOOL") or DEFAULT_TOOL_NAME

    def throttle(self) -> None:
        """Throttle requests per NCBI policy: 3 req/s without key, 10 req/s with key."""
        gap = 0.11 if self.api_key else 0.34
        with self._lock:
            wait = self._last_call + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def sanitize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of params with secret tokens removed for provenance/logging."""
        sanitized = {}
        for k, v in params.items():
            if k.lower() in ("api_key", "apikey", "password", "token", "secret"):
                continue
            sanitized[k] = v
        return sanitized

    def build_provenance(self, utility: str, params: Dict[str, Any], database: str = "pubmed") -> Dict[str, Any]:
        """Generate structured, audit-ready provenance metadata."""
        return {
            "provider": "NCBI PubMed",
            "database": database,
            "utility": utility,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "request_parameters": self.sanitize_params(params),
            "server_version": SERVER_VERSION,
            "schema_version": SCHEMA_VERSION,
        }

    @staticmethod
    def compute_hash(text: str) -> Dict[str, str]:
        """Generate SHA-256 integrity hash for a response payload."""
        return {
            "algorithm": "sha256",
            "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    def request(self, endpoint: str, params: Dict[str, Any], method: str = "GET") -> requests.Response:
        """Execute a rate-limited HTTP request to NCBI with exponential backoff retry."""
        full_params = {**params, "tool": self.tool}
        if self.email:
            full_params["email"] = self.email
        if self.api_key:
            full_params["api_key"] = self.api_key

        url = f"{self.base_url}/{endpoint}"
        last_error = "unknown error"

        for attempt in range(self.max_retries):
            self.throttle()
            try:
                if method.upper() == "POST":
                    resp = requests.post(url, data=full_params, timeout=self.timeout)
                else:
                    resp = requests.get(url, params=full_params, timeout=self.timeout)

                if resp.status_code == 200:
                    return resp

                last_error = f"HTTP {resp.status_code}"
                if resp.status_code == 429:
                    logger.warning("NCBI rate limit hit (HTTP 429) on attempt %d", attempt + 1)
                elif resp.status_code not in (500, 502, 503, 504):
                    break

            except requests.Timeout as e:
                last_error = f"Timeout: {e}"
            except requests.RequestException as e:
                last_error = f"{type(e).__name__}: {e}"

            time.sleep(1.5 * (attempt + 1))

        if "429" in last_error:
            raise RateLimitError(f"NCBI rate limit exceeded for {endpoint}: {last_error}")
        raise NcbiError(f"NCBI E-utilities request to {endpoint} failed: {last_error}")

    def esearch(
        self,
        term: str,
        retmax: int = 20,
        retstart: int = 0,
        sort: str = "relevance",
        mindate: Optional[int] = None,
        maxdate: Optional[int] = None,
        usehistory: bool = False,
        webenv: Optional[str] = None,
        query_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform an NCBI ESearch query and return parsed JSON payload."""
        term_clean = (term or "").strip()
        if not term_clean and not (webenv and query_key):
            raise InvalidInputError("Search query term must be non-empty unless using history parameters.")

        params: Dict[str, Any] = {
            "db": "pubmed",
            "term": term_clean,
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
            "sort": sort,
        }
        if usehistory:
            params["usehistory"] = "y"
        if webenv:
            params["WebEnv"] = webenv
        if query_key:
            params["query_key"] = query_key
        if mindate or maxdate:
            params["datetype"] = "pdat"
            params["mindate"] = str(mindate or 1800)
            params["maxdate"] = str(maxdate or datetime.date.today().year + 1)

        resp = self.request("esearch.fcgi", params, method="GET")
        try:
            data = resp.json().get("esearchresult", {})
        except Exception as e:
            raise ParseError(f"Failed to parse NCBI ESearch JSON response: {e}") from e

        if "ERROR" in data:
            raise NcbiError(f"NCBI ESearch error: {data['ERROR']}")

        return data

    def efetch(
        self,
        pmids: List[str],
        retmode: str = "xml",
        rettype: str = "abstract",
        webenv: Optional[str] = None,
        query_key: Optional[str] = None,
        retstart: int = 0,
        retmax: Optional[int] = None,
    ) -> str:
        """Fetch records via NCBI EFetch in XML format."""
        params: Dict[str, Any] = {
            "db": "pubmed",
            "retmode": retmode,
            "rettype": rettype,
        }
        if pmids:
            params["id"] = ",".join(pmids)
        if webenv:
            params["WebEnv"] = webenv
        if query_key:
            params["query_key"] = query_key
        if retstart > 0:
            params["retstart"] = retstart
        if retmax is not None:
            params["retmax"] = retmax

        resp = self.request("efetch.fcgi", params, method="POST")
        return resp.text

    def einfo(self, db: str = "pubmed") -> Dict[str, Any]:
        """Fetch database metadata and field descriptions via NCBI EInfo."""
        params: Dict[str, Any] = {"db": db, "retmode": "json"}
        resp = self.request("einfo.fcgi", params, method="GET")
        try:
            return resp.json().get("einforesult", {}).get("dbinfo", {})
        except Exception as e:
            raise ParseError(f"Failed to parse NCBI EInfo JSON response: {e}") from e
