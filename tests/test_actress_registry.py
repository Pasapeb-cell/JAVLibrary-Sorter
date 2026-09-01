from __future__ import annotations

import io
from pathlib import Path

import pytest

from javsorter.scraping.actress_registry import (
    RegistryManager,
    RegistryState,
    parse_copy_dump,
)
from javsorter.scraping.registry_download import _revision_from_url


FIXTURE = Path(__file__).parent / "fixtures" / "registry" / "minimal.sql"


def _imported(tmp_path):
    manager = RegistryManager(tmp_path / "registry")
    with FIXTURE.open("r", encoding="utf-8") as stream:
        manager.import_dump(stream, "2026-09-01", source_url="fixture://minimal")
    return manager


def test_import_lookup_by_display_and_content_id(tmp_path):
    manager = _imported(tmp_path)
    index = manager.open_active()
    assert index is not None
    try:
        match = index.lookup("ABC-1")
        assert match.state is RegistryState.EXACT
        assert [actress.canonical_name for actress in match.actresses] == [
            "Alice Example",
            "Bob Example",
        ]
        assert index.lookup("118abc00002").actresses[0].stable_id == "a3"
        assert index.lookup("missing-999").state is RegistryState.NO_ENTRY
    finally:
        index.close()


def test_duplicate_identity_sets_are_ambiguous(tmp_path):
    manager = RegistryManager(tmp_path / "registry")
    sql = """\
COPY public.derived_video (content_id, dvd_id, dvd_id_norm) FROM stdin;
cid-a\tDUP-1\tDUP1
cid-b\tDUP-1\tDUP1
\\.
COPY public.derived_actress (id, name_romaji) FROM stdin;
a\tA
b\tB
\\.
COPY public.derived_video_actress (content_id, actress_id, ordinality) FROM stdin;
cid-a\ta\t1
cid-b\tb\t1
\\.
"""
    manager.import_dump(io.StringIO(sql), "duplicate")
    index = manager.open_active()
    assert index is not None
    try:
        assert index.lookup("DUP-1").state is RegistryState.AMBIGUOUS
    finally:
        index.close()


def test_failed_import_leaves_previous_generation_active(tmp_path):
    manager = _imported(tmp_path)
    with pytest.raises(ValueError):
        manager.import_dump(io.StringIO("COPY public.derived_video (content_id) FROM stdin;\n"), "broken")
    assert manager.active_revision() == "2026-09-01"


def test_copy_parser_decodes_null_and_escapes():
    rows = []
    parse_copy_dump(
        io.StringIO(
            "COPY public.derived_actress (id, name_romaji) FROM stdin;\n"
            "x\ty\\N\n\\.\n"
            "COPY public.derived_video (content_id) FROM stdin;\n"
            "cid\n\\.\n"
            "COPY public.derived_video_actress (content_id, actress_id) FROM stdin;\n"
            "cid\tx\n\\.\n"
        ),
        lambda table, row: rows.append((table, row)),
    )
    assert rows[0][1]["name_romaji"] == "y\\N"


def test_revision_from_latest_url_is_stable():
    assert _revision_from_url("https://r18.dev/dumps/r18dotdev_dump_2026-09-01.sql.gz") == "2026-09-01"
    assert _revision_from_url("https://mirror.invalid/latest") == _revision_from_url(
        "https://mirror.invalid/latest"
    )
