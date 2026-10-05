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
        self.assertEqual(prov["server_version"], "0.2.0")
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


class TestPubmedGet(unittest.TestCase):
    STANDARD_XML = (
        '<?xml version="1.0"?><PubmedArticleSet>'
        '<PubmedArticle><MedlineCitation><PMID>2001</PMID><Article>'
        '<Journal><JournalIssue><PubDate><Year>2024</Year><Month>Aug</Month></PubDate></JournalIssue><Title>Cardio Journal</Title></Journal>'
        '<ArticleTitle>Cardiomyopathy trial results</ArticleTitle>'
        '<Abstract><AbstractText Label="AIM">Evaluate therapy.</AbstractText><AbstractText Label="CONCLUSION">Therapy effective.</AbstractText></Abstract>'
        '<AuthorList><Author><LastName>Smith</LastName><ForeName>Alice</ForeName></Author></AuthorList>'
        '<PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>'
        '</Article></MedlineCitation>'
        '<PubmedData><ArticleIdList><ArticleId IdType="doi">10.1016/cardio.2024.01</ArticleId><ArticleId IdType="pmc">PMC8888</ArticleId></ArticleIdList></PubmedData>'
        '</PubmedArticle>'
        '</PubmedArticleSet>'
    )

    MISSING_FIELDS_XML = (
        '<?xml version="1.0"?><PubmedArticleSet>'
        '<PubmedArticle><MedlineCitation><PMID>2002</PMID><Article>'
        '<ArticleTitle>Brief note without abstract</ArticleTitle>'
        '</Article></MedlineCitation><PubmedData/></PubmedArticle>'
        '</PubmedArticleSet>'
    )

    ERRATA_RETRACTION_XML = (
        '<?xml version="1.0"?><PubmedArticleSet>'
        '<PubmedArticle><MedlineCitation><PMID>2003</PMID><Article>'
        '<ArticleTitle>Study under revision</ArticleTitle>'
        '</Article>'
        '<CommentsCorrectionsList>'
        '<CommentsCorrections RefType="ErratumIn"><PMID>3001</PMID><Note>Dose correction</Note></CommentsCorrections>'
        '<CommentsCorrections RefType="RetractionIn"><PMID>3002</PMID><Note>Data discrepancy</Note></CommentsCorrections>'
        '</CommentsCorrectionsList>'
        '</MedlineCitation><PubmedData/></PubmedArticle>'
        '</PubmedArticleSet>'
    )

    def test_pubmed_get_normalized_standard(self):
        mock_resp = MagicMock(status_code=200, text=self.STANDARD_XML)
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_get("2001", mode="normalized")
            self.assertEqual(res["status"], "found")
            self.assertEqual(res["pmid"], "2001")
            self.assertEqual(res["mode"], "normalized")
            self.assertIn("integrity", res)
            self.assertEqual(res["integrity"]["algorithm"], "sha256")

            rec = res["record"]
            self.assertEqual(rec["title"]["status"], "available")
            self.assertEqual(rec["title"]["value"], "Cardiomyopathy trial results")
            self.assertEqual(rec["abstract"]["status"], "available")
            self.assertEqual(rec["abstract"]["value"], "AIM: Evaluate therapy.\nCONCLUSION: Therapy effective.")
            self.assertEqual(rec["doi"]["status"], "available")
            self.assertEqual(rec["doi"]["value"], "10.1016/cardio.2024.01")
            self.assertEqual(rec["pmcid"]["status"], "available")
            self.assertEqual(rec["pmcid"]["value"], "PMC8888")
            self.assertEqual(rec["publication_types"]["status"], "available")
            self.assertEqual(rec["publication_types"]["value"], ["Randomized Controlled Trial"])
            self.assertFalse(rec["has_retraction_notice"])
            self.assertFalse(rec["has_erratum_notice"])
            self.assertEqual(res["provenance"]["utility"], "efetch")

    def test_pubmed_get_missing_doi_and_abstract(self):
        mock_resp = MagicMock(status_code=200, text=self.MISSING_FIELDS_XML)
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_get("2002", mode="normalized")
            rec = res["record"]
            self.assertEqual(rec["doi"]["status"], "not_returned_by_ncbi")
            self.assertIsNone(rec["doi"]["value"])
            self.assertEqual(rec["pmcid"]["status"], "not_returned_by_ncbi")
            self.assertIsNone(rec["pmcid"]["value"])
            self.assertEqual(rec["abstract"]["status"], "missing")
            self.assertIsNone(rec["abstract"]["value"])
            self.assertEqual(rec["publication_types"]["status"], "not_returned_by_ncbi")
            self.assertEqual(rec["publication_types"]["value"], [])
            self.assertEqual(rec["authors"]["status"], "missing")
            self.assertEqual(rec["authors"]["value"], [])

    def test_pubmed_get_errata_and_retractions(self):
        mock_resp = MagicMock(status_code=200, text=self.ERRATA_RETRACTION_XML)
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_get("2003", mode="normalized")
            rec = res["record"]
            self.assertTrue(rec["has_retraction_notice"])
            self.assertTrue(rec["has_erratum_notice"])
            self.assertEqual(len(rec["comments_corrections"]), 2)
            types = [c["ref_type"] for c in rec["comments_corrections"]]
            self.assertIn("ErratumIn", types)
            self.assertIn("RetractionIn", types)

    def test_pubmed_get_raw_mode(self):
        mock_resp = MagicMock(status_code=200, text=self.STANDARD_XML)
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_get("2001", mode="raw")
            self.assertEqual(res["status"], "found")
            self.assertEqual(res["mode"], "raw")
            self.assertIn("<PubmedArticle>", res["raw_xml"])
            self.assertIn("<PMID>2001</PMID>", res["raw_xml"])
            self.assertEqual(res["integrity"]["algorithm"], "sha256")
            self.assertEqual(len(res["integrity"]["response_hash"]), 64)

    def test_pubmed_get_not_found(self):
        mock_resp = MagicMock(status_code=200, text='<?xml version="1.0"?><PubmedArticleSet></PubmedArticleSet>')
        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_get("99999", mode="normalized")
            self.assertEqual(res["status"], "not_found")
            self.assertIsNone(res["record"])
            self.assertEqual(res["pmid"], "99999")

    def test_pubmed_get_validation(self):
        with self.assertRaises(ValueError):
            s.pubmed_get("abc")
        with self.assertRaises(ValueError):
            s.pubmed_get("123; DROP TABLE")
        with self.assertRaises(ValueError):
            s.pubmed_get("123", mode="invalid_mode")


