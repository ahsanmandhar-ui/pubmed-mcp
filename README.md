# pubmed-mcp

A minimal, auditable [Model Context Protocol](https://modelcontextprotocol.io) server for PubMed via NCBI E-utilities.
Built for evidence synthesis: the server returns only what NCBI returns, and flags everything else.

## Quick install

    pip install pubmed-access-mcp

Or run without installing:

    uvx pubmed-access-mcp

## Tools

### Provenance-First & Systematic Review Tools
| Tool | Purpose |
|---|---|
| `pubmed_get(pmid, mode="normalized")` | Retrieve a single record by PMID. In `normalized` mode, returns deterministic schema with structured missingness indicators (`available`, `missing`, `not_returned_by_ncbi`) and errata/retraction notices. In `raw` mode, returns verbatim NCBI XML with SHA-256 integrity hash. |
| `pubmed_search(query, max_results=20, start=0, sort="relevance", date_from=None, date_to=None, use_history=False)` | Search PubMed with a PRISMA-compliant reproducibility object (`original_query`, `effective_query`, `count`, `executed_at`), Entrez History tokens (`webenv`, `query_key`), and machine-verifiable provenance. |
| `pubmed_fetch(pmids)` | Bulk-fetch PubMed records with audit provenance and explicit per-record status tracking (`success` vs `not_found`). |
| `pubmed_batch_fetch(pmids=None, webenv=None, query_key=None, retstart=0, total_records=None, batch_size=200)` | Entrez History & large-scale batch retrieval. Supports slicing arbitrary length PMID lists or iterating Entrez History tokens across multiple rate-limited chunks with machine-verifiable audit provenance, error resilience, and explicit per-record statuses. |
| `pubmed_database_info(db="pubmed")` | Query NCBI EInfo for database statistics (total records, last update timestamp) and search field tag definitions. |


### Access & Retrieval Tools
| Tool | Purpose |
|---|---|
| `search_pubmed(...)` | Legacy/minimal search; returns PMIDs, `total_matches`, and `query_translation`. |
| `fetch_abstracts(pmids)` | Returns title, authors, journal, date, DOI, PMCID, publication types, retraction-notice flag, abstract (section labels kept), URL, up to 200 PMIDs per call. |
| `search_with_access(query, max_results<=100, ...)` | Search, then list each hit as open-access PDF / landing page only / no open access found / unchecked. |
| `check_access(pmids)` | Same classification for given PMIDs via Unpaywall & PubMed Central. |
| `download_pdfs(pmids, folder=None)` | Saves open-access PDFs as PMID<id>.pdf; paywalled papers are skipped, never bypassed. |


## Guarantees
- Missing field => literal `Data not provided in PubMed abstract`. Nothing is inferred or paraphrased.
- Requested PMIDs that NCBI did not return are listed in `not_found`.
- `publication_types` is NCBI's own tag. **No evidence level (CEBM/GRADE) is assigned by the server**: abstracts alone are not enough to grade evidence.
- `has_retraction_notice` is true only if the record carries an NCBI "RetractionIn" link.
- Respects NCBI rate limits (3 req/s, 10 req/s with an API key) with retry/backoff.

## Open access and PDFs
Sources are Unpaywall (via DOI) and PubMed Central (via PMCID). Set `UNPAYWALL_EMAIL` or `NCBI_EMAIL`. `NO_OPEN_ACCESS_FOUND` means no legal free copy is indexed, not that an institution cannot reach it. Every file is checked to start with `%PDF` and bot-check pages are rejected. Files go to `PUBMED_PDF_DIR` (default `~/pubmed_pdfs`). No paywall bypass.

## Register in your MCP client

### After `pip install pubmed-access-mcp`
Add to your MCP client config (Claude Desktop, Antigravity, Cursor, etc.):

    {"mcpServers": {"pubmed-scraper": {
      "command": "pubmed-access-mcp",
      "args": [],
      "env": {"NCBI_EMAIL": "you@example.com", "UNPAYWALL_EMAIL": "you@example.com"}}}}

### With `uvx` (no install needed)

    {"mcpServers": {"pubmed-scraper": {
      "command": "uvx",
      "args": ["pubmed-access-mcp"],
      "env": {"NCBI_EMAIL": "you@example.com", "UNPAYWALL_EMAIL": "you@example.com"}}}}

### In OpenCode

OpenCode uses `opencode.json` (per project) or `~/.config/opencode/opencode.jsonc` (global). Note that OpenCode uses `type: "local"` and a single command array:

#### With `uvx`
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "pubmed-scraper": {
      "type": "local",
      "command": ["uvx", "pubmed-access-mcp"],
      "environment": {
        "NCBI_EMAIL": "you@example.com",
        "UNPAYWALL_EMAIL": "you@example.com"
      }
    }
  }
}
```

#### From source or local virtualenv
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "pubmed-scraper": {
      "type": "local",
      "command": [
        "/path/to/.venv/bin/python",
        "/path/to/server.py"
      ],
      "environment": {
        "NCBI_EMAIL": "you@example.com",
        "UNPAYWALL_EMAIL": "you@example.com"
      }
    }
  }
}
```
*(On Windows, escape path backslashes e.g. `C:\\path\\to\\.venv\\Scripts\\python.exe`)*

