"""Offline tests. The XML below is a SYNTHETIC fixture shaped like NCBI's PubmedArticleSet (not a real record)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server as s

XML = """<?xml version="1.0"?><PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID Version="1">111</PMID><Article>
 <Journal><JournalIssue><PubDate><Year>2024</Year><Month>Mar</Month></PubDate></JournalIssue><Title>Synthetic Journal</Title></Journal>
 <ArticleTitle>A <i>synthetic</i> trial of X.</ArticleTitle>
 <Abstract><AbstractText Label="BACKGROUND">Bg text.</AbstractText><AbstractText Label="RESULTS">n = 10; p &lt; 0.05.</AbstractText></Abstract>
 <AuthorList><Author><LastName>Doe</LastName><ForeName>Jane</ForeName></Author><Author><CollectiveName>Test Group</CollectiveName></Author></AuthorList>
 <PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList>
</Article><CommentsCorrectionsList><CommentsCorrections RefType="RetractionIn"><PMID>999</PMID></CommentsCorrections></CommentsCorrectionsList></MedlineCitation>
<PubmedData><ArticleIdList><ArticleId IdType="pubmed">111</ArticleId><ArticleId IdType="doi">10.0000/synthetic</ArticleId></ArticleIdList></PubmedData></PubmedArticle>
<PubmedArticle><MedlineCitation><PMID Version="1">222</PMID><Article>
 <Journal><JournalIssue><PubDate><MedlineDate>2020 Jan-Feb</MedlineDate></PubDate></JournalIssue><Title>Other Journal</Title></Journal>
 <ArticleTitle>No abstract record.</ArticleTitle></Article></MedlineCitation><PubmedData/></PubmedArticle>
</PubmedArticleSet>"""

def test_full_record():
    out = s.parse_efetch(XML, ["111", "222", "333"])
    r = out["records"][0]
    assert r["title"] == "A synthetic trial of X."
    assert r["abstract"] == "BACKGROUND: Bg text.\nRESULTS: n = 10; p < 0.05."
    assert r["authors"] == ["Doe Jane", "Test Group"]
    assert r["doi"] == "10.0000/synthetic" and r["pub_date"] == "2024 Mar"
    assert r["publication_types"] == ["Randomized Controlled Trial"]
    assert r["has_retraction_notice"] is True

def test_missing_fields_are_flagged_not_invented():
    r = s.parse_efetch(XML, ["222"])["records"][1]
    for k in ("abstract", "authors", "doi", "publication_types"):
        assert r[k] == s.MISSING, k
    assert r["pub_date"] == "2020 Jan-Feb" and r["has_retraction_notice"] is False

def test_not_found_reported():
    assert s.parse_efetch(XML, ["111", "222", "333"])["not_found"] == ["333"]

def test_input_validation(monkeypatch=None):
    for bad in (["abc"], [], ["1; DROP"], ["1" * 12]):
        try: s.fetch_abstracts(bad)
        except ValueError: continue
        raise AssertionError(bad)

def test_search_uses_ncbi_fields_only():
    class R:  # stand-in for the HTTP response
        def json(self): return {"esearchresult": {"count": "57", "idlist": ["1", "2"], "querytranslation": "x[All Fields]"}}
    s._request = lambda *a, **k: R()
    out = s.search_pubmed("x", max_results=999)
    assert out["total_matches"] == 57 and out["pmids"] == ["1", "2"] and out["max_results_applied"] == 200

def test_placeholder_key_ignored():
    os.environ["NCBI_API_KEY"] = "YOUR_OPTIONAL_FREE_KEY"
    assert s._env("NCBI_API_KEY") is None

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("ok", n)
