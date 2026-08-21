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
    sorted_root = tmp_path / "Sorted"
    _touch(source / "hhd800.com@SSIS-001.mp4")
    _touch(source / "not_a_real_id_ZZZZ99999.mp4")

    window = MainWindow(
        cache_path=tmp_path / "cache.sqlite3",
        settings_path=tmp_path / "settings.json",
        runs_dir=tmp_path / "runs",
        log_dir=tmp_path / "logs",
    )
    qtbot.addWidget(window)

    window.settings_panel.source_edit.setText(str(source))
    window.settings_panel.into_folder_radio.setChecked(True)
    window.settings_panel.destination_edit.setText(str(sorted_root))
    window.settings_panel.tag_layout_radio.setChecked(True)
    window.settings_panel.sort_by_combo.setCurrentText("Genre")

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
        # Which genre folder it lands in depends on live metadata, so assert
        # the shape rather than a specific genre name.
        assert list(sorted_root.rglob("SSIS-001.mp4"))

    qtbot.waitUntil(_sorted, timeout=10000)

    video = next(iter(sorted_root.rglob("SSIS-001.mp4")))
    assert video.parent.parent == sorted_root  # exactly one tag folder deep
    assert (video.parent / "SSIS-001.nfo").exists()
    assert not (source / "hhd800.com@SSIS-001.mp4").exists()
    # The unmatched file is left where it is.
    assert (source / "not_a_real_id_ZZZZ99999.mp4").exists()

    window.close()


def _left_button():
    from PySide6.QtCore import Qt

    return Qt.MouseButton.LeftButton
