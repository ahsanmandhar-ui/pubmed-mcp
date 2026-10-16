"""Offline tests for bibliographic exporters."""

from export import to_ris, to_bibtex, to_csv, to_json


SAMPLE = [
    {
        "pmid": "12345678",
        "title": "A test paper about nothing",
        "authors": ["Smith J", "Doe A"],
        "journal": "Journal of Testing",
        "pub_date": "2024 Jan",
        "doi": "10.1234/test.5678",
        "pmcid": "PMC9999999",
        "publication_types": ["Journal Article"],
        "has_retraction_notice": False,
        "abstract": "BACKGROUND: Something. METHODS: Nothing.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    }
]


def test_ris_contains_pmid_and_title():
    text = to_ris(SAMPLE)
    assert "PMID- 12345678" in text
    assert "TI  - A test paper about nothing" in text
    assert "TY  - JOUR" in text
    assert "ER  -" in text


def test_bibtex_key_and_fields():
    text = to_bibtex(SAMPLE)
    assert "@article{" in text
    assert "title = {A test paper about nothing}" in text
    assert "pmid = {12345678}" in text


def test_csv_header_and_row():
    text = to_csv(SAMPLE)
    assert "pmid,title,authors" in text
    assert "12345678" in text
    assert "Smith J; Doe A" in text


def test_json_roundtrip():
    text = to_json(SAMPLE)
    assert '"pmid": "12345678"' in text
    assert "A test paper about nothing" in text