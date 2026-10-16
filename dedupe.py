"""
Cross-source deduplication for pubmed-mcp (Phase 4).

Strategy (in order of confidence)
1. Exact PMID match
2. Exact DOI match (case-insensitive, normalized)
3. Exact PMCID match
4. Conservative title + first-author-lastname + year match
   (only when all three are present and title similarity is high)

Ambiguous matches are never silently dropped; they are returned
in a separate review list.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def _plain(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, dict):
        v = val.get("value")
        if v is None:
            return None
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        return str(v)
    if isinstance(val, list):
        return "; ".join(str(x) for x in val)
    return str(val)


def _norm_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


def _norm_pmcid(pmcid: Optional[str]) -> Optional[str]:
    if not pmcid:
        return None
    p = pmcid.strip().upper()
    if not p.startswith("PMC"):
        p = "PMC" + p
    return p


def _first_author_last(authors: Optional[str]) -> Optional[str]:
    if not authors:
        return None
    first = authors.split(";")[0].strip()
    parts = first.split()
    return parts[-1].lower() if parts else None


def _title_key(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:120] if t else None  # truncate very long titles


def deduplicate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deduplicate a list of records from one or more sources.

    Returns:
    {
      "unique": [...],           # winning records
      "duplicates_removed": N,
      "review": [                # ambiguous cases that need human eyes
        {"reason": "...", "records": [r1, r2]}
      ],
      "match_log": [             # for audit
        {"kept_pmid": "...", "dropped_pmid": "...", "matched_on": "doi"}
      ]
    }
    """
    by_pmid: Dict[str, Dict[str, Any]] = {}
    by_doi: Dict[str, str] = {}      # doi -> pmid key
    by_pmcid: Dict[str, str] = {}
    unique: List[Dict[str, Any]] = []
    match_log: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []
    seen_keys = set()

    for rec in records:
        pmid = _plain(rec.get("pmid"))
        doi = _norm_doi(_plain(rec.get("doi")))
        pmcid = _norm_pmcid(_plain(rec.get("pmcid")))
        title_k = _title_key(_plain(rec.get("title")))
        year = (_plain(rec.get("pub_date")) or "")[:4]
        author_last = _first_author_last(_plain(rec.get("authors")))

        matched = False
        match_type = None
        kept_key = None

        if pmid and pmid in by_pmid:
            matched = True
            match_type = "pmid"
            kept_key = pmid
        elif doi and doi in by_doi:
            matched = True
            match_type = "doi"
            kept_key = by_doi[doi]
        elif pmcid and pmcid in by_pmcid:
            matched = True
            match_type = "pmcid"
            kept_key = by_pmcid[pmcid]
        elif title_k and author_last and year and len(year) == 4:
            soft_key = f"{title_k}|{author_last}|{year}"
            if soft_key in seen_keys:
                # potential soft match — send to review rather than auto-merge
                review.append({
                    "reason": "possible title+author+year match (not auto-merged)",
                    "candidate_pmid": pmid,
                    "soft_key": soft_key,
                })
                # still keep the record for now; human can decide later
            else:
                seen_keys.add(soft_key)

        if matched and kept_key:
            match_log.append({
                "kept_pmid": kept_key,
                "dropped_pmid": pmid,
                "matched_on": match_type,
            })
            continue

        # new unique record
        unique.append(rec)
        if pmid:
            by_pmid[pmid] = rec
            if doi:
                by_doi[doi] = pmid
            if pmcid:
                by_pmcid[pmcid] = pmid

    return {
        "unique": unique,
        "unique_count": len(unique),
        "input_count": len(records),
        "duplicates_removed": len(records) - len(unique),
        "review": review,
        "match_log": match_log,
    }