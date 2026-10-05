#!/usr/bin/env python3
"""PubMed MCP server — NCBI E-utilities (esearch + efetch) over stdio.

Design guarantees
-----------------
* Every field comes from the NCBI response. Nothing is inferred, guessed or paraphrased.
* A field PubMed does not provide is returned as the literal string MISSING
  ("Data not provided in PubMed abstract").
* PMIDs that were requested but not returned by NCBI are listed in `not_found`, never fabricated.
* stdout is reserved for the MCP protocol; all logging goes to stderr.

Env (all optional): NCBI_API_KEY, NCBI_EMAIL, NCBI_TOOL
"""
import datetime
import logging
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from typing import List, Optional

import requests
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pubmed-mcp")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MISSING = "Data not provided in PubMed abstract"
MAX_SEARCH = 200
MAX_FETCH = 200
PMID_RE = re.compile(r"^\d{1,9}$")

mcp = FastMCP(
    "pubmed-scraper",
    instructions=(
        "Search PubMed and fetch exact records via NCBI E-utilities. Report only what the tools return. "
        f"If a field equals '{MISSING}', say so; never infer or fill in missing text. "
        "Do not assign evidence levels from the tool output alone: use publication_types plus the full text."
    ),
)


# ----------------------------------------------------------------- config / HTTP
def _env(name: str) -> Optional[str]:
    v = os.environ.get(name, "").strip()
    if not v or v.upper().startswith("YOUR_") or v.startswith("${"):
        return None  # ignore unfilled placeholders instead of sending a bad key to NCBI
    return v


_lock = threading.Lock()
_last_call = 0.0


def _throttle() -> None:
    """NCBI limits: 3 requests/s without an API key, 10/s with one."""
    global _last_call
    gap = 0.11 if _env("NCBI_API_KEY") else 0.34
    with _lock:
        wait = _last_call + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _request(endpoint: str, params: dict, method: str = "GET") -> requests.Response:
    params = {**params, "tool": _env("NCBI_TOOL") or "pubmed-mcp"}
    if _env("NCBI_EMAIL"):
        params["email"] = _env("NCBI_EMAIL")
    if _env("NCBI_API_KEY"):
        params["api_key"] = _env("NCBI_API_KEY")
    url = f"{EUTILS}/{endpoint}"
    last = "unknown error"
    for attempt in range(4):
        _throttle()
        try:
            r = requests.post(url, data=params, timeout=45) if method == "POST" else requests.get(url, params=params, timeout=45)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"NCBI E-utilities request to {endpoint} failed: {last}")


# ----------------------------------------------------------------- parsing (pure functions, unit-tested offline)
def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return MISSING
    t = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
    return t or MISSING


def _authors(art: ET.Element):
    out = []
    for a in art.findall("AuthorList/Author"):
        coll = a.findtext("CollectiveName")
        if coll:
            out.append(coll.strip())
            continue
        last, fore = a.findtext("LastName"), a.findtext("ForeName") or a.findtext("Initials")
        if last:
            out.append(f"{last.strip()} {fore.strip()}" if fore else last.strip())
    return out or MISSING


def _abstract(art: ET.Element) -> str:
    parts = []
    for el in art.findall("Abstract/AbstractText"):
        body = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
        if not body:
            continue
        label = el.get("Label")
        parts.append(f"{label}: {body}" if label else body)
    return "\n".join(parts) if parts else MISSING


def _pub_date(art: ET.Element) -> str:
    pd = art.find("Journal/JournalIssue/PubDate")
    if pd is None:
        return MISSING
    bits = [pd.findtext(k) for k in ("Year", "Month", "Day")]
    bits = [b for b in bits if b]
    return " ".join(bits) if bits else (pd.findtext("MedlineDate") or MISSING)


