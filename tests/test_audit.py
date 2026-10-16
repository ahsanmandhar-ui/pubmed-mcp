"""Offline tests for access / download audit helpers."""

from audit import make_access_audit, summarize_audit, STATUS_SUCCESS, STATUS_SKIPPED_PAYWALLED


def test_make_access_audit_shape():
    e = make_access_audit(
        "123",
        access_status="open_access_pdf",
        route="pmc",
        download_status=STATUS_SUCCESS,
        file_path="/tmp/123.pdf",
        checksum_sha256="abc",
    )
    assert e["pmid"] == "123"
    assert e["download_status"] == STATUS_SUCCESS
    assert e["checksum_sha256"] == "abc"


def test_summarize():
    entries = [
        make_access_audit("1", access_status="open_access_pdf", download_status=STATUS_SUCCESS),
        make_access_audit("2", access_status="no_open_access_found", download_status=STATUS_SKIPPED_PAYWALLED),
    ]
    summary = summarize_audit(entries)
    assert summary["total"] == 2
    assert summary["by_status"][STATUS_SUCCESS] == 1
    assert summary["by_status"][STATUS_SKIPPED_PAYWALLED] == 1