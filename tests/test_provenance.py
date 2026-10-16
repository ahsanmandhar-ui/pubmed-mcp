"""Offline unit tests for the evidence provenance ledger helpers (Phase 1).

Run with:  python -m unittest discover tests
           or:  python -m pytest tests/test_provenance.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from provenance import (  # noqa: E402
    field,
    make_record_provenance,
    sanitize_params,
    STATUS_DIRECTLY_SOURCED,
    STATUS_NOT_RETURNED,
    STATUS_UNAVAILABLE,
)


class TestProvenanceField(unittest.TestCase):
    def test_field_directly_sourced(self):
        f = field("Hello", STATUS_DIRECTLY_SOURCED, pmid="123")
        self.assertEqual(f["value"], "Hello")
        self.assertEqual(f["status"], STATUS_DIRECTLY_SOURCED)
        self.assertEqual(f["pmid"], "123")
        self.assertEqual(f["source"], "NCBI PubMed")
        self.assertIn("retrieved_at", f)

    def test_field_rejects_bad_status(self):
        with self.assertRaises(ValueError):
            field("x", "invented_status")

    def test_field_omits_optional_pmid_and_note(self):
        f = field(None, STATUS_NOT_RETURNED)
        self.assertNotIn("pmid", f)
        self.assertNotIn("note", f)
        self.assertEqual(f["value"], None)

    def test_sanitize_removes_secrets(self):
        raw = {"term": "cancer", "api_key": "secret", "token": "abc", "retmax": 20}
        clean = sanitize_params(raw)
        self.assertNotIn("api_key", clean)
        self.assertNotIn("token", clean)
        self.assertEqual(clean["term"], "cancer")
        self.assertEqual(clean["retmax"], 20)

    def test_record_provenance_shape(self):
        p = make_record_provenance(utility="efetch", pmid="999", response_hash="abc")
        self.assertEqual(p["provider"], "NCBI PubMed")
        self.assertEqual(p["database"], "pubmed")
        self.assertEqual(p["utility"], "efetch")
        self.assertEqual(p["response_hash"], {"algorithm": "sha256", "value": "abc"})
        self.assertEqual(p["schema_version"], "1.1")
        self.assertEqual(p["server_version"], "0.3.1")


if __name__ == "__main__":
    unittest.main()
