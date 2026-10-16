# Systematic Review Example — Full Retrieval via Entrez History + Batch Fetch

## Problem

`pubmed_search` caps at `MAX_SEARCH` (9999) records per call. For systematic reviews
where `total_matches` can be far larger (e.g. thousands of results), a single
`pubmed_search` only returns the first `max_results` PMIDs.

## Solution — Two-step retrieval

Use NCBI Entrez History to store the search, then batch-fetch all records.

### Step 1: Search with history enabled

```python
result = server.pubmed_search(
    query='("Escherichia coli"[All Fields]) AND (tetracycline[All Fields] OR doxycycline[All Fields]) AND (resistance[All Fields])',
    max_results=200,
    use_history=True,
)
total_matches = result["search"]["count"]   # e.g. 1282
webenv = result["webenv"]
query_key = result["query_key"]
```

The response always includes `webenv` and `query_key` when `use_history=True`.

### Step 2: Batch fetch all records

```python
batch = server.pubmed_batch_fetch(
    webenv=webenv,
    query_key=query_key,
    total_records=total_matches,
    batch_size=200,   # efetch batches stay within MAX_FETCH=200
)
all_records = batch["records"]   # every record, up to total_records
```

`pubmed_batch_fetch` iterates `retstart` in chunks of `batch_size` (max `MAX_FETCH=200`)
until `total_records` is reached or NCBI returns fewer records than requested.

## Key constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_SEARCH` | 9999 | Max PMIDs per `pubmed_search` / `search_pubmed` call |
| `MAX_FETCH` | 200  | Max PMIDs per `efetch` batch (safe for NCBI) |

## Anti-inference guarantee

Every field in every fetched record carries a provenance status
(`directly_sourced` / `not_returned_by_ncbi`). Nothing is inferred or fabricated.
Retraction/erratum flags are reported exactly as NCBI provides them.