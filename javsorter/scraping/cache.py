from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from javsorter.core.models import MetadataRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata_cache (
    content_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('ok', 'not_found')),
    json_blob TEXT,
    fetched_at TEXT NOT NULL
)
"""


class MetadataCache:
    """SQLite-backed cache keyed by content ID, so repeat scans skip the
    network entirely -- including for IDs that previously had no match.

    Opened with check_same_thread=False and guarded by a lock because the
    GUI creates one MetadataCache on the main thread but background
    QThread workers (MatchWorker) are the ones actually calling get/put.
    """

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def get(self, content_id: str) -> MetadataRecord | None:
        """Return the cached record for content_id, or None if there's no
        'ok' entry cached (either never fetched, or cached as not-found --
        use has_not_found() to tell those two apart).
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT json_blob FROM metadata_cache WHERE content_id = ? AND status = 'ok'",
                (content_id,),
            ).fetchone()
        if row is None:
            return None
        return MetadataRecord(**json.loads(row[0]))

    def has_not_found(self, content_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM metadata_cache WHERE content_id = ? AND status = 'not_found'",
                (content_id,),
            ).fetchone()
        return row is not None

    def put(self, content_id: str, record: MetadataRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO metadata_cache (content_id, status, json_blob, fetched_at) "
                "VALUES (?, 'ok', ?, ?)",
                (content_id, json.dumps(asdict(record)), _now()),
            )
            self._conn.commit()

    def put_not_found(self, content_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO metadata_cache (content_id, status, json_blob, fetched_at) "
                "VALUES (?, 'not_found', NULL, ?)",
                (content_id, _now()),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "MetadataCache":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
