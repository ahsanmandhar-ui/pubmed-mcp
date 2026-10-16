# Evidence Provenance Ledger — Schema 1.1

## Field-level entry

```json
{
  "value": "any JSON-serializable value or null",
  "status": "directly_sourced | transformed | unavailable | not_returned_by_ncbi | parse_error | not_applicable",
  "source": "NCBI PubMed",
  "pmid": "12345678",
  "retrieved_at": "2026-10-17T01:00:00+00:00",
  "note": "optional free-text note"
}
```

### Status meanings

| Status | Meaning |
|--------|---------|
| `directly_sourced` | Value taken exactly (or after trivial whitespace normalization) from the NCBI record |
| `transformed` | Value was lightly processed (e.g. structured abstract labels preserved) but content is still from NCBI |
| `unavailable` | Field existed in the XML but was empty / blank |
| `not_returned_by_ncbi` | NCBI simply did not include this field for the record |
| `parse_error` | XML was present but could not be parsed for this field |
| `not_applicable` | Field does not apply to this publication type |

## Record-level provenance block

```json
{
  "provider": "NCBI PubMed",
  "database": "pubmed",
  "utility": "efetch",
  "timestamp": "2026-10-17T01:00:00+00:00",
  "server_version": "0.3.0-dev",
  "schema_version": "1.1",
  "parser_version": "1.1",
  "pmid": "12345678",
  "request_parameters": { "...": "sanitized" },
  "response_hash": {
    "algorithm": "sha256",
    "value": "abc123..."
  }
}
```

## Rules

1. Never invent a value. If NCBI did not supply it, status must be one of the explicit missing/unavailable codes.
2. Secrets (API keys, tokens) must never appear in any provenance object.
3. The ledger is additive — older clients that ignore the new fields continue to work.