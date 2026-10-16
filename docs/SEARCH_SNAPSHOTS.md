# Search Snapshots

## Identifier format

```
PUBMED-YYYYMMDD-XXXXXX
```

Example: `PUBMED-20261017-A3F9C2`

- Date is UTC
- Suffix is 6 random hex characters (cryptographically random)

## What is stored

| Field | Purpose |
|-------|---------|
| `snapshot_id` | Stable identifier |
| `created_at` | UTC timestamp |
| `original_query` | Exactly what the user submitted |
| `effective_query` | NCBI’s translated query |
| `total_matches` | Hit count reported by NCBI at execution time |
| `pmids` | List of PMIDs returned in this snapshot |
| `retmax` / `sort` / date limits | Parameters used |
| `webenv` / `query_key` | Entrez History tokens when used |
| `response_hash` | SHA-256 of the raw response (optional but recommended) |

## Lifetime

Phase 1 uses an in-process store. Snapshots live only for the lifetime of the MCP server process.  
A later phase can add optional file or SQLite persistence without changing the tool names.

## Tools

- `pubmed_create_search_snapshot(...)` → returns the full snapshot including ID
- `pubmed_get_snapshot(snapshot_id)` → retrieve one
- `pubmed_list_snapshots(limit=20)` → recent list

These tools never invent results; they only store and return what was previously obtained from NCBI.