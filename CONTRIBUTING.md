# Contributing to pubmed-mcp

Thanks for helping improve pubmed-mcp. Here is how to contribute.

## How to contribute

1. Fork the repo and create a branch from `main`.
2. Make your change. Keep it small and reviewable.
3. Run the offline test suite: `python tests/test_server.py` and `python tests/test_access.py`.
4. Open a pull request describing what changed and why.

## Ground rules

- Do not change Python source files unless asked — the anti-inference guarantees must stay intact.
- Never commit API keys, emails, or secrets. Keep credentials in environment variables or your global MCP config.
- Bug reports and feature ideas are welcome as GitHub issues.

## License

By contributing, you agree your contributions will be licensed under the Apache License 2.0, the same license used by this project.
