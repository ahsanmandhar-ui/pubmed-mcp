"""Offline tests for ncbi_client.py and enhanced provenance/reproducibility tools."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ncbi_client
from ncbi_client import NcbiClient, InvalidInputError, RateLimitError, NcbiError
import server as s


class TestNcbiClient(unittest.TestCase):
    def setUp(self):
        self.client = NcbiClient(base_url="https://mock.ncbi.nlm.nih.gov")

    def test_env_strips_placeholders(self):
        with patch.dict(os.environ, {"NCBI_API_KEY": "YOUR_KEY_HERE"}):
            self.assertIsNone(NcbiClient.env("NCBI_API_KEY"))

        with patch.dict(os.environ, {"NCBI_API_KEY": "${NCBI_API_KEY}"}):
            self.assertIsNone(NcbiClient.env("NCBI_API_KEY"))

        with patch.dict(os.environ, {"NCBI_API_KEY": "valid_key_123"}):
            self.assertEqual(NcbiClient.env("NCBI_API_KEY"), "valid_key_123")

    def test_sanitize_params_never_leaks_secrets(self):
        params = {
            "db": "pubmed",
            "term": "oncology",
            "api_key": "super_secret_ncbi_key",
            "token": "secret_bearer_token",
            "retmax": 20,
        }
        sanitized = self.client.sanitize_params(params)
        self.assertNotIn("api_key", sanitized)
        self.assertNotIn("token", sanitized)
        self.assertEqual(sanitized["term"], "oncology")
        self.assertEqual(sanitized["retmax"], 20)

    def test_provenance_structure(self):
        prov = self.client.build_provenance("esearch", {"db": "pubmed", "term": "trial", "api_key": "secret"})
        self.assertEqual(prov["provider"], "NCBI PubMed")
        self.assertEqual(prov["database"], "pubmed")
        self.assertEqual(prov["utility"], "esearch")
        self.assertEqual(prov["server_version"], "0.1.0")
        self.assertEqual(prov["schema_version"], "1.0")
        self.assertIn("timestamp", prov)
        self.assertNotIn("api_key", prov["request_parameters"])

    def test_compute_hash(self):
        res = NcbiClient.compute_hash("pubmed evidence record")
        self.assertEqual(res["algorithm"], "sha256")
        self.assertEqual(len(res["response_hash"]), 64)

    def test_invalid_search_input(self):
        with self.assertRaises(InvalidInputError):
            self.client.esearch(term="   ")


class TestTargetTools(unittest.TestCase):
    def test_pubmed_database_info(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "einforesult": {
                "dbinfo": {
                    "dbname": "pubmed",
                    "menuname": "PubMed",
                    "description": "PubMed bibliographic record",
                    "count": "38000000",
                    "lastupdate": "2026/10/05 02:00",
                    "fieldlist": [
                        {"name": "ALL", "fullname": "All Fields", "description": "All terms in record"},
                        {"name": "TITL", "fullname": "Title", "description": "Words in title"},
                    ],
                }
            }
        }
        with patch.object(s, "_request", return_value=mock_resp):
            info = s.pubmed_database_info("pubmed")
            self.assertEqual(info["database"], "pubmed")
            self.assertEqual(info["record_count"], 38000000)
            self.assertEqual(info["field_count"], 2)
            self.assertEqual(info["fields"][0]["name"], "ALL")
            self.assertEqual(info["provenance"]["utility"], "einfo")
            self.assertEqual(info["provenance"]["provider"], "NCBI PubMed")

    def test_pubmed_search_reproducibility(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "esearchresult": {
                "count": "42",
                "retmax": "10",
                "retstart": "0",
                "idlist": ["101", "102"],
                "querytranslation": "neoplasm[MeSH Terms]",
                "webenv": "MCID_12345",
                "querykey": "1",
            }
        }
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_search("cancer", max_results=10, use_history=True)
            self.assertEqual(res["pmids"], ["101", "102"])
            self.assertEqual(res["webenv"], "MCID_12345")
            self.assertEqual(res["query_key"], "1")
            # Verify reproducibility block
            search_block = res["search"]
            self.assertEqual(search_block["original_query"], "cancer")
            self.assertEqual(search_block["effective_query"], "neoplasm[MeSH Terms]")
            self.assertEqual(search_block["count"], 42)
            self.assertEqual(search_block["retmax"], 10)
            self.assertIn("executed_at", search_block)
            self.assertEqual(res["provenance"]["utility"], "esearch")

    def test_pubmed_fetch_per_record_status(self):
        xml_fixture = (
            '<?xml version="1.0"?><PubmedArticleSet>'
            '<PubmedArticle><MedlineCitation><PMID>101</PMID><Article>'
            '<ArticleTitle>Test 101</ArticleTitle></Article></MedlineCitation></PubmedArticle>'
            '</PubmedArticleSet>'
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = xml_fixture
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_fetch(["101", "999"])
            self.assertEqual(res["requested"], 2)
            self.assertEqual(res["returned"], 1)
            self.assertEqual(res["not_found"], ["999"])
            # Verify explicit per-record status
            self.assertEqual(res["records"][0]["status"], "success")
            self.assertEqual(res["records"][0]["pmid"], "101")
            self.assertEqual(res["results_summary"][1]["status"], "not_found")
            self.assertEqual(res["results_summary"][1]["pmid"], "999")
            self.assertEqual(res["provenance"]["utility"], "efetch")


if __name__ == "__main__":
    unittest.main()
