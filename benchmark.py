"""
Offline evaluation & regression benchmark for pubmed-mcp (Phase 5).

Purpose
-------
- Run synthetic fixtures through the record-normalization pipeline
- Detect any field that is marked `directly_sourced` but was NOT present in the source input
- Track `false_inference_count` — must stay 0 (the anti-inference guarantee)
- Provide regression detection: any change that introduces inference fails the benchmark

Anti-inference contract
-----------------------
- A field is only `directly_sourced` if the value came from the source input
- Never mark a field `directly_sourced` if it was inferred, guessed, or defaulted
- `false_inference_count` must never be > 0
- Absence of data is never evidence of absence
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Anti-inference counter — module level, must stay 0
# ---------------------------------------------------------------------------

false_inference_count = 0

# Fields that are structural/provenance metadata and should not be checked
# for source-fidelity (they describe the record itself, not the article content).
_PROVENANCE_FIELDS = {
    "source",
    "provenance",
    "europepmc_id",
}


def _is_provenance_field(field_name: str) -> bool:
    """Return True if a field is structural metadata rather than article content."""
    return field_name in _PROVENANCE_FIELDS or field_name.startswith("_")


def _extract_value(entry: Any) -> Any:
    """Extract the raw value from a provenance field entry or plain value."""
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _field_status(entry: Any) -> Optional[str]:
    """Return the status string of a provenance field entry, or None."""
    if isinstance(entry, dict):
        return entry.get("status")
    return None


def check_record_for_inference(
    record: Dict[str, Any],
    source_input: Dict[str, Any],
    *,
    record_name: str = "unnamed",
) -> List[Dict[str, Any]]:
    """
    Check a normalized record against its raw source input for inference violations.

    A violation occurs when a field is marked `directly_sourced` but its value
    is not present (or is None/empty) in the source input. Provenance/structural
    fields (e.g. `source`, `provenance`) are excluded.

    Returns a list of violation dicts, each with:
      - field: field name
      - value: the value that was incorrectly marked directly_sourced
      - reason: human-readable explanation
      - record_name: name of the fixture being checked
    """
    violations: List[Dict[str, Any]] = []

    for field_name, entry in record.items():
        if _is_provenance_field(field_name):
            continue

        status = _field_status(entry)
        if status != "directly_sourced":
            continue

        value = _extract_value(entry)
        # Skip MISSING/empty markers — those are not inferences
        if value is None or value == "" or value == "Data not provided in PubMed abstract":
            continue

        source_value = source_input.get(field_name)
        if source_value is None or source_value == "":
            violations.append({
                "record_name": record_name,
                "field": field_name,
                "value": value,
                "reason": (
                    f"field '{field_name}' marked directly_sourced "
                    f"but value {value!r} not present in source input"
                ),
            })

    return violations


def run_benchmark(
    fixtures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run the offline evaluation & regression benchmark.

    Each fixture is a dict with:
      - "name": str — fixture name
      - "record": dict — the normalized record (provenance-style entries)
      - "source_input": dict — the raw source data the record was derived from

    Returns a dict with:
      - false_inference_count: int (must be 0)
      - passed: bool (True if false_inference_count == 0)
      - total_fixtures: int
      - results: list of per-fixture result dicts
    """
    global false_inference_count
    false_inference_count = 0

    results: List[Dict[str, Any]] = []

    for fixture in fixtures:
        name = fixture.get("name", "unnamed")
        record = fixture.get("record", {})
        source_input = fixture.get("source_input", {})

        violations = check_record_for_inference(record, source_input, record_name=name)
        false_inference_count += len(violations)

        results.append({
            "name": name,
            "violation_count": len(violations),
            "violations": violations,
            "passed": len(violations) == 0,
        })

    return {
        "false_inference_count": false_inference_count,
        "passed": false_inference_count == 0,
        "total_fixtures": len(fixtures),
        "results": results,
    }


def validate_record(
    record: Dict[str, Any],
    source_input: Dict[str, Any],
    *,
    record_name: str = "unnamed",
) -> Dict[str, Any]:
    """
    Validate a single record for inference violations.

    This is the function exposed via the `pubmed_validate` MCP tool.

    Returns a dict with:
      - valid: bool (True if no inference violations)
      - false_inference_count: int
      - violations: list of violation dicts
      - record_name: str
    """
    violations = check_record_for_inference(record, source_input, record_name=record_name)
    return {
        "valid": len(violations) == 0,
        "false_inference_count": len(violations),
        "violations": violations,
        "record_name": record_name,
    }


# ---------------------------------------------------------------------------
# Default synthetic fixtures for offline regression testing
# ---------------------------------------------------------------------------

