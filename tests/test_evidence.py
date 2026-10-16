"""Offline tests for the structured evidence table builder."""

from evidence import (
    build_evidence_row,
    build_evidence_table,
    evidence_table_to_csv,
    STATUS_EXTRACTED,
    STATUS_NOT_REPORTED,
    STATUS_NOT_RETRIEVED,
)


RCT_ABSTRACT = {
    "pmid": "111",
    "title": "A randomized controlled trial of drug X versus placebo",
    "abstract": "BACKGROUND: We conducted an RCT. METHODS: We enrolled n = 240 patients. RESULTS: Something.",
    "publication_types": ["Randomized Controlled Trial", "Journal Article"],
    "has_retraction_notice": False,
}

NO_ABSTRACT = {
    "pmid": "222",
    "title": "Some observational paper",
    "abstract": "Data not provided in PubMed abstract",
    "publication_types": ["Journal Article"],
    "has_retraction_notice": False,
}


def test_rct_design_and_sample_size_extracted():
    row = build_evidence_row(RCT_ABSTRACT)
    assert row["study_design_hint"]["status"] == STATUS_EXTRACTED
    assert "randomized controlled trial" in row["study_design_hint"]["value"].lower()
    assert row["sample_size"]["status"] == STATUS_EXTRACTED
    assert row["sample_size"]["value"] == 240
    assert row["abstract_available"]["value"] is True


def test_no_abstract_marks_not_retrieved():
    row = build_evidence_row(NO_ABSTRACT)
    assert row["abstract_available"]["value"] is False
    assert row["population_hint"]["status"] == STATUS_NOT_RETRIEVED
    assert row["sample_size"]["status"] == STATUS_NOT_RETRIEVED


def test_table_and_csv():
    table = build_evidence_table([RCT_ABSTRACT, NO_ABSTRACT])
    assert table["row_count"] == 2
    csv_text = evidence_table_to_csv(table)
    assert "pmid,title" in csv_text
    assert "111" in csv_text
    assert "222" in csv_text


def test_never_invents_pico_when_absent():
    row = build_evidence_row(RCT_ABSTRACT)
    # We deliberately do not try to parse free-text PICO yet
    assert row["population_hint"]["status"] == STATUS_NOT_REPORTED
    assert row["intervention_hint"]["value"] is None