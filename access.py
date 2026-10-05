"""Open-access discovery and PDF download for PubMed records.

Rules (same philosophy as server.py): report only what the sources return; never guess.
Sources: DOI -> Unpaywall (legal open-access locations); PMCID (from PubMed) -> PubMed Central.
No paywall bypass, no shadow libraries. A paper with no open-access copy is reported as such.
"""
import ipaddress
import os
import time
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import quote, urlparse

import requests

MISSING = "Data not provided in PubMed abstract"
NO_PDF = "No open-access PDF found"
UNPAYWALL = "https://api.unpaywall.org/v2"
PMC_PDF = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"
PMC_PAGE = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
MAX_BYTES = 60 * 1024 * 1024
UA = {"User-Agent": "pubmed-mcp/1.0 (open-source research tool)"}

OPEN_PDF = "OPEN_ACCESS_PDF"
OPEN_LANDING = "OPEN_ACCESS_LANDING_PAGE_ONLY"
NO_OA = "NO_OPEN_ACCESS_FOUND"
UNCHECKED = "UNCHECKED"
NO_OA_NOTE = ("No legal open-access copy was indexed by Unpaywall/PubMed Central at check time. Likely paywalled; "
              "it may still be reachable through your institution, or as an author copy/preprint that is not indexed.")


