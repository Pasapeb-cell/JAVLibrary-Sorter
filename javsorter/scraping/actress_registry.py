"""Local, read-only actress evidence imported from an R18.dev dump.

The public dump is a PostgreSQL ``pg_dump`` rather than an API response.  This
module deliberately understands only the COPY blocks needed for actress
resolution.  It never executes SQL from a downloaded archive.  Importing into
a revisioned SQLite file makes a refresh atomic: readers keep using the old
generation until the new one has passed validation and the active pointer is
switched.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, TextIO


class RegistryUnavailableError(RuntimeError):
    """The registry is absent or could not be read safely."""


class RegistryState(str, Enum):
    EXACT = "exact"
    NO_ENTRY = "no_entry"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ActressIdentity:
    stable_id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegistryMatch:
    state: RegistryState
    requested_id: str
    actresses: tuple[ActressIdentity, ...] = ()
    snapshot_revision: str | None = None
    candidates: tuple[tuple[ActressIdentity, ...], ...] = ()
    reason: str | None = None

    @property
    def is_exact(self) -> bool:
        return self.state is RegistryState.EXACT


@dataclass(frozen=True)
class RegistryProvenance:
    revision: str
    source_url: str | None
    source_digest: str | None
    imported_at: str | None


_NULL = "\x00__r18_null__\x00"
_COPY_HEADER = re.compile(
    r'^COPY\s+(?:"?public"?\.)"?([^"\s(]+)"?\s*(?:\((.*?)\))?\s+FROM\s+stdin;\s*$'
)
_RELEVANT_TABLES = {"derived_video", "derived_actress", "derived_video_actress"}


def normalize_content_id(value: str | None) -> str:
    return "".join((value or "").strip().upper().split())


def normalize_display_id(value: str | None) -> str:
    return re.sub(r"[-\s]", "", (value or "").strip().upper())


def _decode_copy_field(value: str) -> str:
    if value == "\\N":
        return _NULL
    if "\\" not in value:
        return value
    out: list[str] = []
    i = 0
    while i < len(value):
        if value[i] != "\\" or i + 1 >= len(value):
            out.append(value[i])
            i += 1
            continue
        escaped = value[i + 1]
        out.append(
            {
                "n": "\n",
                "t": "\t",
                "r": "\r",
                "b": "\b",
                "f": "\f",
                "v": "\v",
                "\\": "\\",
            }.get(escaped, "\\" + escaped)
        )
        i += 2
    return "".join(out)


def _parse_header(line: str) -> tuple[str, list[str]] | None:
    match = _COPY_HEADER.match(line.rstrip("\r\n"))
    if not match:
        return None
    table = match.group(1)
    columns = []
    if match.group(2):
        columns = [part.strip().strip('"') for part in match.group(2).split(",")]
    return table, columns


def parse_copy_dump(reader: TextIO | io.BufferedIOBase, emit: Callable[[str, dict[str, str]], None]) -> None:
    """Stream relevant PostgreSQL COPY rows to ``emit``.

    Only table/column data is interpreted; regular SQL statements and unknown
    tables are ignored.  A malformed COPY block is rejected rather than being
    silently imported as incomplete evidence.
    """

    if isinstance(reader, io.BufferedIOBase):
        text_reader: Iterable[str] = io.TextIOWrapper(reader, encoding="utf-8", errors="strict")
    else:
        text_reader = reader

    table: str | None = None
    columns: list[str] = []
    seen_tables: set[str] = set()
    for line_number, raw_line in enumerate(text_reader, start=1):
        line = raw_line.rstrip("\r\n")
        if table is None:
            header = _parse_header(line)
            if header is None:
                continue
            table, columns = header
            if table in _RELEVANT_TABLES and not columns:
                raise ValueError(f"COPY {table} at line {line_number} has no column list")
            seen_tables.add(table)
            continue
        if line == r"\.":
            table = None
            columns = []
            continue
        if table not in _RELEVANT_TABLES:
            continue
        values = [_decode_copy_field(part) for part in line.split("\t")]
        if len(values) != len(columns):
            raise ValueError(
                f"COPY {table} at line {line_number} has {len(values)} values for {len(columns)} columns"
            )
        emit(table, {column: value for column, value in zip(columns, values)})

    if table is not None:
        raise ValueError(f"unterminated COPY block for {table}")
    missing = _RELEVANT_TABLES - seen_tables
    if missing:
        raise ValueError("dump is missing required COPY tables: " + ", ".join(sorted(missing)))


_SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE raw_videos (
    content_id TEXT NOT NULL,
    dvd_id TEXT,
    dvd_id_norm TEXT
);
CREATE TABLE raw_actresses (
    id TEXT NOT NULL,
    name_romaji TEXT,
    name_kanji TEXT,
    name_kana TEXT
);
CREATE TABLE raw_video_actresses (
    content_id TEXT NOT NULL,
    actress_id TEXT NOT NULL,
    ordinality INTEGER
);
CREATE TABLE entries (
    entry_id INTEGER PRIMARY KEY,
    content_id TEXT NOT NULL,
    dvd_id_norm TEXT NOT NULL,
    signature TEXT NOT NULL,
    revision TEXT NOT NULL,
    cast_complete INTEGER NOT NULL DEFAULT 1,
    UNIQUE(content_id, signature)
);
CREATE TABLE entry_actresses (
    entry_id INTEGER NOT NULL REFERENCES entries(entry_id),
    ordinal INTEGER NOT NULL,
    stable_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    PRIMARY KEY(entry_id, ordinal)
);
CREATE INDEX entries_content_idx ON entries(content_id);
CREATE INDEX entries_dvd_idx ON entries(dvd_id_norm);
"""


