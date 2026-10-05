# pubmed-mcp

A minimal, auditable [Model Context Protocol](https://modelcontextprotocol.io) server for PubMed via NCBI E-utilities.
Built for evidence synthesis: the server returns only what NCBI returns, and flags everything else.

## Tools
| Tool | Purpose |
|---|---|
| `search_pubmed(query, max_results=20, sort="relevance", date_from=None, date_to=None)` | Returns PMIDs, `total_matches`, and `query_translation` (how PubMed parsed your query; log it in your methods). |
| `fetch_abstracts(pmids)` | Returns title, authors, journal, date, DOI, publication types, retraction-notice flag, abstract (section labels kept), URL, up to 200 PMIDs per call. |
| `search_with_access(query, max_results<=100, ...)` | search, then list each hit as open-access PDF / landing page only / no open access found / unchecked |
| `check_access(pmids)` | same classification for given PMIDs |
| `download_pdfs(pmids, folder=None)` | saves open-access PDFs as PMID<id>.pdf; paywalled papers are skipped, never bypassed |

## Guarantees
- Missing field => literal `Data not provided in PubMed abstract`. Nothing is inferred or paraphrased.
- Requested PMIDs that NCBI did not return are listed in `not_found`.
- `publication_types` is NCBI's own tag. **No evidence level (CEBM/GRADE) is assigned by the server**: abstracts alone are not enough to grade evidence.
- `has_retraction_notice` is true only if the record carries an NCBI "RetractionIn" link.
- Respects NCBI rate limits (3 req/s, 10 req/s with an API key) with retry/backoff.

## Open access and PDFs
Sources are Unpaywall (via DOI) and PubMed Central (via PMCID). Set `UNPAYWALL_EMAIL` or `NCBI_EMAIL`. `NO_OPEN_ACCESS_FOUND` means no legal free copy is indexed, not that an institution cannot reach it. Every file is checked to start with `%PDF` and bot-check pages are rejected. Files go to `PUBMED_PDF_DIR` (default `~/pubmed_pdfs`). No paywall bypass.

## Install
    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python tests/test_server.py                             # offline tests (synthetic fixture, no network)

Optional env: `NCBI_API_KEY` (free, raises rate limit), `NCBI_EMAIL` (NCBI usage policy asks for one), `NCBI_TOOL`.

## Register in Google Antigravity
Agent panel -> "..." -> MCP Servers -> Manage MCP Servers -> View raw config. Antigravity reads either
`~/.gemini/config/mcp_config.json` (global) or `.agents/mcp_config.json` (this workspace). Use ABSOLUTE paths:

    {"mcpServers": {"pubmed-scraper": {
      "command": "/abs/path/.venv/bin/python",
      "args": ["/abs/path/pubmed-mcp/server.py"],
      "env": {"NCBI_EMAIL": "you@example.com"}}}}

Put your real `NCBI_API_KEY` / email only in the GLOBAL config, never in a file you commit.
Other MCP clients (Claude Desktop, Claude Code, Cursor) use the same command/args pair.

## Limitations
- Abstract-level data only; no full text. Not a substitute for a full systematic-review search strategy across Embase, Cochrane, etc.
- Search quality depends on your query syntax (MeSH, field tags); PubMed may translate it unexpectedly, so check `query_translation`.
- Open-access coverage varies, and some publishers block automated downloads.
- Live NCBI, Unpaywall, and PDF download behaviour was not covered by automated tests (they use synthetic fixtures).

## License
Apache License 2.0, see `LICENSE`. Copyright [year] [your name].
