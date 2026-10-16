"""Offline tests for retraction monitoring helpers."""

from retraction import make_retraction_check_result, summarize_retraction_checks


def test_retraction_found():
    r = make_retraction_check_result("123", has_retraction_notice=True)
    assert r["status"] == "retraction_found"
    assert r["has_retraction_notice"] is True


def test_clean_record():
    r = make_retraction_check_result("456", has_retraction_notice=False)
    assert r["status"] == "no_notice_found"


def test_summary():
    results = [
        make_retraction_check_result("1", has_retraction_notice=True),
        make_retraction_check_result("2", has_retraction_notice=False),
        make_retraction_check_result("3", has_retraction_notice=False, has_erratum_notice=True),
    ]
    summary = summarize_retraction_checks(results)
    assert summary["total_checked"] == 3
    assert summary["by_status"]["retraction_found"] == 1
    assert summary["by_status"]["erratum_found"] == 1
    assert summary["by_status"]["no_notice_found"] == 1
