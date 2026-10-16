# CLINE_PUSH_EXAMPLES — Example Documentation Push Convention

This file documents the convention for adding example documentation to the
`examples/` directory and referencing it from `README.md`.

## Purpose

Example files under `examples/` provide runnable, copy-pasteable snippets that
show how to use pubmed-mcp for real workflows (systematic reviews, live smoke
tests, access audits, snapshots, exports). Every example must:

1. Be self-contained (no secrets, no real API keys, no emails).
2. Use placeholder values (`you@example.com`, `your-key`) for any credential.
3. Reference only tools and constants that exist in `server.py`.
4. Declare the anti-inference guarantee where records are fetched.

## Naming convention

Files are `UPPER_SNAKE_CASE.md`, e.g.:
- `SYSTEMATIC_REVIEW_EXAMPLE.md`
- `LIVE_SMOKE_EXAMPLE.md`

## README linkage

Add a short "Examples" section to `README.md` that links to each example file
with a one-line description. Keep it brief; examples live in `examples/`.

## Commit message format

`docs: add <example-name> and <example-name> examples`

Merge to `main` and push to `origin/main`.

## Secret hygiene

Before committing, grep the staged diff for:
- `@` in email-like positions
- `sk-`, `pk-`, `NCBI_API_KEY=`, `UNPAYWALL_EMAIL=` with real values
- Any token longer than 20 random-looking characters

If found, replace with placeholders before committing.