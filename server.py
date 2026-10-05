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
import access
import ncbi_client
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pubmed-mcp")

EUTILS = ncbi_client.EUTILS_BASE
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

client = ncbi_client.NcbiClient()


# ----------------------------------------------------------------- config / HTTP delegates
def _env(name: str) -> Optional[str]:
    return client.env(name)


def _throttle() -> None:
    client.throttle()


def _request(endpoint: str, params: dict, method: str = "GET") -> requests.Response:
    return client.request(endpoint, params, method)



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
    doi, pmcid = MISSING, MISSING
    for aid in node.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi" and (aid.text or "").strip():
            doi = aid.text.strip()
        elif aid.get("IdType") == "pmc" and (aid.text or "").strip():
            pmcid = aid.text.strip()
    ptypes = [t.text.strip() for t in art.findall("PublicationTypeList/PublicationType") if t.text and t.text.strip()]
    retraction = any(c.get("RefType") == "RetractionIn" for c in cit.findall("CommentsCorrectionsList/CommentsCorrections"))
    return {
        "pmid": pmid,
        "title": _text(art.find("ArticleTitle")),
        "authors": _authors(art),
        "journal": _text(art.find("Journal/Title")),
        "pub_date": _pub_date(art),
        "doi": doi,
        "pmcid": pmcid,
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


@mcp.tool()
def check_access(pmids: List[str]) -> dict:
    """Classify each PMID as open-access PDF, open-access landing page only, no open access found (likely paywalled), or unchecked.

    Uses DOI -> Unpaywall and PMCID -> PubMed Central. 'no_open_access_found' means no legal free copy is indexed;
    it does not prove the paper cannot be reached through an institution. Max 100 PMIDs per call.
    Needs UNPAYWALL_EMAIL (or NCBI_EMAIL) for the Unpaywall lookup; without it only PubMed Central links are found.
    """
    ids = [str(p).strip() for p in (pmids or [])]
    if len(set(ids)) > 100:
        raise ValueError("max 100 PMIDs per call; split the request")
    data = fetch_abstracts(ids)
    email = access.unpaywall_email()
    out = access.summarize(access.check_records(data["records"], email))
    out.update({"requested": data["requested"], "not_found": data["not_found"], "unpaywall_email_configured": bool(email)})
    return out


@mcp.tool()
def search_with_access(query: str, max_results: int = 20, sort: str = "relevance",
                       date_from: Optional[int] = None, date_to: Optional[int] = None) -> dict:
    """Run a PubMed search, then report for every hit whether a legal open-access PDF exists or the paper looks paywalled.

    max_results is capped at 100 here. Returns query_translation and total_matches (as search_pubmed) plus
    counts and four lists: open_access_pdf, open_access_landing_page_only, no_open_access_found, unchecked.
    """
    s = search_pubmed(query, min(int(max_results), 100), sort, date_from, date_to)
    head = {"query_submitted": s["query_submitted"], "query_translation": s["query_translation"],
            "total_matches": s["total_matches"], "returned": s["returned"], "warnings": s["warnings"]}
    if not s["pmids"]:
        return {**head, **access.summarize([])}
    return {**head, **check_access(s["pmids"])}


@mcp.tool()
def download_pdfs(pmids: List[str], folder: Optional[str] = None) -> dict:
    """Download open-access PDFs for the given PMIDs (max 50) as PMID<id>.pdf. Paywalled papers are skipped, never bypassed.

    folder: absolute path, or a sub-folder name under PUBMED_PDF_DIR (default ~/pubmed_pdfs). Every file is verified
    to be a real PDF (starts with %PDF); HTML login/bot-check pages are rejected and reported as failed.
    """
    ids = [str(p).strip() for p in (pmids or [])]
    if len(set(ids)) > 50:
        raise ValueError("max 50 PMIDs per call; split the request")
    data = fetch_abstracts(ids)
    results = access.check_records(data["records"], access.unpaywall_email())
    dest = access.target_dir(folder)
    rows = access.download_many(results, dest)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"folder": str(dest), "counts": counts, "results": rows, "not_found": data["not_found"]}


