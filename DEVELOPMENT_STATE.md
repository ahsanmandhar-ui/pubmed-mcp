# PubMed MCP Development State

## 1. Project Identity
- **Name:** pubmed-access-mcp (Repository: ahsanmandhar-ui/pubmed-mcp)
- **Repository:** https://github.com/ahsanmandhar-ui/pubmed-mcp
- **Purpose:** Minimal, auditable, provenance-first Model Context Protocol (MCP) server for PubMed via NCBI E-utilities, specifically optimized for evidence synthesis, systematic reviews, and reproducible medical/scientific research.
- **Current version:** 0.2.0
- **Schema version:** 1.0

## 2. Product Thesis
- **Core Principle:** NCBI → retrieval → deterministic normalization → provenance.
- **Strict Anti-Inference:** The server is a retrieval and normalization layer, NOT an AI inference agent. It never guesses or fills in missing metadata (no hallucinated DOIs, no inferred sample sizes, no guessed study types, no fabricated countries).
- **Authoritative Source:** NCBI PubMed is the single source of truth. No silent external enrichment (Crossref, OpenAlex, Semantic Scholar, etc.) unless an explicit modular layer is introduced in the future.
- **Auditability & Reproducibility:** Every retrieved record and search query includes machine-verifiable provenance and query translation, allowing researchers and systematic reviewers to audit exactly what NCBI returned.

## 3. Architecture
```
User / AI Client (Claude, Antigravity, Cursor, etc.)
  |
  | MCP Protocol (stdio / FastMCP)
  v
pubmed-mcp
  |
  +-- MCP Tool Layer (server.py)
  |     - Target Tools: pubmed_search, pubmed_get, pubmed_fetch,
  |       pubmed_batch_fetch, pubmed_validate, pubmed_search_audit, pubmed_database_info
  |     - Legacy Compatibility: search_pubmed, fetch_abstracts, check_access,
  |       search_with_access, download_pdfs
  |
  +-- NCBI Client Layer (ncbi_client.py)
  |     - Rate limiting (3 req/s anonymous, 10 req/s with key)
  |     - Exponential backoff & retry (429, 500, 502, 503, 504)
  |     - Structured error handling (invalid_input, ncbi_error, timeout, rate_limited)
  |     - Utilities: esearch, efetch, einfo, esummary
  |     - Entrez History support (WebEnv, QueryKey)
  |
  +-- Normalization Layer
  |     - Deterministic XML parsing of MedlineCitation & PubmedData
  |     - Source fidelity: raw text preserved without editorial alteration
  |
  +-- Provenance Layer (provenance.py)
  |     - Structured metadata: provider, database, utility, timestamp, request_parameters, server_version
  |     - Zero secret leakage (sanitizes API keys and authorization tokens)
  |
  +-- Missingness Layer
  |     - Distinguishes: available, missing, not_returned_by_ncbi, not_requested, not_applicable, parse_error
  |
  +-- Validation Layer
  |     - PMID regex/syntax, pagination ranges, sort criteria, parameter bounds
  |
  +-- Integrity / Hash Layer
  |     - SHA-256 integrity hashes for stored searches and raw responses
  |
  v
NCBI E-utilities (https://eutils.ncbi.nlm.nih.gov/entrez/eutils)
```

## 4. Repository Structure
```
.
├── .gitignore
├── DEVELOPMENT_STATE.md   # Persistent source of truth for engineering sessions
├── LICENSE                # Apache 2.0
├── README.md              # User-facing documentation and quick start
├── pyproject.toml         # PEP 621 metadata, entry point: pubmed-access-mcp = server:main
├── requirements.txt       # Dependencies: mcp, requests
├── smithery.yaml          # Smithery MCP registry manifest
├── access.py              # Open-access detection (Unpaywall + PubMed Central) & safe PDF downloads
├── server.py              # FastMCP server definition & tool entry points
├── tests/
│   ├── test_access.py     # Offline synthetic tests for access detection and PDF safety
│   └── test_server.py     # Offline synthetic tests for XML parsing and tool validation
```

## 5. MCP Surface

### Tools (Current)
1. `search_pubmed(query, max_results=20, sort="relevance", date_from=None, date_to=None)`:
   - Query PubMed using NCBI ESearch; returns PMIDs, count, and NCBI query_translation.
2. `fetch_abstracts(pmids)`:
   - Batch fetch (up to 200 PMIDs) using NCBI EFetch XML; returns title, authors, journal, pub_date, doi, pmcid, publication_types, retraction notice flag, abstract, url.
3. `check_access(pmids)`:
   - Classify access status (open_access_pdf, open_access_landing_page_only, no_open_access_found, unchecked) via Unpaywall & PMC.
4. `search_with_access(query, max_results=20, sort="relevance", date_from=None, date_to=None)`:
   - Composite search + access classification (capped at 100 PMIDs).