class RegistryIndex:
    """A pinned read-only view of one validated registry generation."""

    def __init__(self, path: Path):
        if not path.exists():
            raise RegistryUnavailableError(f"registry generation does not exist: {path}")
        self.path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            self._conn = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False
            )
            self._revision = self._conn.execute(
                "SELECT value FROM metadata WHERE key = 'revision'"
            ).fetchone()[0]
        except (sqlite3.DatabaseError, OSError, TypeError, IndexError, AttributeError) as exc:
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:
                pass
            raise RegistryUnavailableError(f"invalid registry generation: {path}") from exc

    @property
    def revision(self) -> str:
        return self._revision

    def lookup(self, requested_id: str) -> RegistryMatch:
        """Return exact evidence, no entry, or ambiguity without guessing."""
        normalized_content = normalize_content_id(requested_id).lower()
        normalized_display = normalize_display_id(requested_id)
        with self._lock:
            if self._conn is None:
                raise RegistryUnavailableError("registry generation is closed")
            rows = self._conn.execute(
                "SELECT DISTINCT entry_id, cast_complete FROM entries WHERE content_id = ? OR dvd_id_norm = ?",
                (normalized_content, normalized_display),
            ).fetchall()
            if not rows:
                return RegistryMatch(RegistryState.NO_ENTRY, requested_id, snapshot_revision=self.revision)
            candidate_sets: list[tuple[ActressIdentity, ...]] = []
            for entry_id, cast_complete in rows:
                if not cast_complete:
                    return RegistryMatch(
                        RegistryState.AMBIGUOUS,
                        requested_id,
                        snapshot_revision=self.revision,
                        reason="registry entry has an unresolved actress relation",
                    )
                actress_rows = self._conn.execute(
                    "SELECT stable_id, canonical_name, aliases_json FROM entry_actresses "
                    "WHERE entry_id = ? ORDER BY ordinal",
                    (entry_id,),
                ).fetchall()
                identities = tuple(
                    ActressIdentity(stable_id, canonical, tuple(json.loads(aliases)))
                    for stable_id, canonical, aliases in actress_rows
                )
                if identities not in candidate_sets:
                    candidate_sets.append(identities)
            if len(candidate_sets) != 1:
                return RegistryMatch(
                    RegistryState.AMBIGUOUS,
                    requested_id,
                    snapshot_revision=self.revision,
                    candidates=tuple(candidate_sets),
                    reason="multiple actress identity sets in registry",
                )
            return RegistryMatch(
                RegistryState.EXACT,
                requested_id,
                actresses=candidate_sets[0],
                snapshot_revision=self.revision,
            )

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "RegistryIndex":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class RegistryManager:
    """Own generation imports and the active-version pointer."""

    def __init__(self, root: Path, pointer_path: Path | None = None):
        self.root = root
        self.pointer_path = pointer_path or root / "active"
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def active_revision(self) -> str | None:
        try:
            value = self.pointer_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    def open_active(self) -> RegistryIndex | None:
        revision = self.active_revision()
        if not revision:
            return None
        try:
            return RegistryIndex(self._generation_path(revision))
        except RegistryUnavailableError:
            return None

    def import_dump(
        self,
        reader: TextIO | io.BufferedIOBase,
        revision: str,
        *,
        source_url: str | None = None,
        source_digest: str | None = None,
        imported_at: str | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> RegistryProvenance:
        """Build and atomically activate one generation from a COPY stream."""
        requested_revision = _safe_revision(revision)
        with self._write_lock:
            revision = requested_revision
            final = self._generation_path(revision)
            while final.exists():
                existing_digest = _generation_digest(final)
                if source_digest and existing_digest == source_digest:
                    _atomic_write_text(self.pointer_path, revision)
                    return RegistryProvenance(revision, source_url, source_digest, imported_at)
                if not source_digest:
                    raise ValueError(
                        f"refusing to replace existing registry generation {revision} without a source digest"
                    )
                revision = f"{requested_revision}-{source_digest[:16]}"
                final = self._generation_path(revision)
                if final.exists() and _generation_digest(final) == source_digest:
                    _atomic_write_text(self.pointer_path, revision)
                    return RegistryProvenance(revision, source_url, source_digest, imported_at)
                if final.exists():
                    revision = f"{requested_revision}-{source_digest[:16]}-2"
                    final = self._generation_path(revision)
            fd, candidate_name = tempfile.mkstemp(
                prefix=".generation-", suffix=".sqlite3.tmp", dir=self.root
            )
            os.close(fd)
            Path(candidate_name).unlink(missing_ok=True)
            candidate = Path(candidate_name)
            conn: sqlite3.Connection | None = None
            try:
                conn = sqlite3.connect(candidate)
                conn.executescript(_SCHEMA)
                conn.execute("BEGIN")
                seen = {"derived_video": False, "derived_actress": False, "derived_video_actress": False}

                def emit(table: str, row: dict[str, str]) -> None:
                    if should_cancel and should_cancel():
                        raise InterruptedError("registry import cancelled")
                    seen[table] = True
                    if table == "derived_video":
                        content_id = _required(row, "content_id", table).lower()
                        dvd_id = _optional(row, "dvd_id")
                        dvd_norm = _optional(row, "dvd_id_norm")
                        if not dvd_norm:
                            dvd_norm = normalize_display_id(dvd_id)
                        conn.execute(
                            "INSERT INTO raw_videos VALUES (?, ?, ?)",
                            (content_id, _nullable(dvd_id), dvd_norm),
                        )
                    elif table == "derived_actress":
                        stable_id = _required(row, "id", table)
                        conn.execute(
                            "INSERT INTO raw_actresses VALUES (?, ?, ?, ?)",
                            (
                                stable_id,
                                _nullable(_optional(row, "name_romaji")),
                                _nullable(_optional(row, "name_kanji")),
                                _nullable(_optional(row, "name_kana")),
                            ),
                        )
                    else:
                        content_id = _required(row, "content_id", table).lower()
                        stable_id = _required(row, "actress_id", table)
                        ordinal = _optional(row, "ordinality")
                        try:
                            ordinal_value = int(ordinal) if ordinal and ordinal != _NULL else 999999
                        except ValueError:
                            ordinal_value = 999999
                        conn.execute(
                            "INSERT INTO raw_video_actresses VALUES (?, ?, ?)",
                            (content_id, stable_id, ordinal_value),
                        )

                parse_copy_dump(reader, emit)
                if not all(seen.values()):
                    raise ValueError("registry dump did not contain all required actress tables")
                conn.execute("INSERT INTO metadata VALUES ('revision', ?)", (revision,))
                conn.execute("INSERT INTO metadata VALUES ('source_url', ?)", (source_url or "",))
                conn.execute("INSERT INTO metadata VALUES ('source_digest', ?)", (source_digest or "",))
                conn.execute("INSERT INTO metadata VALUES ('imported_at', ?)", (imported_at or "",))
                _materialize_entries(conn, revision)
                if conn.execute("SELECT COUNT(*) FROM entries WHERE cast_complete = 0").fetchone()[0]:
                    raise ValueError("registry dump contains unresolved actress relations")
                if conn.execute("SELECT COUNT(*) FROM entries WHERE cast_complete = 1").fetchone()[0] == 0:
                    raise ValueError("registry dump contained no video entries")
                if should_cancel and should_cancel():
                    raise InterruptedError("registry import cancelled")
                conn.execute("PRAGMA foreign_keys = ON")
                conn.commit()
                conn.close()
                conn = None
                if should_cancel and should_cancel():
                    raise InterruptedError("registry import cancelled")
                _validate_candidate(candidate, revision)
                candidate.replace(final)
                _atomic_write_text(self.pointer_path, revision)
                return RegistryProvenance(revision, source_url, source_digest, imported_at)
            except Exception:
                if conn is not None:
                    conn.rollback()
                    conn.close()
                candidate.unlink(missing_ok=True)
                raise

    def _generation_path(self, revision: str) -> Path:
        return self.root / f"generation-{revision}.sqlite3"


def _materialize_entries(conn: sqlite3.Connection, revision: str) -> None:
    video_rows = conn.execute(
        "SELECT DISTINCT content_id, dvd_id_norm FROM raw_videos WHERE content_id <> ''"
    ).fetchall()
    for content_id, dvd_id_norm in video_rows:
        actress_rows = conn.execute(
            "SELECT rva.actress_id, rva.ordinality, ra.name_romaji, ra.name_kanji, ra.name_kana "
            "FROM raw_video_actresses rva LEFT JOIN raw_actresses ra ON ra.id = rva.actress_id "
            "WHERE rva.content_id = ? ORDER BY rva.ordinality, rva.actress_id",
            (content_id,),
        ).fetchall()
        identities: list[tuple[str, str, tuple[str, ...]]] = []
        cast_complete = bool(actress_rows)
        for stable_id, _ordinal, romaji, kanji, kana in actress_rows:
            names = tuple(dict.fromkeys(name.strip() for name in (romaji, kanji, kana) if name and name.strip()))
            if not names:
                cast_complete = False
                continue
            identities.append((stable_id, names[0], names[1:]))
        signature = hashlib.sha256(
            json.dumps(identities, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        conn.execute(
            "INSERT OR IGNORE INTO entries(content_id, dvd_id_norm, signature, revision, cast_complete) VALUES (?, ?, ?, ?, ?)",
            (content_id, dvd_id_norm or "", signature, revision, int(cast_complete)),
        )
        entry_id = conn.execute(
            "SELECT entry_id FROM entries WHERE content_id = ? AND signature = ?",
            (content_id, signature),
        ).fetchone()[0]
        for ordinal, (stable_id, canonical, aliases) in enumerate(identities):
            conn.execute(
                "INSERT OR IGNORE INTO entry_actresses VALUES (?, ?, ?, ?, ?)",
                (entry_id, ordinal, stable_id, canonical, json.dumps(aliases, ensure_ascii=False)),
            )


def _required(row: dict[str, str], key: str, table: str) -> str:
    value = _optional(row, key)
    if not value:
        raise ValueError(f"COPY {table} is missing required value {key}")
    return value


def _optional(row: dict[str, str], key: str) -> str:
    value = row.get(key, "")
    return "" if value == _NULL else value.strip()


def _nullable(value: str) -> str | None:
    return value or None


def _safe_revision(value: str) -> str:
    value = value.strip()
    if not value or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError("registry revision must contain only letters, digits, '.', '_' or '-'")
    return value


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value + "\n", encoding="utf-8")
    temporary.replace(path)


def _generation_digest(path: Path) -> str | None:
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        row = conn.execute("SELECT value FROM metadata WHERE key = 'source_digest'").fetchone()
        return row[0] or None if row else None
    except (OSError, sqlite3.DatabaseError):
        return None
    finally:
        if conn is not None:
            conn.close()


def _validate_candidate(path: Path, revision: str) -> None:
    """Reopen a staged generation and verify it before publishing the pointer."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("registry generation failed SQLite integrity check")
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchone()
        if foreign_keys is not None:
            raise ValueError("registry generation has broken references")
        stored = conn.execute("SELECT value FROM metadata WHERE key = 'revision'").fetchone()
        if not stored or stored[0] != revision:
            raise ValueError("registry generation revision metadata is inconsistent")
        if conn.execute("SELECT COUNT(*) FROM entries WHERE cast_complete = 1").fetchone()[0] == 0:
            raise ValueError("registry generation has no complete entries")
    except (OSError, sqlite3.DatabaseError) as exc:
        raise ValueError("registry generation could not be validated") from exc
    finally:
        if conn is not None:
            conn.close()
