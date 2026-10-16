"""
Search Snapshot store for pubmed-mcp (Phase 1).

In-memory by default. Designed so a later file- or SQLite-backed
implementation can replace the storage backend without changing the
public tool surface.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
import threading
from typing import Any, Dict, List, Optional


def _make_snapshot_id() -> str:
    """Generate PUBMED-YYYYMMDD-XXXXXX style identifier."""
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()  # 6 hex chars
    return f"PUBMED-{today}-{suffix}"


class SnapshotStore:
    """Thread-safe in-memory store of systematic-search snapshots."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: Dict[str, Dict[str, Any]] = {}

    def create(
        self,
        *,
        original_query: str,
        effective_query: str,
        total_matches: int,
        pmids: List[str],
        retmax: int,
        sort: str = "relevance",
        date_from: Optional[int] = None,
        date_to: Optional[int] = None,
        webenv: Optional[str] = None,
        query_key: Optional[str] = None,
        response_hash: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and store a new search snapshot. Returns the snapshot object."""
        snapshot_id = _make_snapshot_id()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        snap: Dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "created_at": now,
            "original_query": original_query,
            "effective_query": effective_query,
            "total_matches": total_matches,
            "returned_count": len(pmids),
            "pmids": list(pmids),
            "retmax": retmax,
            "sort": sort,
            "date_from": date_from,
            "date_to": date_to,
            "webenv": webenv,
            "query_key": query_key,
            "response_hash": response_hash,
        }
        if extra:
            snap["extra"] = extra

        with self._lock:
            self._store[snapshot_id] = snap
        return snap

    def get(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._store.get(snapshot_id)

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return most recent snapshots (newest first), truncated to limit."""
        with self._lock:
            items = sorted(
                self._store.values(),
                key=lambda s: s["created_at"],
                reverse=True,
            )
        return items[: max(1, min(limit, 200))]

    def delete(self, snapshot_id: str) -> bool:
        with self._lock:
            if snapshot_id in self._store:
                del self._store[snapshot_id]
                return True
            return False


# Module-level singleton used by the MCP tools
store = SnapshotStore()