5. `download_pdfs(pmids, folder=None)`:
   - Download verified legal open-access PDFs with magic number check (`%PDF`) and path traversal protection.

### Target Tool Evolution (Roadmap)
1. `pubmed_search`: ESearch with full reproducibility object, query translation, and provenance.
2. `pubmed_get`: Retrieve single record by PMID with raw/normalized toggle.
3. `pubmed_fetch`: Batch retrieval with per-record status and provenance.
4. `pubmed_batch_fetch`: Entrez History-backed batch retrieval for large systematic review sets.
5. `pubmed_validate`: Offline and schema-level validation of PMIDs, query syntax, and record consistency.
6. `pubmed_search_audit`: Detailed analysis of query translation, MeSH terms, and search warnings.
7. `pubmed_database_info`: NCBI EInfo metadata (last update time, field tags, total database count).

### Resources
- Target: `pubmed://record/{pmid}`, `pubmed://search/{search_id}`

### Prompts
- None currently registered. Target prompts for systematic review PRISMA-compliant search documentation.

## 6. NCBI Integration
- **Endpoints Used:**
  - `esearch.fcgi`: Term searches, count retrieval, translation string, Entrez History creation.
  - `efetch.fcgi`: Bulk XML retrieval (`rettype=abstract`, `retmode=xml`).
  - `einfo.fcgi`: Database statistics and search field descriptions.
- **Parameters:**
  - `tool`: Set via `NCBI_TOOL` (default: `pubmed-mcp` or `pubmed-access-mcp`).
  - `email`: Set via `NCBI_EMAIL`.
  - `api_key`: Optional, read from `NCBI_API_KEY`.
- **Throttling:** Thread-safe locking: 3 requests/s without API key (340ms interval); 10 requests/s with API key (110ms interval).

