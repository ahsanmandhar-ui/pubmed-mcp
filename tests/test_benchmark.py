"""Offline tests for the Phase 5 evaluation & regression benchmark."""

from benchmark import (
    check_record_for_inference,
    run_benchmark,
    run_default_benchmark,
    validate_record,
    false_inference_count,
)
from provenance import field, STATUS_DIRECTLY_SOURCED, STATUS_NOT_RETURNED


def test_fully_populated_record_no_violations():
    source = {
        "pmid": "12345678",
        "title": "A Synthetic Study",
        "authors": "Smith J; Doe A",
        "doi": "10.1234/synthetic.2024",
    }
    record = {
        "pmid": field("12345678", STATUS_DIRECTLY_SOURCED),
        "title": field("A Synthetic Study", STATUS_DIRECTLY_SOURCED),
        "authors": field("Smith J; Doe A", STATUS_DIRECTLY_SOURCED),
        "doi": field("10.1234/synthetic.2024", STATUS_DIRECTLY_SOURCED),
        "source": "NCBI PubMed",
    }
    violations = check_record_for_inference(record, source, record_name="test1")
    assert violations == []


def test_missing_fields_marked_not_returned_no_violations():
    source = {
        "pmid": "87654321",
        "title": "Partial Record",
    }
    record = {
        "pmid": field("87654321", STATUS_DIRECTLY_SOURCED),
        "title": field("Partial Record", STATUS_DIRECTLY_SOURCED),
        "authors": field(None, STATUS_NOT_RETURNED),
        "journal": field(None, STATUS_NOT_RETURNED),
        "doi": field(None, STATUS_NOT_RETURNED),
        "source": "NCBI PubMed",
    }
    violations = check_record_for_inference(record, source, record_name="test2")
    assert violations == []


def test_provenance_fields_excluded():
    source = {"pmid": "111", "title": "X"}
    record = {
        "pmid": field("111", STATUS_DIRECTLY_SOURCED),
        "title": field("X", STATUS_DIRECTLY_SOURCED),
        "source": "NCBI PubMed",
        "provenance": {"utility": "esearch"},
    }
    violations = check_record_for_inference(record, source, record_name="test3")
    assert violations == []


def test_inference_violation_detected():
    source = {
        "pmid": "55667788",
        "title": "Violation Fixture",
    }
    record = {
        "pmid": field("55667788", STATUS_DIRECTLY_SOURCED),
        "title": field("Violation Fixture", STATUS_DIRECTLY_SOURCED),
        "doi": field("10.9999/inferred.doi", STATUS_DIRECTLY_SOURCED),
        "source": "NCBI PubMed",
    }
    violations = check_record_for_inference(record, source, record_name="test4")
    assert len(violations) == 1
    assert violations[0]["field"] == "doi"
    assert violations[0]["value"] == "10.9999/inferred.doi"


def test_empty_value_not_violation():
    source = {"pmid": "222", "title": "Y"}
    record = {
        "pmid": field("222", STATUS_DIRECTLY_SOURCED),
        "title": field("Y", STATUS_DIRECTLY_SOURCED),
        "doi": field(None, STATUS_NOT_RETURNED),
        "source": "NCBI PubMed",
    }
    violations = check_record_for_inference(record, source, record_name="test5")
    assert violations == []


def test_run_benchmark_legitimate_fixtures_pass():
    fixtures = [
        {
            "name": "fixture_a",
            "record": {
                "pmid": field("111", STATUS_DIRECTLY_SOURCED),
                "title": field("Title A", STATUS_DIRECTLY_SOURCED),
                "source": "NCBI PubMed",
            },
            "source_input": {"pmid": "111", "title": "Title A"},
        },
        {
            "name": "fixture_b",
            "record": {
                "pmid": field("222", STATUS_DIRECTLY_SOURCED),
                "title": field("Title B", STATUS_DIRECTLY_SOURCED),
                "authors": field(None, STATUS_NOT_RETURNED),
                "source": "NCBI PubMed",
            },
            "source_input": {"pmid": "222", "title": "Title B"},
        },
    ]
    result = run_benchmark(fixtures)
    assert result["passed"] is True
    assert result["false_inference_count"] == 0
    assert result["total_fixtures"] == 2


def test_run_benchmark_violation_fixture_fails():
    fixtures = [
        {
            "name": "bad_fixture",
            "record": {
                "pmid": field("333", STATUS_DIRECTLY_SOURCED),
                "doi": field("10.0/inferred", STATUS_DIRECTLY_SOURCED),
                "source": "NCBI PubMed",
            },
            "source_input": {"pmid": "333"},
        },
    ]
    result = run_benchmark(fixtures)
    assert result["passed"] is False
    assert result["false_inference_count"] == 1


def test_validate_record_valid():
    out = validate_record(
        {"pmid": field("1", STATUS_DIRECTLY_SOURCED), "source": "NCBI PubMed"},
        {"pmid": "1"},
        record_name="rec1",
    )
    assert out["valid"] is True
    assert out["false_inference_count"] == 0
    assert out["record_name"] == "rec1"


def test_validate_record_invalid():
    out = validate_record(
        {
            "pmid": field("1", STATUS_DIRECTLY_SOURCED),
            "doi": field("10.0/inferred", STATUS_DIRECTLY_SOURCED),
            "source": "NCBI PubMed",
        },
        {"pmid": "1"},
        record_name="rec2",
    )
    assert out["valid"] is False
    assert out["false_inference_count"] == 1
    assert out["violations"][0]["field"] == "doi"


def test_run_default_benchmark_passed():
    result = run_default_benchmark()
    assert result["passed"] is True
    assert result["false_inference_count"] == 0
    assert result["legitimate_fixtures"] == 3
    assert result["violation_fixtures"] == 1
    assert result["violation_detection"]["caught_violation"] is True


def test_false_inference_count_is_zero():
    run_default_benchmark()
    assert false_inference_count == 0