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
import json
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
SERVER_VERSION = ncbi_client.SERVER_VERSION
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


def normalize_article(node: ET.Element) -> dict:
    """Normalize a PubmedArticle XML node into a strict schema with structured missingness indicators."""
    cit = node.find("MedlineCitation")
    art = cit.find("Article") if cit is not None else None
    if cit is None or art is None:
        return {}
    pmid = (cit.findtext("PMID") or "").strip()

    title_val = _text(art.find("ArticleTitle"))
    title = {"value": title_val, "status": "available"} if title_val != MISSING else {"value": None, "status": "missing"}

    authors_val = _authors(art)
    authors = {"value": authors_val, "status": "available"} if authors_val != MISSING else {"value": [], "status": "missing"}

    journal_val = _text(art.find("Journal/Title"))
    journal = {"value": journal_val, "status": "available"} if journal_val != MISSING else {"value": None, "status": "missing"}

    pub_date_val = _pub_date(art)
    pub_date = {"value": pub_date_val, "status": "available"} if pub_date_val != MISSING else {"value": None, "status": "missing"}

    doi_val, pmcid_val = None, None
    for aid in node.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi" and (aid.text or "").strip():
            doi_val = aid.text.strip()
        elif aid.get("IdType") == "pmc" and (aid.text or "").strip():
            pmcid_val = aid.text.strip()

    doi = {"value": doi_val, "status": "available"} if doi_val else {"value": None, "status": "not_returned_by_ncbi"}
    pmcid = {"value": pmcid_val, "status": "available"} if pmcid_val else {"value": None, "status": "not_returned_by_ncbi"}

    ptypes = [t.text.strip() for t in art.findall("PublicationTypeList/PublicationType") if t.text and t.text.strip()]
    publication_types = {"value": ptypes, "status": "available"} if ptypes else {"value": [], "status": "not_returned_by_ncbi"}

    abstract_val = _abstract(art)
    abstract = {"value": abstract_val, "status": "available"} if abstract_val != MISSING else {"value": None, "status": "missing"}

    comments_corrections = []
    has_retraction = False
    has_erratum = False
    for cc in cit.findall("CommentsCorrectionsList/CommentsCorrections"):
        ref_type = cc.get("RefType", "").strip() or "Unknown"
        cc_pmid = (cc.findtext("PMID") or "").strip() or None
        note = (cc.findtext("Note") or "").strip() or None
        if ref_type == "RetractionIn":
            has_retraction = True
        elif ref_type in ("ErratumIn", "ErratumFor"):
            has_erratum = True
        comments_corrections.append({
            "ref_type": ref_type,
            "pmid": cc_pmid,
            "note": note,
        })

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "pub_date": pub_date,
        "doi": doi,
        "pmcid": pmcid,
        "publication_types": publication_types,
        "abstract": abstract,
        "has_retraction_notice": has_retraction,
        "has_erratum_notice": has_erratum,
        "comments_corrections": comments_corrections,
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


@mcp.tool()
def pubmed_get(pmid: str, mode: str = "normalized") -> dict:
    """Retrieve a single PubMed record by PMID in normalized mode or raw verbatim XML.

    Args:
      pmid: PubMed identifier (1-9 digits).
      mode: 'normalized' (default) returns deterministic schema with structured missingness indicators;
            'raw' returns verbatim XML with SHA-256 integrity hash for auditing.
    """
    clean_pmid = str(pmid or "").strip()
    if not PMID_RE.match(clean_pmid):
        raise ValueError(f"invalid PMID {pmid!r}: PMIDs are 1-9 digits")

    clean_mode = str(mode or "normalized").strip().lower()
    if clean_mode not in ("normalized", "raw"):
        raise ValueError("mode must be 'normalized' or 'raw'")

    r = _request("efetch.fcgi", {"db": "pubmed", "id": clean_pmid, "retmode": "xml", "rettype": "abstract"}, method="POST")
    prov = client.build_provenance("efetch", {"id": clean_pmid, "mode": clean_mode})

    try:
        root = ET.fromstring(r.text)
    except Exception as e:
        raise RuntimeError(f"Failed to parse NCBI XML response: {e}")

    target_node = None
    for art_node in root.findall("PubmedArticle"):
        cit = art_node.find("MedlineCitation")
        if cit is not None and (cit.findtext("PMID") or "").strip() == clean_pmid:
            target_node = art_node
            break

    if target_node is None:
        return {
            "pmid": clean_pmid,
            "mode": clean_mode,
            "status": "not_found",
            "record": None,
            "provenance": prov,
        }

    if clean_mode == "raw":
        raw_xml = ET.tostring(target_node, encoding="unicode")
        return {
            "pmid": clean_pmid,
            "mode": "raw",
            "status": "found",
            "raw_xml": raw_xml,
            "integrity": ncbi_client.NcbiClient.compute_hash(raw_xml),
            "provenance": prov,
        }

    rec = normalize_article(target_node)
    rec_json = json.dumps(rec, sort_keys=True)
    return {
        "pmid": clean_pmid,
        "mode": "normalized",
        "status": "found",
        "record": rec,
        "integrity": ncbi_client.NcbiClient.compute_hash(rec_json),
        "provenance": prov,
    }


