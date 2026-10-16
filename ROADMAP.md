# pubmed-mcp Roadmap — Evidence Synthesis Focus

**Goal:** Turn this server into reliable infrastructure for moving from a research question to a reproducible, auditable collection of studies — without allowing the AI to invent missing evidence.

**Core differentiators (never compromise these):**
1. Every claim is traceable to a source.
2. Every search is reproducible.
3. Every failure or missing value is explicit.

---

## Phase 1 — Reliability Foundation (Current focus)

### 1.1 Evidence Provenance Ledger (P0)
For every returned field record:
- source database
- PMID (or other identifier)
- retrieval timestamp
- status: `directly_sourced` | `transformed` | `unavailable` | `not_returned_by_ncbi` | `parse_error`
- optional: checksum of the raw response fragment, parser version

**Deliverable:** Extended normalized schema + `provenance` object on every record and every search.

### 1.2 Search Snapshots & Systematic-search Workspace (P0)
- Generate stable snapshot IDs: `PUBMED-YYYYMMDD-XXXXXX`
- Persist (in-memory for now, optional file later):
  - original query
  - NCBI translated query
  - date/language limits
  - result count
  - WebEnv / QueryKey when used
  - full list of retrieved PMIDs (or pagination state)
  - SHA-256 of the response payload
- New tools:
  - `pubmed_search_snapshot` (create)
  - `pubmed_list_snapshots` / `pubmed_get_snapshot`

### 1.3 Regression & Evaluation Foundation (P0)
- Fixed offline fixtures covering:
  - malformed queries
  - missing metadata
  - structured abstracts
  - retraction / erratum notices
  - duplicate identifiers
  - partial NCBI responses
- Metrics to track later: field-level accuracy, false inferences (must stay zero), reproducibility, latency.

---

## Phase 2 — Research Workflow

- RIS / BibTeX / CSV / JSON exports
- Search history export (PRISMA-ready)
- Reliable PMC full-text path + download audit trail

## Phase 3 — Structured Evidence Tables (source-linked only)

- Extract only what is explicitly present in retrieved text
- Every cell carries source location / quote + extraction status
- Distinguish `not reported` vs `not retrieved` vs `not applicable`

## Phase 4 — Differentiation

- Europe PMC adapter + careful deduplication
- Citation chasing (with coverage notes)
- Retraction / correction monitoring for saved libraries

## Explicitly out of scope for now

- Automatic GRADE or risk-of-bias judgements
- Unvalidated AI-generated study characteristics
- Claims of exhaustive systematic searching
- Complex web dashboard
- Large number of new MCP tools that increase complexity without improving auditability

---

## Success criteria for Phase 1

- [ ] Every normalized record carries a full provenance ledger entry per field
- [ ] Search snapshots can be created and retrieved with stable IDs
- [ ] Offline test suite still passes and grows with new fixtures
- [ ] No inference of missing data is introduced
- [ ] DEVELOPMENT_STATE.md and README accurately reflect the new surface