def default_fixtures() -> List[Dict[str, Any]]:
    """
    Return a default set of synthetic fixtures for offline benchmarking.

    Each fixture pairs a normalized record (provenance-style) with the raw
    source input it was derived from. Records that correctly mark only
    present fields as `directly_sourced` produce 0 violations.
    """
    from provenance import (
        field,
        STATUS_DIRECTLY_SOURCED,
        STATUS_NOT_RETURNED,
    )

    fixtures: List[Dict[str, Any]] = []

    # --- Fixture 1: fully populated record, all fields present in source ---
    source_1 = {
        "pmid": "12345678",
        "title": "A Synthetic Study",
        "authors": "Smith J; Doe A",
        "journal": "Journal of Synthetic Research",
        "pub_date": "2024",
        "doi": "10.1234/synthetic.2024",
        "pmcid": "PMC123456",
        "abstract": "This is a synthetic abstract for testing.",
    }
    record_1 = {
        "pmid": field("12345678", STATUS_DIRECTLY_SOURCED),
        "title": field("A Synthetic Study", STATUS_DIRECTLY_SOURCED),
        "authors": field("Smith J; Doe A", STATUS_DIRECTLY_SOURCED),
        "journal": field("Journal of Synthetic Research", STATUS_DIRECTLY_SOURCED),
        "pub_date": field("2024", STATUS_DIRECTLY_SOURCED),
        "doi": field("10.1234/synthetic.2024", STATUS_DIRECTLY_SOURCED),
        "pmcid": field("PMC123456", STATUS_DIRECTLY_SOURCED),
        "abstract": field("This is a synthetic abstract for testing.", STATUS_DIRECTLY_SOURCED),
        "source": "NCBI PubMed",
        "provenance": {"utility": "esearch", "timestamp": "2026-01-01T00:00:00+00:00"},
    }
    fixtures.append({
        "name": "fully_populated_record",
        "record": record_1,
        "source_input": source_1,
    })

    # --- Fixture 2: partially populated record, missing fields marked not_returned ---
    source_2 = {
        "pmid": "87654321",
        "title": "Partial Record",
        # authors, journal, doi, pmcid, abstract are absent from source
    }
    record_2 = {
        "pmid": field("87654321", STATUS_DIRECTLY_SOURCED),
        "title": field("Partial Record", STATUS_DIRECTLY_SOURCED),
        "authors": field(None, STATUS_NOT_RETURNED),
        "journal": field(None, STATUS_NOT_RETURNED),
        "pub_date": field(None, STATUS_NOT_RETURNED),
        "doi": field(None, STATUS_NOT_RETURNED),
        "pmcid": field(None, STATUS_NOT_RETURNED),
        "abstract": field(None, STATUS_NOT_RETURNED),
        "source": "NCBI PubMed",
        "provenance": {"utility": "esearch", "timestamp": "2026-01-01T00:00:00+00:00"},
    }
    fixtures.append({
        "name": "partial_record_missing_fields",
        "record": record_2,
        "source_input": source_2,
    })

    # --- Fixture 3: Europe PMC record with only some identifiers ---
    source_3 = {
        "pmid": "11223344",
        "title": "Europe PMC Synthetic",
        "doi": "10.5555/epmc.2024",
        # pmcid, abstract absent
    }
    record_3 = {
        "pmid": field("11223344", STATUS_DIRECTLY_SOURCED),
        "title": field("Europe PMC Synthetic", STATUS_DIRECTLY_SOURCED),
        "authors": field(None, STATUS_NOT_RETURNED),
        "journal": field(None, STATUS_NOT_RETURNED),
        "pub_date": field(None, STATUS_NOT_RETURNED),
        "doi": field("10.5555/epmc.2024", STATUS_DIRECTLY_SOURCED),
        "pmcid": field(None, STATUS_NOT_RETURNED),
        "abstract": field(None, STATUS_NOT_RETURNED),
        "source": "Europe PMC",
        "europepmc_id": "EPMC11223344",
        "provenance": {"utility": "europepmc_search", "timestamp": "2026-01-01T00:00:00+00:00"},
    }
    fixtures.append({
        "name": "europe_pmc_partial_record",
        "record": record_3,
        "source_input": source_3,
    })

    # --- Fixture 4: record with an intentional inference violation (for regression testing) ---
    # This fixture is designed to FAIL — it marks `doi` as directly_sourced when
    # the source input does not contain a doi. Used to verify the benchmark
    # actually catches inference violations.
    source_4 = {
        "pmid": "55667788",
        "title": "Violation Fixture",
        # doi is NOT in source_input
    }
    record_4 = {
        "pmid": field("55667788", STATUS_DIRECTLY_SOURCED),
        "title": field("Violation Fixture", STATUS_DIRECTLY_SOURCED),
        "doi": field("10.9999/inferred.doi", STATUS_DIRECTLY_SOURCED),  # VIOLATION: not in source
        "authors": field(None, STATUS_NOT_RETURNED),
        "journal": field(None, STATUS_NOT_RETURNED),
        "pub_date": field(None, STATUS_NOT_RETURNED),
        "pmcid": field(None, STATUS_NOT_RETURNED),
        "abstract": field(None, STATUS_NOT_RETURNED),
        "source": "NCBI PubMed",
        "provenance": {"utility": "esearch", "timestamp": "2026-01-01T00:00:00+00:00"},
    }
    fixtures.append({
        "name": "intentional_inference_violation",
        "record": record_4,
        "source_input": source_4,
        "expect_violation": True,
    })

    return fixtures


def run_default_benchmark() -> Dict[str, Any]:
    """
    Run the benchmark with the default synthetic fixtures.

    Note: The default fixtures include one intentional violation fixture
    (expect_violation=True) to verify detection works. That fixture is
    excluded from the false_inference_count assertion so the default
    run can still report passed=True when only legitimate fixtures pass.

    Returns the benchmark result dict.
    """
    fixtures = default_fixtures()

    # Separate legitimate fixtures from the intentional violation fixture
    legitimate = [f for f in fixtures if not f.get("expect_violation")]
    violation_fixtures = [f for f in fixtures if f.get("expect_violation")]

    # Run legitimate fixtures — these must produce 0 false inferences
    result = run_benchmark(legitimate)

    # Run the violation fixture separately to confirm detection works
    violation_result = None
    if violation_fixtures:
        violation_result = run_benchmark(violation_fixtures)

    # Combine results
    combined = {
        "false_inference_count": result["false_inference_count"],
        "passed": result["passed"],
        "total_fixtures": len(fixtures),
        "legitimate_fixtures": len(legitimate),
        "violation_fixtures": len(violation_fixtures),
        "results": result["results"],
    }
    if violation_result:
        combined["violation_detection"] = {
            "caught_violation": violation_result["false_inference_count"] > 0,
            "violation_count": violation_result["false_inference_count"],
        }

    return combined