@mcp.tool()
def pubmed_batch_fetch(
    pmids: Optional[List[str]] = None,
    webenv: Optional[str] = None,
    query_key: Optional[str] = None,
    retstart: int = 0,
    total_records: Optional[int] = None,
    batch_size: int = 200,
) -> dict:
    """Batch fetch PubMed records in chunks supporting long PMID lists (>200) or NCBI Entrez History.

    Supports two retrieval modes:
      1. Direct PMID batching: Accepts an arbitrary list of PMIDs, chunking them into batch_size (max 200).
      2. Entrez History batching: Accepts webenv and query_key from a prior pubmed_search(..., use_history=True),
         iterating retstart up to total_records in chunks of batch_size.

    Args:
      pmids: Optional list of PMIDs (arbitrary length; chunked into batch_size).
      webenv: Optional NCBI WebEnv token from a prior pubmed_search(..., use_history=True).
      query_key: Optional NCBI QueryKey token from a prior pubmed_search.
      retstart: Starting offset for pagination (default 0).
      total_records: Total records to retrieve in Entrez History mode (if omitted, queries history count).
      batch_size: Number of records per chunk (1-200, default 200).

    Returns:
      Comprehensive batch execution report, per-batch results, per-record statuses ('status': 'success'),
      not_found PMIDs, and audit provenance.
    """
    if batch_size is None or int(batch_size) <= 0:
        raise ValueError("batch_size must be a positive integer (1-200)")
    effective_batch_size = min(int(batch_size), MAX_FETCH)
    clean_retstart = max(0, int(retstart or 0))

    has_pmids = pmids is not None and len(pmids) > 0
    has_history = bool(webenv and query_key)

    if not has_pmids and not has_history:
        raise ValueError("Must provide either a non-empty list of 'pmids' or both 'webenv' and 'query_key'.")

    clean_pmids = []
    if pmids is not None:
        seen = set()
        for p in pmids:
            s_pmid = str(p).strip()
            if not PMID_RE.match(s_pmid):
                raise ValueError(f"invalid PMID {p!r}: PMIDs are 1-9 digits")
            if s_pmid not in seen:
                seen.add(s_pmid)
                clean_pmids.append(s_pmid)
        if not clean_pmids and not has_history:
            raise ValueError("Must provide at least one valid PMID or valid 'webenv' and 'query_key'.")

    mode = "pmids" if clean_pmids else "entrez_history"
    all_records = []
    all_not_found = []
    batches_results = []
    successful_batches = 0
    failed_batches = 0

    if mode == "pmids":
        chunks = [
            clean_pmids[i : i + effective_batch_size]
            for i in range(0, len(clean_pmids), effective_batch_size)
        ]
        target_total = len(clean_pmids)

        for idx, chunk in enumerate(chunks):
            _throttle()
            params = {
                "db": "pubmed",
                "id": ",".join(chunk),
                "retmode": "xml",
                "rettype": "abstract",
            }
            batch_prov = client.build_provenance("efetch", params)
            try:
                r = _request("efetch.fcgi", params, method="POST")
                parsed = parse_efetch(r.text, chunk)
                chunk_records = [{**rec, "status": "success"} for rec in parsed.get("records", [])]
                chunk_not_found = parsed.get("not_found", [])
                all_records.extend(chunk_records)
                all_not_found.extend(chunk_not_found)
                successful_batches += 1
                batches_results.append({
                    "batch_index": idx,
                    "status": "success" if not chunk_not_found else "partial_success",
                    "requested": len(chunk),
                    "returned": len(chunk_records),
                    "retstart": idx * effective_batch_size,
                    "pmids": [rec["pmid"] for rec in chunk_records],
                    "not_found": chunk_not_found,
                    "records": chunk_records,
                    "error": None,
                    "provenance": batch_prov,
                })
            except Exception as e:
                failed_batches += 1
                all_not_found.extend(chunk)
                batches_results.append({
                    "batch_index": idx,
                    "status": "failed",
                    "requested": len(chunk),
                    "returned": 0,
                    "retstart": idx * effective_batch_size,
                    "pmids": [],
                    "not_found": chunk,
                    "records": [],
                    "error": str(e),
                    "provenance": batch_prov,
                })

    else:
        # Entrez History mode
        if total_records is not None:
            target_total = max(0, int(total_records))
        else:
            search_params = {
                "db": "pubmed",
                "WebEnv": webenv,
                "query_key": query_key,
                "retmax": 0,
                "retmode": "json",
            }
            try:
                esearch_res = _request("esearch.fcgi", search_params, method="GET").json().get("esearchresult", {})
                total_history_count = int(esearch_res.get("count", 0))
                target_total = max(0, total_history_count - clean_retstart)
            except Exception as e:
                log.warning("Could not determine total records from history count: %s", e)
                target_total = None

        fetched_so_far = 0
        batch_idx = 0

        while True:
            if target_total is not None and fetched_so_far >= target_total:
                break

            chunk_size = effective_batch_size
            if target_total is not None:
                chunk_size = min(chunk_size, target_total - fetched_so_far)

            if chunk_size <= 0:
                break

            curr_retstart = clean_retstart + fetched_so_far
            _throttle()
            params = {
                "db": "pubmed",
                "WebEnv": webenv,
                "query_key": query_key,
                "retstart": curr_retstart,
                "retmax": chunk_size,
                "retmode": "xml",
                "rettype": "abstract",
            }
            batch_prov = client.build_provenance("efetch", params)

            try:
                r = _request("efetch.fcgi", params, method="POST")
                root = ET.fromstring(r.text)
                batch_articles = [parse_article(n) for n in root.findall("PubmedArticle")]
                chunk_records = [{**rec, "status": "success"} for rec in batch_articles if rec]
                ret_count = len(chunk_records)
                all_records.extend(chunk_records)
                successful_batches += 1

                batches_results.append({
                    "batch_index": batch_idx,
                    "status": "success",
                    "requested": chunk_size,
                    "returned": ret_count,
                    "retstart": curr_retstart,
                    "pmids": [rec["pmid"] for rec in chunk_records],
                    "not_found": [],
                    "records": chunk_records,
                    "error": None,
                    "provenance": batch_prov,
                })

                fetched_so_far += ret_count
                batch_idx += 1

                # If NCBI returned fewer records than requested or 0 records, we have reached the end
                if ret_count < chunk_size:
                    break

            except Exception as e:
                failed_batches += 1
                batches_results.append({
                    "batch_index": batch_idx,
                    "status": "failed",
                    "requested": chunk_size,
                    "returned": 0,
                    "retstart": curr_retstart,
                    "pmids": [],
                    "not_found": [],
                    "records": [],
                    "error": str(e),
                    "provenance": batch_prov,
                })
                fetched_so_far += chunk_size
                batch_idx += 1

    results_summary = (
        [{"pmid": r["pmid"], "status": "success"} for r in all_records]
        + [{"pmid": p, "status": "not_found"} for p in all_not_found]
    )

    overall_prov = client.build_provenance(
        "efetch_batch",
        {
            "mode": mode,
            "total_requested": len(clean_pmids) if mode == "pmids" else target_total,
            "total_returned": len(all_records),
            "batches_executed": len(batches_results),
            "batch_size": effective_batch_size,
            "retstart": clean_retstart,
            "webenv": webenv if mode == "entrez_history" else None,
            "query_key": query_key if mode == "entrez_history" else None,
        },
    )

    return {
        "mode": mode,
        "total_requested": len(clean_pmids) if mode == "pmids" else (target_total if target_total is not None else len(all_records)),
        "total_returned": len(all_records),
        "batches_executed": len(batches_results),
        "batches_successful": successful_batches,
        "batches_failed": failed_batches,
        "batch_size": effective_batch_size,
        "batches": batches_results,
        "records": all_records,
        "not_found": all_not_found,
        "results_summary": results_summary,
        "provenance": overall_prov,
    }


def main():
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