class TestPubmedBatchFetch(unittest.TestCase):
    def setUp(self):
        # Disable sleep/throttle during tests for maximum test execution speed
        self.throttle_patcher = patch.object(s, "_throttle", return_value=None)
        self.throttle_patcher.start()

    def tearDown(self):
        self.throttle_patcher.stop()

    @staticmethod
    def _make_xml_for_pmids(pmids):
        articles = []
        for p in pmids:
            articles.append(
                f'<PubmedArticle><MedlineCitation><PMID>{p}</PMID><Article>'
                f'<ArticleTitle>Title for {p}</ArticleTitle>'
                f'</Article></MedlineCitation></PubmedArticle>'
            )
        return f'<?xml version="1.0"?><PubmedArticleSet>{"".join(articles)}</PubmedArticleSet>'

    def test_multi_batch_chunking_long_pmid_list(self):
        # 250 PMIDs with batch_size=200 -> 2 batches (200 + 50)
        pmid_list = [str(10000 + i) for i in range(250)]

        def mock_request(endpoint, params, method="GET"):
            self.assertEqual(endpoint, "efetch.fcgi")
            self.assertEqual(method, "POST")
            chunk_ids = params["id"].split(",")
            mock_resp = MagicMock(status_code=200)
            mock_resp.text = self._make_xml_for_pmids(chunk_ids)
            return mock_resp

        with patch.object(s, "_request", side_effect=mock_request):
            res = s.pubmed_batch_fetch(pmids=pmid_list, batch_size=200)
            self.assertEqual(res["mode"], "pmids")
            self.assertEqual(res["total_requested"], 250)
            self.assertEqual(res["total_returned"], 250)
            self.assertEqual(res["batches_executed"], 2)
            self.assertEqual(res["batches_successful"], 2)
            self.assertEqual(res["batches_failed"], 0)
            self.assertEqual(len(res["records"]), 250)
            self.assertEqual(len(res["batches"]), 2)
            self.assertEqual(res["batches"][0]["requested"], 200)
            self.assertEqual(res["batches"][0]["returned"], 200)
            self.assertEqual(res["batches"][0]["retstart"], 0)
            self.assertEqual(res["batches"][1]["requested"], 50)
            self.assertEqual(res["batches"][1]["returned"], 50)
            self.assertEqual(res["batches"][1]["retstart"], 200)
            self.assertEqual(res["not_found"], [])
            self.assertEqual(res["provenance"]["utility"], "efetch_batch")
            self.assertEqual(res["provenance"]["request_parameters"]["total_requested"], 250)
            # Ensure every record has status == 'success'
            self.assertTrue(all(r["status"] == "success" for r in res["records"]))

    def test_entrez_history_retrieval_with_pagination(self):
        # WebEnv and query_key with retstart=10, total_records=5, batch_size=2 -> 3 batches (2, 2, 1)
        calls = []

        def mock_request(endpoint, params, method="GET"):
            self.assertEqual(endpoint, "efetch.fcgi")
            self.assertEqual(params["WebEnv"], "MCID_history_test")
            self.assertEqual(params["query_key"], "2")
            retstart = params["retstart"]
            retmax = params["retmax"]
            calls.append((retstart, retmax))
            chunk_pmids = [str(5000 + retstart + i) for i in range(retmax)]
            mock_resp = MagicMock(status_code=200)
            mock_resp.text = self._make_xml_for_pmids(chunk_pmids)
            return mock_resp

        with patch.object(s, "_request", side_effect=mock_request):
            res = s.pubmed_batch_fetch(
                webenv="MCID_history_test",
                query_key="2",
                retstart=10,
                total_records=5,
                batch_size=2,
            )
            self.assertEqual(res["mode"], "entrez_history")
            self.assertEqual(res["total_requested"], 5)
            self.assertEqual(res["total_returned"], 5)
            self.assertEqual(res["batches_executed"], 3)
            self.assertEqual(res["batches_successful"], 3)
            self.assertEqual(res["batches_failed"], 0)
            self.assertEqual(len(res["records"]), 5)
            self.assertEqual(calls, [(10, 2), (12, 2), (14, 1)])
            self.assertEqual(res["batches"][0]["retstart"], 10)
            self.assertEqual(res["batches"][1]["retstart"], 12)
            self.assertEqual(res["batches"][2]["retstart"], 14)
            self.assertTrue(all(r["status"] == "success" for r in res["records"]))
            self.assertEqual(res["records"][0]["pmid"], "5010")
            self.assertEqual(res["records"][4]["pmid"], "5014")

    def test_entrez_history_without_total_records_queries_count(self):
        # When total_records is None, queries esearch to get count then fetches
        def mock_request(endpoint, params, method="GET"):
            mock_resp = MagicMock(status_code=200)
            if endpoint == "esearch.fcgi":
                mock_resp.json.return_value = {
                    "esearchresult": {"count": "3", "webenv": params["WebEnv"], "querykey": params["query_key"]}
                }
                return mock_resp
            elif endpoint == "efetch.fcgi":
                retstart = params["retstart"]
                retmax = params["retmax"]
                chunk_pmids = [str(7000 + retstart + i) for i in range(retmax)]
                mock_resp.text = self._make_xml_for_pmids(chunk_pmids)
                return mock_resp
            raise ValueError(f"Unexpected endpoint {endpoint}")

        with patch.object(s, "_request", side_effect=mock_request):
            res = s.pubmed_batch_fetch(
                webenv="MCID_count_test",
                query_key="1",
                batch_size=10,
            )
            self.assertEqual(res["mode"], "entrez_history")
            self.assertEqual(res["total_requested"], 3)
            self.assertEqual(res["total_returned"], 3)
            self.assertEqual(res["batches_executed"], 1)
            self.assertEqual(res["batches_successful"], 1)
            self.assertEqual(len(res["records"]), 3)

    def test_partial_batch_missing_ids_handling(self):
        # 3 PMIDs requested, only 2 exist in XML -> 1 missing
        requested_ids = ["101", "102", "999"]
        mock_resp = MagicMock(status_code=200)
        mock_resp.text = self._make_xml_for_pmids(["101", "102"])

        with patch.object(s, "_request", return_value=mock_resp):
            res = s.pubmed_batch_fetch(pmids=requested_ids, batch_size=10)
            self.assertEqual(res["total_requested"], 3)
            self.assertEqual(res["total_returned"], 2)
            self.assertEqual(res["not_found"], ["999"])
            self.assertEqual(res["batches"][0]["status"], "partial_success")
            self.assertEqual(res["batches"][0]["not_found"], ["999"])

            # Verify results_summary contains per-record success vs not_found status
            statuses = {item["pmid"]: item["status"] for item in res["results_summary"]}
            self.assertEqual(statuses["101"], "success")
            self.assertEqual(statuses["102"], "success")
            self.assertEqual(statuses["999"], "not_found")

    def test_batch_error_resilience(self):
        # 4 PMIDs across 2 batches of 2. Batch 1 succeeds, Batch 2 fails with network exception.
        def mock_request(endpoint, params, method="GET"):
            chunk_ids = params["id"].split(",")
            if "300" in chunk_ids:
                raise RuntimeError("503 Service Unavailable")
            mock_resp = MagicMock(status_code=200)
            mock_resp.text = self._make_xml_for_pmids(chunk_ids)
            return mock_resp

        with patch.object(s, "_request", side_effect=mock_request):
            res = s.pubmed_batch_fetch(pmids=["100", "200", "300", "400"], batch_size=2)
            # Batch 1 succeeded, Batch 2 failed without crashing
            self.assertEqual(res["batches_executed"], 2)
            self.assertEqual(res["batches_successful"], 1)
            self.assertEqual(res["batches_failed"], 1)
            self.assertEqual(res["batches"][0]["status"], "success")
            self.assertEqual(res["batches"][1]["status"], "failed")
            self.assertIn("503 Service Unavailable", res["batches"][1]["error"])
            self.assertEqual(res["total_returned"], 2)
            self.assertEqual(len(res["records"]), 2)
            self.assertEqual(res["records"][0]["pmid"], "100")
            self.assertEqual(res["records"][1]["pmid"], "200")
            self.assertEqual(res["not_found"], ["300", "400"])

    def test_parameter_validation(self):
        # Missing both pmids and history
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch()
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(pmids=[])
        # Incomplete history tokens
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(webenv="MCID_env")
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(query_key="1")
        # Invalid PMID syntax
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(pmids=["invalid_pmid"])
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(pmids=["100", "200; DROP TABLE"])
        # Invalid batch_size
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(pmids=["100"], batch_size=0)
        with self.assertRaises(ValueError):
            s.pubmed_batch_fetch(pmids=["100"], batch_size=-10)


if __name__ == "__main__":
    unittest.main()