## 7. Data Model
- **Record Fields (Normalized Mode):**
  - `pmid`: str (1-9 digits)
  - `title`: str
  - `authors`: list of str (or CollectiveName)
  - `journal`: str
  - `pub_date`: str (structured Year Month Day or MedlineDate)
  - `doi`: str or missingness indicator
  - `pmcid`: str or missingness indicator
  - `publication_types`: list of str
  - `has_retraction_notice`: bool (True only if `RetractionIn` link exists in comments/corrections)
  - `abstract`: str (structured sections preserve labels, e.g. `BACKGROUND: ...`)
  - `url`: str (canonical https://pubmed.ncbi.nlm.nih.gov/{pmid}/)
- **Raw Mode:** Preserves parsed XML node structure or raw XML text for auditability.

## 8. Missingness Semantics
- Traditional string sentinel: `"Data not provided in PubMed abstract"` (`s.MISSING`).
- Target structured vocabulary:
  - `available`: Field present with non-empty data from NCBI.
  - `missing`: Field explicitly omitted or blank in NCBI record.
  - `not_returned_by_ncbi`: Requested record/field was omitted from response payload.
  - `not_requested`: Field not included in requested projection.
  - `not_applicable`: Field not valid for this publication type.
  - `parse_error`: Field could not be parsed from XML structure.

## 9. Provenance
- Target response schema includes:
  ```json
  "provenance": {
    "provider": "NCBI PubMed",
    "database": "pubmed",
    "utility": "esearch",
    "timestamp": "2026-10-05T11:40:00Z",
    "request_parameters": {
      "db": "pubmed",
      "term": "neoplasm",
      "retmax": 20
    },
    "server_version": "0.2.0",
    "schema_version": "1.0"
  }
  ```
- **Security Rule:** Secret credentials (`api_key`, tokens) are stripped before generating provenance objects.

## 10. Search Reproducibility
- In evidence synthesis, PRISMA requires reporting the exact search string, date run, and results.
- PubMed silently expands queries via Automatic Term Mapping (ATM).
- The server captures and returns:
  - `query_submitted`: Original user query string.
  - `query_translation`: NCBI's translated query (MeSH terms, explosion, fields).
  - `total_matches`: Total matching records at execution timestamp.
  - `timestamp`: UTC execution time.

## 11. Rate Limiting
- Thread-safe monotonic clock throttle.
- Configurable backoff: exponential retry (1.5s, 3.0s, 4.5s, 6.0s) on HTTP 429 and 5xx errors.
- Max retries: 4 attempts before raising structured `NcbiError`.

## 12. Error Handling
- Structured categories:
  - `invalid_input`: Invalid PMIDs, bad date ranges, unsupported sort parameters.
  - `not_found`: PMIDs requested but absent from NCBI response.
  - `ncbi_error`: NCBI returned an XML/JSON error element or non-retryable HTTP code.
  - `rate_limited`: Persistent 429 response exceeding retry budget.
  - `timeout`: Request exceeded socket timeout (45s).
  - `parse_error`: Malformed XML from NCBI.
  - `partial_failure`: Some PMIDs succeeded, some failed.

## 13. Security
- Safe URL validation in `access.py`: Private IP ranges (RFC 1918, loopback, link-local, file://) are blocked to prevent SSRF.
- Path traversal defense: `access.target_dir` restricts downloads to configured folder and rejects relative `..` escapes.
- PDF magic number validation: Files must start with `%PDF` header; HTML bot-checks and login portals are rejected.
- Zero credential logging: API keys and PATs never written to stdout, logs, or response objects.

## 14. Testing
- Offline synthetic fixtures (`tests/test_server.py`, `tests/test_access.py`).
- No live network requests required for unit test pass.
- Tests cover:
  - Full record extraction and multi-author handling.
  - Missing field sentinel assertions.
  - Retraction notice detection (`RetractionIn`).
  - Input validation (PMID regex, injection defense).
  - Rate-limit placeholder key handling.
  - Open-access classification and PDF validation.
  - Path traversal and SSRF defenses.

## 15. Completed
- [x] Initial FastMCP server with `search_pubmed`, `fetch_abstracts`, `check_access`, `search_with_access`, `download_pdfs`.
- [x] Unpaywall and PMC open-access resolution.
- [x] Pure XML parser with synthetic tests.
- [x] Packaging for PyPI as `pubmed-access-mcp` v0.1.0.
- [x] Smithery manifest (`smithery.yaml`).
- [x] Decoupled NCBI HTTP, rate-limiting, and retry logic into dedicated `ncbi_client.py`.
- [x] Implemented `pubmed_database_info` tool querying NCBI EInfo with field tags and record counts.
- [x] Implemented `pubmed_search` with PRISMA-compliant reproducibility object (`database`, `original_query`, `effective_query`, `retstart`, `retmax`, `count`, `executed_at`), Entrez History tokens (`webenv`, `query_key`), and machine-verifiable provenance.
- [x] Implemented `pubmed_fetch` with explicit per-record status tracking (`success` vs `not_found`) and provenance.
- [x] Implemented `pubmed_get` (single PMID record retrieval) supporting `mode="normalized"` (clean deterministic schema with structured missingness indicators) and `mode="raw"` (verbatim XML with SHA-256 integrity hash).
- [x] Implemented `pubmed_batch_fetch` with multi-batch chunking (>200 PMIDs) and NCBI Entrez History pagination (`webenv`, `query_key`, `retstart`, `total_records`, `batch_size`), error resilience, per-record statuses, and audit provenance.
- [x] Structured missingness vocabulary: `available`, `missing`, `not_returned_by_ncbi`.
- [x] Errata (`has_erratum_notice`) and retraction (`has_retraction_notice`) notice tracking via `comments_corrections`.
- [x] Preserved 100% backward compatibility with legacy tool signatures and existing test suites.
- [x] Expanded offline test suite to 32 unit tests across `test_server.py`, `test_access.py`, and `test_client.py`.
- [x] Bumped package version to 0.2.0 (`pyproject.toml`, `ncbi_client.py`, `server.py`).

## 16. In Progress
- [ ] Search snapshot identifiers (`PUBMED-YYYYMMDD-XXXXXX`) and session preservation.

## 17. Remaining Roadmap
### P0 (Core Stability & Architecture) — COMPLETED
- [x] Separate NCBI client layer (`ncbi_client.py`) with clean session management and error typing.
- [x] Structured provenance generator in `ncbi_client.py`.
- [x] Implement `pubmed_database_info` and canonical `pubmed_search` with search reproducibility object.
- [x] Maintain 100% backward compatibility for existing tools and tests.
- [x] Implement `pubmed_get` (single PMID, raw XML vs. normalized mode, strict missingness indicators).
- [x] Implement `pubmed_batch_fetch` (multi-chunk PMID lists, Entrez History pagination, error resilience, provenance).

### P1 (Evidence Synthesis & History)
- [x] Entrez History support (`usehistory=y`, `WebEnv`, `QueryKey`) in `pubmed_batch_fetch` for multi-thousand PMID retrieval.
- [ ] Search snapshot identifiers (`PUBMED-YYYYMMDD-XXXXXX`) and SHA-256 response hashing.

### P2 (Exports & Validation)
- [ ] `pubmed_validate` tool (syntax, duplicate checking, MeSH validation).
- [ ] Standard bibliographic exports: RIS, BibTeX, CSV for Covidence / Rayyan import.
- [ ] MCP Resources (`pubmed://record/{pmid}`, `pubmed://search/{search_id}`).

## 18. Known Bugs
- None identified; all test suites passing offline.

## 19. Known Limitations
- Abstract-level data only; NCBI E-utilities does not return full text (unless PMCID is in open-access subset).
- Unpaywall lookup requires `UNPAYWALL_EMAIL` or `NCBI_EMAIL` to query their API.
- MCP server runs over stdio; HTTP/SSE transport required for cloud-hosted registry endpoints like Smithery.

## 20. Architectural Decisions
- **Decision:** Split package into decoupled layers: tool layer (`server.py`), client layer (`ncbi_client.py`), and access layer (`access.py`).
  - *Rationale:* Prevents HTTP request logic and XML parsing from tangling with MCP tool dispatch.
- **Decision:** Keep legacy tool names (`search_pubmed`, `fetch_abstracts`) alongside target names (`pubmed_get`, `pubmed_search`, `pubmed_fetch`, `pubmed_batch_fetch`, `pubmed_database_info`).
  - *Rationale:* Preserves backward compatibility for existing scripts, clients, and test fixtures.
- **Decision:** Strict non-inference rule.
  - *Rationale:* Medical research and evidence synthesis demand 100% source fidelity; AI hallucinations must not enter citation graphs.
- **Decision:** In `pubmed_get`, wrap missing fields in `{ "value": ..., "status": ... }` objects.
  - *Rationale:* Clearly distinguishes between fields NCBI didn't return (e.g. DOI) versus fields that were empty in the abstract.
- **Decision:** `pubmed_batch_fetch` partial failure tolerance.
  - *Rationale:* In systematic reviews retrieving hundreds or thousands of citations, a transient failure on a single batch chunk must not discard already retrieved batches.

## 21. Rejected Approaches
- **Rejected:** Inferred metadata / LLM-based abstract completion.
  - *Why:* Violates core scientific auditability; dangerous in systematic reviews.
- **Rejected:** Silent multi-source enrichment from Crossref/Semantic Scholar inside the core server.
  - *Why:* Obscures provenance; makes it impossible to know if an author or date was reported by NCBI or an external aggregator.
- **Rejected:** Bypassing publisher paywalls.
  - *Why:* Legal compliance; only open-access repositories (PMC, Unpaywall gold/green) are indexed and fetched.

## 22. Environment Variables
- `NCBI_API_KEY`: Optional; raises NCBI rate limit from 3 req/s to 10 req/s.
- `NCBI_EMAIL`: Recommended by NCBI E-utilities usage guidelines.
- `NCBI_TOOL`: Optional identifier sent in NCBI requests (defaults to `pubmed-access-mcp`).
- `UNPAYWALL_EMAIL`: Required for Unpaywall DOI queries (falls back to `NCBI_EMAIL`).
- `PUBMED_PDF_DIR`: Target directory for PDF downloads (defaults to `~/pubmed_pdfs`).

## 23. How to Run
```bash
# Direct execution (stdio MCP transport)
pubmed-access-mcp

# Or via uvx without installation
uvx pubmed-access-mcp

# Development mode
.venv/Scripts/python server.py
```

## 24. How to Test
```bash
# Run unit tests offline
.venv/Scripts/python tests/test_server.py
.venv/Scripts/python tests/test_access.py
.venv/Scripts/python tests/test_client.py

# Or via unittest discovery
.venv/Scripts/python -m unittest discover tests
```

## 25. Last Verified
- **Date:** 2026-10-05
- **Git commit:** Working tree updated
- **Tests:** 32 passed, 0 failed (offline synthetic test suite across all 3 test modules)
- **Build:** Built successfully (wheel and sdist for pubmed-access-mcp 0.2.0)
- **Lint:** Clean syntax
- **Typecheck:** Clean execution
- **Files Changed in Session:**
  - `server.py` (Implemented pubmed_batch_fetch tool, exposed SERVER_VERSION)
  - `ncbi_client.py` (Bumped SERVER_VERSION to 0.2.0, made pmids optional in efetch)
  - `pyproject.toml` (Bumped version to 0.2.0)
  - `README.md` (Documented pubmed_batch_fetch in tools table)
  - `DEVELOPMENT_STATE.md` (Updated completed items, roadmap, test counts, version 0.2.0)
  - `tests/test_client.py` (Added TestPubmedBatchFetch with 6 new tests covering chunking, history pagination, missing IDs, error resilience, and validation)

## 26. EXACT NEXT TASK
1. Finalize PyPI release for `pubmed-access-mcp` v0.2.0.
2. Implement search snapshot identifiers (`PUBMED-YYYYMMDD-XXXXXX`) and session preservation.
3. Implement `pubmed_validate` tool (syntax, duplicate checking, MeSH validation).

## 27. SESSION HANDOFF
Next agent should:
Review `DEVELOPMENT_STATE.md`, inspect Section 26, and proceed with snapshot identifiers and export utilities (P1/P2 roadmap).
