# Cline — Implement Phase 5: Offline Evaluation & Regression Benchmark

Phase 5 adds an offline evaluation & regression benchmark to pubmed-mcp, guarding the anti-inference guarantee.

## Goal

Build a benchmark module that:
1. Runs synthetic fixtures through the server's record-normalization pipeline
2. Tracks `false_inference_count` — any instance where a field is marked `directly_sourced` but the value was not actually present in the source input
3. Asserts `false_inference_count == 0` (the anti-inference guarantee must hold)
4. Provides regression detection: any change that introduces inference fails the benchmark
5. Never weakens the anti-inference contract

## Deliverables

- `benchmark.py` — core benchmark module with `run_benchmark()` and module-level `false_inference_count`
- `tests/test_benchmark.py` — offline tests for the benchmark
- Register `pubmed_validate` tool in `server.py` (validates records for inference violations)
- Update `pyproject.toml` with `benchmark` module
- Update `ROADMAP.md` (Phase 5 section)
- Update `DEVELOPMENT_STATE.md` (new tool, module, tests)

## Anti-inference guarantee (non-negotiable)

- A field is only `directly_sourced` if the value came from the source input
- Never mark a field `directly_sourced` if it was inferred, guessed, or defaulted
- `false_inference_count` must stay 0 — never allow it to be > 0
- Absence of data is never evidence of absence

## Merge pattern

Feature branch → fast-forward merge → delete branch (no force-push), same as Phase 3 and Phase 4.

## Exact next task

1. Create branch `feature/phase5-benchmark` off `main`
2. Copy scaffolding modules from `phase5-scaffolding.zip` into repo root
3. Add tests `tests/test_benchmark.py` with imports matching flat-module convention (`from benchmark import ...`)
4. Update `server.py`: import benchmark, register `pubmed_validate` tool
5. Update `pyproject.toml`: add `benchmark` to `py-modules`
6. Update `ROADMAP.md` (Phase 4 → DONE, Phase 5 → CURRENT)
7. Update `DEVELOPMENT_STATE.md` (target tools, structure, test commands, Last Verified, Exact Next Task)
8. Create test runner and run full offline suite; confirm `false_inference_count == 0` and 0 failures
9. Commit Phase 5 changes on `feature/phase5-benchmark` and push to origin
10. Fast-forward merge into `main`; delete feature branch locally and remotely
11. Run full test suite on `main` to confirm green