#### Via OpenCode CLI
```bash
opencode mcp add pubmed-scraper --env NCBI_EMAIL=you@example.com --env UNPAYWALL_EMAIL=you@example.com -- uvx pubmed-access-mcp
```

Verify in OpenCode:
```bash
opencode mcp list
```

### From source (development)

    git clone https://github.com/ahsanmandhar-ui/pubmed-mcp.git
    cd pubmed-mcp
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

Then point your MCP config to the absolute path of `.venv/bin/python` (or `.venv\Scripts\python.exe`) and `server.py`.

Optional env: `NCBI_API_KEY` (free, raises rate limit), `NCBI_EMAIL` (NCBI usage policy asks for one), `NCBI_TOOL`.

Put your real `NCBI_API_KEY` / email only in your GLOBAL config, never in a file you commit.

## Install (for development / running tests)
    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python tests/test_server.py                             # offline tests (synthetic fixture, no network)
    python tests/test_access.py                             # offline open-access tests

## Host on Google Cloud Run (remote MCP)

Cloud Run's free tier covers up to **2 million requests/month** with scale-to-zero (no cost when idle).

### Prerequisites
1. Install [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
2. Authenticate: `gcloud auth login`
3. Create or select a project: `gcloud config set project YOUR_PROJECT_ID`
4. Enable billing (free tier covers most usage)

### One-command deploy
```bash
# Set your NCBI credentials as env vars first
export NCBI_EMAIL="you@example.com"
export UNPAYWALL_EMAIL="you@example.com"
export NCBI_API_KEY="your-key"       # optional, raises rate limit

# Deploy (defaults to us-central1)
chmod +x deploy.sh
./deploy.sh

# Or specify project and region explicitly
./deploy.sh my-gcp-project us-east1
```

The script will:
1. Enable Cloud Run & Artifact Registry APIs
2. Build the container image via Cloud Build
3. Deploy with scale 0→3, 512 MB RAM, 300 s timeout
4. Print the service URL and ready-to-paste MCP configs

### Manual deploy (step by step)
```bash
PROJECT_ID="your-project-id"
REGION="us-central1"

# Build
gcloud builds submit --tag gcr.io/$PROJECT_ID/pubmed-mcp

# Deploy
gcloud run deploy pubmed-mcp \
  --image gcr.io/$PROJECT_ID/pubmed-mcp \
  --region $REGION \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --min-instances 0 --max-instances 3 \
  --set-env-vars "MCP_TRANSPORT=streamable-http,NCBI_EMAIL=you@example.com"
```

### Connect MCP clients to the remote server

After deployment, your MCP endpoint will be:
```
https://pubmed-mcp-HASH-REGION.a.run.app/mcp
```

#### Claude Desktop / Cursor / Antigravity
```json
{"mcpServers": {"pubmed-scraper": {
  "url": "https://pubmed-mcp-HASH-REGION.a.run.app/mcp"
}}}
```

#### OpenCode
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "pubmed-scraper": {
      "type": "remote",
      "url": "https://pubmed-mcp-HASH-REGION.a.run.app/mcp"
    }
  }
}
```

#### Test the live endpoint
```bash
curl -X POST https://pubmed-mcp-HASH-REGION.a.run.app/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

### Environment variables for Cloud Run

| Variable | Required | Description |
|---|---|---|
| `MCP_TRANSPORT` | Set by Dockerfile | `streamable-http` (do not change) |
| `PORT` | Set by Cloud Run | Container port (do not change) |
| `NCBI_EMAIL` | Recommended | NCBI usage policy asks for one |
| `NCBI_API_KEY` | Optional | Free key, raises rate limit 3→10 req/s |
| `UNPAYWALL_EMAIL` | Optional | Enables open-access detection via Unpaywall |

## Limitations
- Abstract-level data only; no full text. Not a substitute for a full systematic-review search strategy across Embase, Cochrane, etc.
- Search quality depends on your query syntax (MeSH, field tags); PubMed may translate it unexpectedly, so check `query_translation`.
- Open-access coverage varies, and some publishers block automated downloads.
- Live NCBI, Unpaywall, and PDF download behaviour was not covered by automated tests (they use synthetic fixtures).

## License
Apache License 2.0, see `LICENSE`. Copyright 2024 ahsanmandhar-ui.
