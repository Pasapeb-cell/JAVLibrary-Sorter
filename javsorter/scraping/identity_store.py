"""Authoritative persistence for manual actress decisions."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from javsorter.core.actress_identity import (
    ActressAliasOverride,
    ActressDecision,
    DecisionKind,
    canonical_release_key,
    normalize_actress_names,
)


class DecisionStoreUnavailable(RuntimeError):
    """A decision store cannot safely be read or written."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS release_decisions (
    release_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('correction', 'fallback')),
    actresses_json TEXT NOT NULL,
    stable_ids_json TEXT NOT NULL,
    captured_r18_json TEXT NOT NULL,
    snapshot_revision TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS identity_aliases (
    stable_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    snapshot_revision TEXT,
    updated_at TEXT NOT NULL
);
"""
_SCHEMA_VERSION = "1"


class IdentityDecisionStore:
    """A small transactional SQLite store separate from metadata/cache data.

    Unlike the disposable metadata cache, corruption is fail-closed.  The
    application can show a clear unavailable state and keep rows held for
    review rather than silently replacing user decisions with an empty DB.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self.unavailable_reason: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_meta(key, value) VALUES ('version', ?)", (_SCHEMA_VERSION,))
                conn.commit()
            elif row[0] != _SCHEMA_VERSION:
                raise DecisionStoreUnavailable(f"unsupported decision-store schema version {row[0]}")
            self._conn = conn
        except (OSError, sqlite3.DatabaseError, DecisionStoreUnavailable) as exc:
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:
                pass
            try:
                conn.close()  # type: ignore[name-defined]
            except Exception:
                pass
            self.unavailable_reason = str(exc)

    @property
    def available(self) -> bool:
        return self._conn is not None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise DecisionStoreUnavailable(self.unavailable_reason or "decision store unavailable")
        return self._conn

    def get_release_decision(self, release_id: str) -> ActressDecision | None:
        key = canonical_release_key(release_id)
        with self._lock:
            row = self._require_conn().execute(
                "SELECT release_key, kind, actresses_json, stable_ids_json, captured_r18_json, "
                "snapshot_revision, updated_at FROM release_decisions WHERE release_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        try:
            return ActressDecision(
                release_key=row[0],
                kind=DecisionKind(row[1]),
                actresses=tuple(json.loads(row[2])),
                stable_ids=tuple(json.loads(row[3])),
                captured_r18_actresses=tuple(json.loads(row[4])),
                snapshot_revision=row[5] or None,
                updated_at=row[6],
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise DecisionStoreUnavailable(f"invalid decision for {key}") from exc

    def save_release_decision(
        self,
        release_id: str,
        *,
        kind: DecisionKind,
        actresses: list[str] | tuple[str, ...],
        stable_ids: list[str] | tuple[str, ...] = (),
        captured_r18_actresses: list[str] | tuple[str, ...] = (),
        snapshot_revision: str | None = None,
    ) -> ActressDecision:
        key = canonical_release_key(release_id)
        if not key:
            raise ValueError("release ID cannot be blank")
        if kind is DecisionKind.FALLBACK:
            # An empty list is valid only for an explicit fallback approval.
            normalized = tuple(" ".join(str(name).split()) for name in actresses if str(name).strip())
        else:
            normalized = normalize_actress_names(actresses)
        ids = tuple(str(value).strip() for value in stable_ids if str(value).strip())
        captured = tuple(" ".join(str(name).split()) for name in captured_r18_actresses if str(name).strip())
        updated_at = datetime.now(timezone.utc).isoformat()
        decision = ActressDecision(key, kind, normalized, ids, captured, snapshot_revision, updated_at)
        with self._lock:
            conn = self._require_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR REPLACE INTO release_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        kind.value,
                        json.dumps(normalized, ensure_ascii=False),
                        json.dumps(ids, ensure_ascii=False),
                        json.dumps(captured, ensure_ascii=False),
                        snapshot_revision,
                        updated_at,
                    ),
                )
                conn.commit()
                reread = self.get_release_decision(key)
                if reread is None:
                    raise DecisionStoreUnavailable("decision disappeared after commit")
                return reread
            except Exception:
                conn.rollback()
                raise

    def save_alias_override(
        self,
        stable_id: str,
        canonical_name: str,
        aliases: list[str] | tuple[str, ...] = (),
        snapshot_revision: str | None = None,
    ) -> ActressAliasOverride:
        stable_id = stable_id.strip()
        canonical_name = " ".join(canonical_name.split())
        if not stable_id or not canonical_name:
            raise ValueError("stable ID and canonical actress name are required")
        alias_values = normalize_actress_names((canonical_name, *aliases))
        updated_at = datetime.now(timezone.utc).isoformat()
        result = ActressAliasOverride(stable_id, canonical_name, alias_values[1:], snapshot_revision, updated_at)
        with self._lock:
            conn = self._require_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR REPLACE INTO identity_aliases VALUES (?, ?, ?, ?, ?)",
                    (stable_id, canonical_name, json.dumps(result.aliases, ensure_ascii=False), snapshot_revision, updated_at),
                )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def get_alias_override(self, stable_id: str) -> ActressAliasOverride | None:
        with self._lock:
            row = self._require_conn().execute(
                "SELECT stable_id, canonical_name, aliases_json, snapshot_revision, updated_at "
                "FROM identity_aliases WHERE stable_id = ?",
                (stable_id.strip(),),
            ).fetchone()
        if row is None:
            return None
        try:
            return ActressAliasOverride(row[0], row[1], tuple(json.loads(row[2])), row[3] or None, row[4])
        except (TypeError, json.JSONDecodeError) as exc:
            raise DecisionStoreUnavailable(f"invalid alias override for {stable_id}") from exc

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "IdentityDecisionStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