def _clean(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    return None if (not v or v.upper().startswith("YOUR_") or v.startswith("${")) else v


def unpaywall_email() -> Optional[str]:
    return _clean(os.environ.get("UNPAYWALL_EMAIL")) or _clean(os.environ.get("NCBI_EMAIL"))


def _safe_url(u: str) -> bool:
    p = urlparse(u or "")
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    if p.hostname.lower() == "localhost":
        return False
    try:
        ip = ipaddress.ip_address(p.hostname)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return True  # a normal hostname


def _unpaywall(doi: str, email: str, get: Callable):
    try:
        r = get(f"{UNPAYWALL}/{quote(doi, safe='/:()')}", params={"email": email}, headers=UA, timeout=30)
    except requests.RequestException as e:
        return None, f"Unpaywall request failed: {type(e).__name__}"
    if r.status_code == 404:
        return None, "DOI not found in Unpaywall"
    if r.status_code != 200:
        return None, f"Unpaywall HTTP {r.status_code}"
    try:
        return r.json(), None
    except ValueError:
        return None, "Unpaywall returned invalid JSON"


def classify(rec: dict, email: Optional[str], get: Callable = requests.get) -> dict:
    doi, pmcid = rec.get("doi", MISSING), rec.get("pmcid", MISSING)
    has_doi, has_pmc = doi != MISSING, pmcid != MISSING
    cands, landing, oa_status, note, lookup_ok, is_oa = [], None, "not_checked", "", False, None
    if has_doi and email:
        data, err = _unpaywall(doi, email, get)
        if data:
            lookup_ok, is_oa = True, data.get("is_oa")
            oa_status = data.get("oa_status") or MISSING
            locs = ([data["best_oa_location"]] if data.get("best_oa_location") else []) + (data.get("oa_locations") or [])
            seen = set()
            for loc in locs:
                pdf, page = loc.get("url_for_pdf"), loc.get("url")
                if pdf and pdf not in seen and _safe_url(pdf):
                    seen.add(pdf)
                    cands.append({"url": pdf, "source": f"Unpaywall ({loc.get('host_type') or 'unknown host'})",
                                  "license": loc.get("license") or MISSING, "version": loc.get("version") or MISSING})
                elif page and landing is None and _safe_url(page):
                    landing = page
        else:
            note = err
    elif has_doi:
        note = "Set UNPAYWALL_EMAIL (or NCBI_EMAIL) to enable the Unpaywall lookup."
    if has_pmc:
        cands.append({"url": PMC_PDF.format(pmcid=pmcid), "source": "PubMed Central", "license": MISSING, "version": MISSING})
        landing = landing or PMC_PAGE.format(pmcid=pmcid)
    if cands:
        access = OPEN_PDF
    elif landing:
        access = OPEN_LANDING
    elif lookup_ok and not is_oa:
        access, note = NO_OA, NO_OA_NOTE
    else:
        access = UNCHECKED
        note = note or ("No DOI or PMCID in the PubMed record." if not (has_doi or has_pmc) else "Open-access status could not be determined.")
    return {"pmid": rec.get("pmid"), "title": rec.get("title"), "pub_date": rec.get("pub_date"), "doi": doi, "pmcid": pmcid,
            "has_retraction_notice": rec.get("has_retraction_notice", False), "access": access, "oa_status": oa_status,
            "pdf_candidates": cands, "landing_url": landing or NO_PDF, "note": note}


def check_records(records: List[dict], email: Optional[str], get: Callable = requests.get, delay: float = 0.15) -> List[dict]:
    out = []
    for i, rec in enumerate(records):
        if i and email:
            time.sleep(delay)
        out.append(classify(rec, email, get))
    return out


def summarize(results: List[dict]) -> dict:
    groups = {OPEN_PDF: [], OPEN_LANDING: [], NO_OA: [], UNCHECKED: []}
    for r in results:
        c = r["pdf_candidates"]
        item = {"pmid": r["pmid"], "title": r["title"], "pub_date": r["pub_date"], "doi": r["doi"],
                "oa_status": r["oa_status"], "has_retraction_notice": r["has_retraction_notice"]}
        if r["access"] == OPEN_PDF:
            item.update(pdf_url=c[0]["url"], source=c[0]["source"], other_pdf_sources=len(c) - 1)
        elif r["access"] == OPEN_LANDING:
            item["landing_url"] = r["landing_url"]
        else:
            item["note"] = r["note"]
        groups[r["access"]].append(item)
    return {"counts": {k: len(v) for k, v in groups.items()},
            "open_access_pdf": groups[OPEN_PDF], "open_access_landing_page_only": groups[OPEN_LANDING],
            "no_open_access_found": groups[NO_OA], "unchecked": groups[UNCHECKED]}


def target_dir(folder: Optional[str]) -> Path:
    root = Path(os.environ.get("PUBMED_PDF_DIR") or (Path.home() / "pubmed_pdfs"))
    if folder:
        p = Path(folder)
        if p.is_absolute():
            root = p
        elif ".." in p.parts:
            raise ValueError("folder must not contain '..'")
        else:
            root = root / p
    root.mkdir(parents=True, exist_ok=True)
    return root


def _download(url: str, dest: Path, get: Callable) -> int:
    if not _safe_url(url):
        raise ValueError("unsafe or invalid URL")
    r = get(url, stream=True, timeout=60, headers=UA, allow_redirects=True)
    part = dest.with_suffix(".part")
    try:
        if r.status_code != 200:
            raise ValueError(f"HTTP {r.status_code}")
        if int(r.headers.get("Content-Length") or 0) > MAX_BYTES:
            raise ValueError("file larger than 60 MB limit")
        size, first = 0, True
        with open(part, "wb") as f:
            for chunk in r.iter_content(65536):
                if first:
                    if not chunk.startswith(b"%PDF"):
                        raise ValueError("response is not a PDF (login, consent or bot-check page)")
                    first = False
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("file larger than 60 MB limit")
                f.write(chunk)
        if size == 0:
            raise ValueError("empty response")
        part.replace(dest)
        return size
    finally:
        r.close()
        if part.exists():
            part.unlink()


def download_many(results: List[dict], folder: Path, get: Callable = requests.get, delay: float = 0.5) -> List[dict]:
    out = []
    for r in results:
        pmid = str(r["pmid"])
        dest = folder / f"PMID{pmid}.pdf"
        if not r["pdf_candidates"]:
            out.append({"pmid": pmid, "status": "skipped", "reason": f"no direct open-access PDF link (access={r['access']})"})
            continue
        if dest.exists() and dest.stat().st_size > 0:
            out.append({"pmid": pmid, "status": "already_exists", "file": str(dest)})
            continue
        errors = []
        for c in r["pdf_candidates"]:
            try:
                size = _download(c["url"], dest, get)
                out.append({"pmid": pmid, "status": "downloaded", "file": str(dest), "bytes": size, "source": c["source"], "url": c["url"]})
                break
            except (ValueError, OSError, requests.RequestException) as e:
                errors.append(f"{c['source']}: {e}")
            time.sleep(delay)
        else:
            out.append({"pmid": pmid, "status": "failed", "reason": errors})
    return out
