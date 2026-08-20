import json
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from javsorter.gui.widgets.match_review_dialog import MatchReviewDialog
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient

FIXTURES = Path(__file__).parent / "fixtures" / "json"


def test_match_review_dialog_successful_lookup(qtbot, tmp_path, requests_mock):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        json=payload,
    )
    cache = MetadataCache(tmp_path / "cache.sqlite3")
    client = ScraperClient(base_delay=0, jitter=0)

    dialog = MatchReviewDialog(None, "some_file.mp4", None, cache, client)
    qtbot.addWidget(dialog)
    dialog.id_edit.setText("SSIS-001")

    dialog._on_look_up()

    assert dialog.result_content_id == "SSIS-001"
    assert dialog.result_record is not None
    assert dialog.result_record.title == payload["title"]

    cache.close()
    client.close()


def test_match_review_dialog_no_match(qtbot, tmp_path, requests_mock, monkeypatch):
    # _on_look_up() shows a real modal QMessageBox on the no-match path,
    # which would block the test event loop waiting for a click; patch it
    # out since we only care about the resulting dialog/cache state.
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=ZZZZ-999/json",
        status_code=404,
    )
    cache = MetadataCache(tmp_path / "cache.sqlite3")
    client = ScraperClient(base_delay=0, jitter=0)

    dialog = MatchReviewDialog(None, "some_file.mp4", None, cache, client)
    qtbot.addWidget(dialog)
    dialog.id_edit.setText("ZZZZ-999")

    dialog._on_look_up()

    assert dialog.result_record is None
    assert cache.has_not_found("ZZZZ-999") is True

    cache.close()
    client.close()


def test_match_review_dialog_uses_cache_before_network(qtbot, tmp_path, requests_mock):
    cache = MetadataCache(tmp_path / "cache.sqlite3")
    client = ScraperClient(base_delay=0, jitter=0)
    from javsorter.core.models import MetadataRecord

    cache.put("ABC-123", MetadataRecord(content_id="ABC-123", title="Cached Title"))
    # Deliberately no requests_mock registration for this URL -- if the
    # dialog hit the network instead of the cache, this would raise
    # requests_mock's NoMockAddress error.

    dialog = MatchReviewDialog(None, "some_file.mp4", "ABC-123", cache, client)
    qtbot.addWidget(dialog)

    dialog._on_look_up()

    assert dialog.result_record.title == "Cached Title"

    cache.close()
    client.close()
