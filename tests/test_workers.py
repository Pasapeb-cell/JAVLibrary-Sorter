"""Offline tests for the background workers.

These matter disproportionately: a worker that dies mid-run leaves the
GUI with its buttons disabled and no way forward short of a restart, so
every path has to end with a completion signal.
"""

import json
from pathlib import Path

import pytest
import requests

from javsorter.core.models import MatchStatus, MetadataRecord
from javsorter.core.scanner import scan_folder
from javsorter.gui.workers import ExecuteWorker, MatchWorker, ScanWorker
from javsorter.organize.options import LIBRARY_LINKS, OrganizeOptions
from javsorter.organize.pipeline import ProcessResult
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient

FIXTURES = Path(__file__).parent / "fixtures" / "json"
DETAIL_URL = "https://r18.dev/videos/vod/movies/detail/-/dvd_id={}/json"


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 32)


@pytest.fixture
def cache(tmp_path):
    c = MetadataCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


@pytest.fixture
def client():
    c = ScraperClient(base_delay=0, jitter=0, retry_backoff=0)
    yield c
    c.close()


def _break_network(client):
    """Make the underlying session raise, as a real dropped connection would."""

    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network is down")

    client._session.get = boom


# --- ScanWorker -----------------------------------------------------------


def test_scan_worker_emits_items(qtbot, tmp_path):
    _touch(tmp_path / "ABC-123.mp4")
    worker = ScanWorker(tmp_path)

    with qtbot.waitSignal(worker.finished_scan, timeout=5000) as blocker:
        worker.start()
    worker.wait(5000)

    items = blocker.args[0]
    assert len(items) == 1
    assert items[0].extracted.content_id == "ABC-123"


def test_scan_worker_reports_failure_instead_of_dying(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "javsorter.gui.workers.scan_folder",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("scan exploded")),
    )
    worker = ScanWorker(tmp_path)

    with qtbot.waitSignal(worker.failed, timeout=5000) as blocker:
        worker.start()
    worker.wait(5000)

    assert "scan exploded" in blocker.args[0]


# --- MatchWorker ----------------------------------------------------------


