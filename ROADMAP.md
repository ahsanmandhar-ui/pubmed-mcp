# pubmed-mcp Roadmap — Evidence Synthesis Focus

**Core differentiators (never compromise):**
1. Every claim is traceable to a source.
2. Every search is reproducible.
3. Every failure or missing value is explicit.

---

## Phase 1 — Reliability Foundation ✅ DONE
- Evidence Provenance Ledger (field-level status + source + timestamp)
- Search Snapshots (`PUBMED-YYYYMMDD-XXXXXX`)
- Tools: `pubmed_create_search_snapshot`, `pubmed_get_snapshot`, `pubmed_list_snapshots`
- 41 offline tests passing

---

## Phase 2 — Research Workflow (CURRENT)

### 2.1 Bibliographic Exports (P0)
Clean, standards-compliant exporters:
- `pubmed_export_ris`
- `pubmed_export_bibtex`
- `pubmed_export_csv`
- `pubmed_export_json`

All exporters must:
- Accept either a list of PMIDs **or** a snapshot_id
- Never invent missing fields
- Mark unavailable fields explicitly
- Include provenance / retrieval metadata where the format allows

### 2.2 Snapshot → Export Pipeline
- One-command export of an entire search snapshot
- Preserve original query, translation, counts, and timestamp in the export header or sidecar when possible

### 2.3 Full-text / Download Audit Trail (P1)
Strengthen the existing open-access path:
- Record access route (PMC / Unpaywall / none)
- Download status (`success` | `skipped_paywalled` | `failed` | `not_attempted`)
- File checksum (SHA-256)
- Clear distinction: metadata only / abstract / full-text

### 2.4 Documentation updates
- ROADMAP.md (this file)
- DEVELOPMENT_STATE.md
- README tool tables

---

## Phase 3 — Structured Evidence Tables (source-linked only)
- Extract only what is explicitly present
- Every cell carries source location + extraction status
- Distinguish `not reported` / `not retrieved` / `not applicable`

## Phase 4 — Differentiation
- Europe PMC adapter + careful deduplication
- Citation chasing (with coverage notes)
- Retraction / correction monitoring for saved libraries

## Explicitly out of scope
- Automatic GRADE or risk-of-bias
- Unvalidated AI-generated study characteristics
- Claims of exhaustive searching
- Complex web dashboard
- Tool explosion that reduces auditability