# Objective
Finish, verify, publish and register an open-source PubMed MCP server (NCBI E-utilities). All code already exists in this folder.

# Hard constraints (do not change)
- Tools: `search_pubmed(query, max_results, sort, date_from, date_to)` and `fetch_abstracts(pmids)`.
- Never infer or fill missing data: absent fields stay the literal string "Data not provided in PubMed abstract".
- No evidence-level (CEBM) grading inside the server: it returns `publication_types` verbatim; grading is a human/LLM step on full text.
- stdout is reserved for the MCP protocol (log to stderr only).
- Never write a real API key, token or email into any file inside this repo.

# Files
server.py, requirements.txt, tests/test_server.py, README.md, LICENSE (Apache-2.0), .gitignore, .agents/mcp_config.json
