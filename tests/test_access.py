"""Offline tests for access.py. All HTTP responses and records below are SYNTHETIC stand-ins, not real data."""
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import access as a
import server as s

M = a.MISSING

class Resp:
    def __init__(self, status=200, js=None, chunks=(), headers=None):
        self.status_code, self._js, self._chunks, self.headers = status, js, chunks, headers or {}
    def json(self): return self._js
    def iter_content(self, n): return iter(self._chunks)
    def close(self): pass

def rec(pmid, doi=M, pmcid=M): return {"pmid": pmid, "title": f"T{pmid}", "pub_date": "2024", "doi": doi, "pmcid": pmcid, "has_retraction_notice": False}

UNPAYWALL = {
    "10.1/oa":  {"is_oa": True, "oa_status": "gold", "best_oa_location": {"url_for_pdf": "https://pub.example/a.pdf", "url": "https://pub.example/a", "host_type": "publisher", "license": "cc-by", "version": "publishedVersion"}, "oa_locations": []},
    "10.1/land": {"is_oa": True, "oa_status": "green", "best_oa_location": {"url_for_pdf": None, "url": "https://repo.example/rec/1", "host_type": "repository"}, "oa_locations": []},
    "10.1/closed": {"is_oa": False, "oa_status": "closed", "best_oa_location": None, "oa_locations": []},
}
def fake_unpaywall(url, params=None, **k):
    doi = url.split("/v2/")[1]
    return Resp(200, UNPAYWALL[doi]) if doi in UNPAYWALL else Resp(404)

def test_classification():
    r = {x["pmid"]: x for x in a.check_records(
        [rec("1", "10.1/oa"), rec("2", "10.1/land"), rec("3", "10.1/closed"), rec("4"), rec("5", pmcid="PMC99"), rec("6", "10.1/nope")],
        "me@example.org", fake_unpaywall, delay=0)}
    assert r["1"]["access"] == a.OPEN_PDF and r["1"]["pdf_candidates"][0]["url"] == "https://pub.example/a.pdf"
    assert r["2"]["access"] == a.OPEN_LANDING and r["2"]["landing_url"] == "https://repo.example/rec/1"
    assert r["3"]["access"] == a.NO_OA and "institution" in r["3"]["note"]
    assert r["4"]["access"] == a.UNCHECKED and "No DOI or PMCID" in r["4"]["note"]
    assert r["5"]["access"] == a.OPEN_PDF and r["5"]["pdf_candidates"][0]["source"] == "PubMed Central"
    assert r["6"]["access"] == a.UNCHECKED and "not found" in r["6"]["note"]

def test_no_email_degrades_honestly():
    r = a.classify(rec("7", "10.1/oa"), None, fake_unpaywall)
    assert r["access"] == a.UNCHECKED and "UNPAYWALL_EMAIL" in r["note"]

def test_summary_groups():
    sm = a.summarize(a.check_records([rec("1", "10.1/oa"), rec("3", "10.1/closed")], "me@example.org", fake_unpaywall, delay=0))
    assert sm["counts"][a.OPEN_PDF] == 1 and sm["counts"][a.NO_OA] == 1
    assert sm["open_access_pdf"][0]["pdf_url"] == "https://pub.example/a.pdf"
    assert sm["no_open_access_found"][0]["pmid"] == "3"

def test_pmcid_parsed_from_pubmed_xml():
    xml = ('<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>5</PMID><Article><ArticleTitle>x</ArticleTitle></Article></MedlineCitation>'
           '<PubmedData><ArticleIdList><ArticleId IdType="pmc">PMC123</ArticleId></ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>')
    assert s.parse_efetch(xml, ["5"])["records"][0]["pmcid"] == "PMC123"

def test_download_validates_pdf_and_folder_rules():
    d = Path(tempfile.mkdtemp())
    res = [a.classify(rec("1", "10.1/oa"), "me@example.org", fake_unpaywall)]
    ok = lambda url, **k: Resp(200, chunks=[b"%PDF-1.7 ...", b"more"])
    row = a.download_many(res, d, ok, delay=0)[0]
    assert row["status"] == "downloaded" and (d / "PMID1.pdf").read_bytes().startswith(b"%PDF")
    assert a.download_many(res, d, ok, delay=0)[0]["status"] == "already_exists"
    d2 = Path(tempfile.mkdtemp())
    html = lambda url, **k: Resp(200, chunks=[b"<html>bot check</html>"])
    row = a.download_many(res, d2, html, delay=0)[0]
    assert row["status"] == "failed" and "not a PDF" in row["reason"][0] and not list(d2.iterdir())
    skipped = a.download_many([a.classify(rec("3", "10.1/closed"), "me@example.org", fake_unpaywall)], d2, ok, delay=0)[0]
    assert skipped["status"] == "skipped"
    try: a.target_dir("../escape"); raise AssertionError("traversal allowed")
    except ValueError: pass

def test_unsafe_urls_rejected():
    for u in ("file:///etc/passwd", "http://127.0.0.1/x.pdf", "http://localhost/x", "ftp://x/y.pdf", "http://192.168.1.5/a.pdf"):
        assert not a._safe_url(u), u
    assert a._safe_url("https://example.org/a.pdf")

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f(); print("ok", n)
