"""Manual/live GUI smoke test -- actually drives the real MainWindow
through the Scan -> match -> Run flow against the real r18.dev API and a
real scratch folder, verifying the visible happy path end to end.

Excluded from the default test run (see `addopts` in pyproject.toml).
Run explicitly with: pytest -m live -k gui
"""

from pathlib import Path

import pytest

from javsorter.core.models import MatchStatus
from javsorter.gui.main_window import MainWindow


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


@pytest.mark.live
def test_gui_scan_and_run_happy_path(qtbot, tmp_path):
    source = tmp_path / "source"
    library = tmp_path / "Library"
    _touch(source / "hhd800.com@SSIS-001.mp4")
    _touch(source / "not_a_real_id_ZZZZ99999.mp4")

    window = MainWindow(cache_path=tmp_path / "cache.sqlite3", settings_path=tmp_path / "settings.json")
    qtbot.addWidget(window)

    window.settings_panel.source_edit.setText(str(source))
    window.settings_panel.library_edit.setText(str(library))

    qtbot.mouseClick(window.settings_panel.scan_button, _left_button())

    def _scanned():
        assert window._model.rowCount() == 2

    qtbot.waitUntil(_scanned, timeout=10000)

    def _matched():
        assert window.settings_panel.run_button.isEnabled()

    qtbot.waitUntil(_matched, timeout=20000)

    ssis_row = next(
        row
        for row in range(window._model.rowCount())
        if window._model.item_at(row).extracted.content_id == "SSIS-001"
    )
    no_match_row = next(
        row
        for row in range(window._model.rowCount())
        if window._model.item_at(row).extracted.content_id == "ZZZZ-99999"
    )
    assert window._model.item_at(ssis_row).status == MatchStatus.MATCHED
    assert window._model.item_at(no_match_row).status == MatchStatus.NO_MATCH

    qtbot.mouseClick(window.settings_panel.run_button, _left_button())

    def _sorted():
        assert (library / "SSIS-001" / "SSIS-001.mp4").exists()

    qtbot.waitUntil(_sorted, timeout=10000)
    assert (library / "SSIS-001" / "SSIS-001.nfo").exists()

    window.close()


def _left_button():
    from PySide6.QtCore import Qt

    return Qt.MouseButton.LeftButton
