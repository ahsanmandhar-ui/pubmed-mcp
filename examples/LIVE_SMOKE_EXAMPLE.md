# Live Smoke Example — End-to-End Server Check

A minimal end-to-end smoke test that verifies the pubmed-mcp server responds,
returns normalized records with provenance, and surfaces retraction/erratum
flags exactly as NCBI provides them. No data is invented.

## Step 1: Search (live, against NCBI)

```python
import server, json

result = server.pubmed_search(
    query='("Escherichia coli"[All Fields]) AND (tetracycline[All Fields]) AND (resistance[All Fields])',
    max_results=5,
    use_history=True,
)
print(json.dumps(result, indent=2)[:1200])
```

Expected shape:
- `search.count` — total match count from NCBI
- `search.effective_query` — how NCBI translated the query
- `pmids` — list of PMIDs (up to `max_results`)
- `webenv` / `query_key` — Entrez History tokens (when `use_history=True`)
- `warnings` — NCBI warning / phrase-not-found messages

## Step 2: Fetch a single normalized record

```python
pmid = result["pmids"][0]
record = server.pubmed_get(pmid=pmid, mode="normalized")
print(json.dumps(record, indent=2)[:1200])
```

Every field carries a provenance status (`directly_sourced` /
`not_returned_by_ncbi`). Missing fields are flagged, never inferred.

Expected fields on the record:
- `title`, `authors`, `journal`, `pub_date`, `doi`, `pmcid`, `abstract`
- `publication_types`, `has_retraction_notice`, `has_erratum_notice`
- `comments_corrections`, `url`
- `integrity.response_hash` — SHA-256 of the raw NCBI response

## Step 3: Verify anti-inference guarantee

```python
from benchmark import false_inference_count, run_default_benchmark
r = run_default_benchmark()
assert false_inference_count == 0
assert r["passed"] is True
```

## Constants referenced

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_SEARCH` | 9999 | Max PMIDs per `pubmed_search` call |
| `MAX_FETCH` | 200 | Max PMIDs per `efetch` batch |
| `MISSING` | `"Data not provided in PubMed abstract"` | Literal for absent fields |

## No secrets

This example uses no API keys, no emails, and no real credentials. Set
`NCBI_EMAIL` / `UNPAYWALL_EMAIL` / `NCBI_API_KEY` in your own environment if
needed — never commit them.