def test_match_worker_matches_items(qtbot, tmp_path, cache, client, requests_mock):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(DETAIL_URL.format("SSIS-001"), json=payload)
    _touch(tmp_path / "hhd800.com@SSIS-001.mp4")
    items = scan_folder(tmp_path)

    worker = MatchWorker(items, cache, client)
    matched = []
    worker.item_matched.connect(lambda i, r: matched.append(r))

    with qtbot.waitSignal(worker.finished_matching, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert len(matched) == 1
    assert matched[0].content_id == "SSIS-001"


def test_match_worker_reports_no_match(qtbot, tmp_path, cache, client, requests_mock):
    requests_mock.get(DETAIL_URL.format("ZZZZ-99999"), status_code=404)
    _touch(tmp_path / "ZZZZ-99999.mp4")
    items = scan_folder(tmp_path)

    worker = MatchWorker(items, cache, client)
    failures = []
    worker.item_failed.connect(lambda i, msg: failures.append(msg))

    with qtbot.waitSignal(worker.finished_matching, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert failures == ["No match found on r18.dev"]


def test_match_worker_survives_dropped_connection(qtbot, tmp_path, cache, client):
    """Regression: requests' own ConnectionError used to escape the worker,
    killing the thread so finished_matching never fired and the GUI stayed
    disabled forever.
    """
    _break_network(client)
    _touch(tmp_path / "ABC-123.mp4")
    items = scan_folder(tmp_path)

    worker = MatchWorker(items, cache, client)
    failures = []
    worker.item_failed.connect(lambda i, msg: failures.append(msg))

    with qtbot.waitSignal(worker.finished_matching, timeout=10000):
        worker.start()
    worker.wait(10000)

    assert len(failures) == 1
    assert "network is down" in failures[0]
    # Reported as a clean network error, not swallowed by the catch-all.
    assert "Unexpected error" not in failures[0]


def test_match_worker_continues_after_one_bad_item(qtbot, tmp_path, cache, client, requests_mock):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(DETAIL_URL.format("SSIS-001"), json=payload)
    requests_mock.get(DETAIL_URL.format("MIST-435"), status_code=500)
    _touch(tmp_path / "SSIS-001.mp4")
    _touch(tmp_path / "MIST-435.mp4")
    items = scan_folder(tmp_path)

    worker = MatchWorker(items, cache, client)
    matched, failures = [], []
    worker.item_matched.connect(lambda i, r: matched.append(r))
    worker.item_failed.connect(lambda i, msg: failures.append(msg))

    with qtbot.waitSignal(worker.finished_matching, timeout=10000):
        worker.start()
    worker.wait(10000)

    assert len(matched) == 1
    assert len(failures) == 1


def test_match_worker_skips_items_with_no_id(qtbot, tmp_path, cache, client):
    _touch(tmp_path / "random_home_video.mp4")
    items = scan_folder(tmp_path)
    assert items[0].status == MatchStatus.NO_ID

    worker = MatchWorker(items, cache, client)
    touched = []
    worker.item_matched.connect(lambda i, r: touched.append(r))
    worker.item_failed.connect(lambda i, m: touched.append(m))

    with qtbot.waitSignal(worker.finished_matching, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert touched == []


# --- ExecuteWorker --------------------------------------------------------


def _matched_entry(tmp_path, content_id="ABC-123"):
    _touch(tmp_path / "source" / f"{content_id}.mp4")
    items = scan_folder(tmp_path / "source")
    record = MetadataRecord(
        content_id=content_id, title="Title", actresses=["Someone"], cover_url=None
    )
    return [(0, items[0], record)]


def test_execute_worker_processes_items(qtbot, tmp_path, client):
    matched = _matched_entry(tmp_path)
    worker = ExecuteWorker(matched, OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS, enabled_categories=["Actress"]), client)
    done = []
    worker.item_done.connect(lambda i, r: done.append(r))

    with qtbot.waitSignal(worker.finished_run, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert len(done) == 1
    assert (tmp_path / "Library" / "ABC-123" / "ABC-123.mp4").exists()


def test_execute_worker_reports_error_and_still_finishes(qtbot, tmp_path, client, monkeypatch):
    matched = _matched_entry(tmp_path)
    monkeypatch.setattr(
        "javsorter.gui.workers.process_item",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("disk on fire")),
    )
    worker = ExecuteWorker(matched, OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS), client)
    errors = []
    worker.item_error.connect(lambda i, msg: errors.append(msg))

    with qtbot.waitSignal(worker.finished_run, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert errors == ["disk on fire"]


def _two_matched_entries(tmp_path):
    _touch(tmp_path / "source" / "ABC-123.mp4")
    _touch(tmp_path / "source" / "DEF-456.mp4")
    items = scan_folder(tmp_path / "source")
    return [
        (i, item, MetadataRecord(content_id=item.extracted.content_id, title="T", cover_url=None))
        for i, item in enumerate(items)
    ]


def test_execute_worker_cancelled_before_start_processes_nothing(qtbot, tmp_path, client):
    worker = ExecuteWorker(_two_matched_entries(tmp_path), OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS), client)
    done = []
    worker.item_done.connect(lambda i, r: done.append(r))

    worker.request_cancel()
    with qtbot.waitSignal(worker.finished_run, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert done == []
    assert not (tmp_path / "Library").exists()


def test_execute_worker_cancel_mid_run_skips_remaining(qtbot, tmp_path, client, monkeypatch):
    """Cancel from inside process_item, i.e. on the worker's own thread, so
    the flag is set before the loop checks it again. (Cancelling via a
    signal handler instead would race the main thread's event loop.)
    """
    matched = _two_matched_entries(tmp_path)
    worker = ExecuteWorker(matched, OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS), client)

    calls = []

    def cancel_after_first(*_args, **_kwargs):
        calls.append(1)
        worker.request_cancel()
        return ProcessResult(content_id="ABC-123")

    monkeypatch.setattr("javsorter.gui.workers.process_item", cancel_after_first)

    with qtbot.waitSignal(worker.finished_run, timeout=5000):
        worker.start()
    worker.wait(5000)

    assert len(calls) == 1