def parse_article(node: ET.Element) -> dict:
    cit = node.find("MedlineCitation")
    art = cit.find("Article") if cit is not None else None
    if cit is None or art is None:
        return {}
    pmid = (cit.findtext("PMID") or "").strip()
    doi = MISSING
    for aid in node.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi" and (aid.text or "").strip():
            doi = aid.text.strip()
    ptypes = [t.text.strip() for t in art.findall("PublicationTypeList/PublicationType") if t.text and t.text.strip()]
    retraction = any(c.get("RefType") == "RetractionIn" for c in cit.findall("CommentsCorrectionsList/CommentsCorrections"))
    return {
        "pmid": pmid,
        "title": _text(art.find("ArticleTitle")),
        "authors": _authors(art),
        "journal": _text(art.find("Journal/Title")),
        "pub_date": _pub_date(art),
        "doi": doi,
        "publication_types": ptypes or MISSING,
        "has_retraction_notice": retraction,  # True only if NCBI lists a 'RetractionIn' link for this record
        "abstract": _abstract(art),
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def parse_efetch(xml_text: str, requested: List[str]) -> dict:
    root = ET.fromstring(xml_text)
    records = [r for r in (parse_article(n) for n in root.findall("PubmedArticle")) if r]
    got = {r["pmid"] for r in records}
    return {"requested": len(requested), "returned": len(records), "records": records,
            "not_found": [p for p in requested if p not in got]}


# ----------------------------------------------------------------- tools
@mcp.tool()
def search_pubmed(query: str, max_results: int = 20, sort: str = "relevance",
                  date_from: Optional[int] = None, date_to: Optional[int] = None) -> dict:
    """Search PubMed (NCBI esearch) and return PMIDs exactly as NCBI returns them.

    Args:
      query: PubMed query; supports field tags, MeSH and Boolean, e.g.
             '"hypertrophic cardiomyopathy"[MeSH] AND mavacamten[tiab] AND randomized controlled trial[pt]'.
      max_results: 1-200 (default 20). `total_matches` reports the full hit count.
      sort: 'relevance' or 'pub_date' (newest first).
      date_from / date_to: optional publication-year bounds (e.g. 2018, 2025).
    Returns pmids, total_matches and query_translation (how PubMed interpreted the query; log it for reproducibility).
    """
    q = (query or "").strip()
    if not q:
        raise ValueError("query must be non-empty")
    if sort not in ("relevance", "pub_date"):
        raise ValueError("sort must be 'relevance' or 'pub_date'")
    n = max(1, min(int(max_results), MAX_SEARCH))
    params = {"db": "pubmed", "term": q, "retmax": n, "retmode": "json", "sort": sort}
    if date_from or date_to:
        params.update({"datetype": "pdat", "mindate": str(date_from or 1800),
                       "maxdate": str(date_to or datetime.date.today().year + 1)})
    res = _request("esearch.fcgi", params).json().get("esearchresult", {})
    if "ERROR" in res:
        raise RuntimeError(f"NCBI esearch error: {res['ERROR']}")
    return {
        "query_submitted": q,
        "query_translation": res.get("querytranslation") or MISSING,
        "total_matches": int(res.get("count", 0)),
        "max_results_applied": n,
        "returned": len(res.get("idlist", [])),
        "pmids": res.get("idlist", []),
        "warnings": (res.get("warninglist") or {}).get("outputmessage", []) + (res.get("errorlist") or {}).get("phrasesnotfound", []),
    }


@mcp.tool()
def fetch_abstracts(pmids: List[str]) -> dict:
    """Fetch exact PubMed records (NCBI efetch) for up to 200 PMIDs.

    Per record: pmid, title, authors, journal, pub_date, doi, publication_types, has_retraction_notice,
    abstract (structured abstracts keep their section labels), url.
    Any field PubMed does not provide is the literal string 'Data not provided in PubMed abstract'.
    PMIDs NCBI did not return are listed in `not_found`. Never infer or complete missing text.
    """
    seen, ids = set(), []
    for p in pmids or []:
        s = str(p).strip()
        if not PMID_RE.match(s):
            raise ValueError(f"invalid PMID {p!r}: PMIDs are 1-9 digits")
        if s not in seen:
            seen.add(s)
            ids.append(s)
    if not ids:
        raise ValueError("provide at least one PMID")
    if len(ids) > MAX_FETCH:
        raise ValueError(f"max {MAX_FETCH} PMIDs per call (got {len(ids)}); split the request")
    r = _request("efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", "rettype": "abstract"}, method="POST")
    return parse_efetch(r.text, ids)


if __name__ == "__main__":
    mcp.run()  # stdio transport
