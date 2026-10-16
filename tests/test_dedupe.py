"""Offline tests for cross-source deduplication."""

from dedupe import deduplicate


def test_exact_pmid_dedupe():
    records = [
        {"pmid": "111", "title": "Paper A", "doi": "10.1/a"},
        {"pmid": "111", "title": "Paper A duplicate", "doi": "10.1/a"},
        {"pmid": "222", "title": "Paper B"},
    ]
    result = deduplicate(records)
    assert result["unique_count"] == 2
    assert result["duplicates_removed"] == 1
    assert any(m["matched_on"] == "pmid" for m in result["match_log"])


def test_doi_dedupe():
    records = [
        {"pmid": "111", "doi": "10.1234/Test"},
        {"pmid": "999", "doi": "https://doi.org/10.1234/test"},  # same DOI, different PMID
    ]
    result = deduplicate(records)
    assert result["unique_count"] == 1
    assert result["duplicates_removed"] == 1
    assert result["match_log"][0]["matched_on"] == "doi"


def test_no_false_merge_on_title_alone():
    records = [
        {"pmid": "1", "title": "Common title words here", "authors": "Smith J", "pub_date": "2020"},
        {"pmid": "2", "title": "Common title words here", "authors": "Jones A", "pub_date": "2021"},
    ]
    result = deduplicate(records)
    # different author + year → both kept
    assert result["unique_count"] == 2
