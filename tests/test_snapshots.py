"""Offline unit tests for the search snapshot store (Phase 1).

Run with:  python -m unittest discover tests
           or:  python -m pytest tests/test_snapshots.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from snapshots import SnapshotStore  # noqa: E402


class TestSnapshotStore(unittest.TestCase):
    def test_create_and_get(self):
        store = SnapshotStore()
        snap = store.create(
            original_query="test[ti]",
            effective_query="test[Title]",
            total_matches=42,
            pmids=["1", "2", "3"],
            retmax=20,
        )
        self.assertTrue(snap["snapshot_id"].startswith("PUBMED-"))
        self.assertEqual(len(snap["snapshot_id"].split("-")), 3)

        got = store.get(snap["snapshot_id"])
        self.assertIsNotNone(got)
        self.assertEqual(got["total_matches"], 42)
        self.assertEqual(got["pmids"], ["1", "2", "3"])
        self.assertEqual(got["original_query"], "test[ti]")
        self.assertEqual(got["effective_query"], "test[Title]")

    def test_list_order_newest_first(self):
        store = SnapshotStore()
        s1 = store.create(
            original_query="a", effective_query="a", total_matches=1, pmids=[], retmax=10
        )
        s2 = store.create(
            original_query="b", effective_query="b", total_matches=2, pmids=[], retmax=10
        )
        items = store.list(limit=10)
        self.assertEqual(items[0]["snapshot_id"], s2["snapshot_id"])
        self.assertEqual(items[1]["snapshot_id"], s1["snapshot_id"])

    def test_list_respects_limit(self):
        store = SnapshotStore()
        for i in range(5):
            store.create(
                original_query=f"q{i}",
                effective_query=f"q{i}",
                total_matches=i,
                pmids=[],
                retmax=10,
            )
        items = store.list(limit=2)
        self.assertEqual(len(items), 2)

    def test_missing_snapshot(self):
        store = SnapshotStore()
        self.assertIsNone(store.get("PUBMED-20990101-DEADBE"))


if __name__ == "__main__":
    unittest.main()
