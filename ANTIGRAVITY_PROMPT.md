Read `mcp-instructions.md`. All code is already written; do NOT rewrite server.py. Do these steps in order and stop and report if any step fails:

1. Create a virtual environment `.venv`, run `pip install -r requirements.txt`, then run `python tests/test_server.py`. All 6 tests must print "ok". Show me the output.
2. Run `grep -rniE "api_key=|ghp_|github_pat_|password" .` and confirm no secrets exist in the repo.
3. Edit `.agents/mcp_config.json`: set "command" to the ABSOLUTE path of `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`) and the first "args" entry to the ABSOLUTE path of `server.py`. Leave NCBI_EMAIL as the placeholder; I will fill it in myself.
4. Fill the "Copyright [year] [name]" line in README.md only if I give you my name; otherwise leave it.
5. `git init`, commit everything, then create a PUBLIC GitHub repository named `pubmed-mcp` on my account using the GitHub MCP tool, and push. Do not push any file containing a key, token or personal email.
6. Reload MCP servers in Antigravity, list the tools of `pubmed-scraper`, then call `search_pubmed` with query `"hypertrophic cardiomyopathy"[MeSH] AND mavacamten[tiab]` and max_results 3, then `fetch_abstracts` on the returned PMIDs. Show me the raw tool output, unedited.
