from javsorter.gui.widgets.genre_blocklist_dialog import GenreBlocklistDialog


def test_dialog_shows_current_settings(qtbot):
    dialog = GenreBlocklistDialog(None, use_defaults=False, extra_blocked=["Featured Actress"])
    qtbot.addWidget(dialog)

    assert dialog.use_defaults() is False
    assert dialog.extra_blocked() == ["Featured Actress"]


def test_dialog_trims_blank_and_padded_lines(qtbot):
    dialog = GenreBlocklistDialog(None, use_defaults=True, extra_blocked=[])
    qtbot.addWidget(dialog)

    dialog.extra_edit.setPlainText("Featured Actress\n\n   Minimal Mosaic   \n\n")

    assert dialog.extra_blocked() == ["Featured Actress", "Minimal Mosaic"]


def test_dialog_edits_are_readable_back(qtbot):
    dialog = GenreBlocklistDialog(None, use_defaults=True, extra_blocked=[])
    qtbot.addWidget(dialog)

    dialog.use_defaults_checkbox.setChecked(False)

    assert dialog.use_defaults() is False