# ----------------------------------------------------------------- target tools (evidence-synthesis & provenance-first)
@mcp.tool()
def pubmed_database_info(db: str = "pubmed") -> dict:
    """Get metadata, last update date, record count, and search field tags for an NCBI database (default: 'pubmed').

    Provides audit-grade database metadata and field definitions directly from NCBI EInfo.
    """
    clean_db = (db or "pubmed").strip().lower()
    res = _request("einfo.fcgi", {"db": clean_db, "retmode": "json"}, method="GET")
    data = res.json().get("einforesult", {}).get("dbinfo", {})
    prov = client.build_provenance("einfo", {"db": clean_db}, database=clean_db)
    fields = [
        {"name": f.get("name"), "full_name": f.get("fullname"), "description": f.get("description")}
        for f in data.get("fieldlist", [])
    ]
    return {
        "database": data.get("dbname") or clean_db,
        "menu_name": data.get("menuname") or MISSING,
        "description": data.get("description") or MISSING,
        "record_count": int(data.get("count", 0)),
        "last_update": data.get("lastupdate") or MISSING,
        "field_count": len(fields),
        "fields": fields,
        "provenance": prov,
    }


@mcp.tool()
def pubmed_search(
    query: str,
    max_results: int = 20,
    start: int = 0,
    sort: str = "relevance",
    date_from: Optional[int] = None,
    date_to: Optional[int] = None,
    use_history: bool = False,
) -> dict:
    """Search PubMed (NCBI esearch) with reproducibility object, query translation, and audit provenance.

    Args:
      query: PubMed query; supports field tags, MeSH, and Boolean logic.
      max_results: 1-200 (default 20).
      start: Result offset / retstart for pagination (default 0).
      sort: 'relevance' or 'pub_date' (newest first).
      date_from / date_to: Optional publication-year bounds.
      use_history: If True, stores search on NCBI Entrez History server (returns webenv & query_key).
    """
    q = (query or "").strip()
    if not q:
        raise ValueError("query must be non-empty")
    if sort not in ("relevance", "pub_date"):
        raise ValueError("sort must be 'relevance' or 'pub_date'")
    n = max(1, min(int(max_results), MAX_SEARCH))
    retstart = max(0, int(start))
    params = {"db": "pubmed", "term": q, "retmax": n, "retstart": retstart, "retmode": "json", "sort": sort}
    if use_history:
        params["usehistory"] = "y"
    if date_from or date_to:
        params.update({
            "datetype": "pdat",
            "mindate": str(date_from or 1800),
            "maxdate": str(date_to or datetime.date.today().year + 1),
        })
    res = _request("esearch.fcgi", params).json().get("esearchresult", {})
    if "ERROR" in res:
        raise RuntimeError(f"NCBI esearch error: {res['ERROR']}")

    prov = client.build_provenance("esearch", params)
    return {
        "search": {
            "database": "pubmed",
            "original_query": q,
            "effective_query": res.get("querytranslation") or MISSING,
            "retstart": retstart,
            "retmax": n,
            "sort": sort,
            "count": int(res.get("count", 0)),
            "executed_at": prov["timestamp"],
        },
        "returned": len(res.get("idlist", [])),
        "pmids": res.get("idlist", []),
        "webenv": res.get("webenv"),
        "query_key": res.get("querykey"),
        "warnings": (res.get("warninglist") or {}).get("outputmessage", [])
        + (res.get("errorlist") or {}).get("phrasesnotfound", []),
        "provenance": prov,
    }


@mcp.tool()
def pubmed_fetch(pmids: List[str]) -> dict:
    """Fetch exact PubMed records (NCBI efetch) with per-record status and provenance.

    Every field comes strictly from the NCBI response; missing fields are flagged and never inferred.
    Returns records with 'status': 'success' and unretrieved items with 'status': 'not_found'.
    """
    base = fetch_abstracts(pmids)
    prov = client.build_provenance("efetch", {"pmids": pmids})
    records_with_status = [{**r, "status": "success"} for r in base.get("records", [])]
    not_found_with_status = [{"pmid": p, "status": "not_found"} for p in base.get("not_found", [])]
    return {
        "requested": base["requested"],
        "returned": base["returned"],
        "records": records_with_status,
        "not_found": base["not_found"],
        "results_summary": records_with_status + not_found_with_status,
        "provenance": prov,
    }


def main():
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
