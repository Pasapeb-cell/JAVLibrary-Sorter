from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from javsorter.core.genre_filter import DEFAULT_BLOCKED_GENRES, DEFAULT_BLOCKED_PATTERNS


class GenreBlocklistDialog(QDialog):
    """Edits which genre tags are kept out of category folders and NFOs.

    The built-in list is shown read-only rather than pre-filled into the
    editable box: that keeps the user's own additions separate, so
    improvements to the built-in list still reach them later.
    """

    def __init__(self, parent: QWidget | None, use_defaults: bool, extra_blocked: list[str]):
        super().__init__(parent)
        self.setWindowTitle("Blocked genres")
        self.resize(460, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "r18.dev mixes promotional and technical tags in with real genres.\n"
                "Blocked tags are left out of both category folders and NFO files."
            )
        )

        self.use_defaults_checkbox = QCheckBox("Use the built-in blocklist")
        self.use_defaults_checkbox.setChecked(use_defaults)
        layout.addWidget(self.use_defaults_checkbox)

        layout.addWidget(QLabel("Built-in (read-only):"))
        builtin_list = QListWidget()
        builtin_list.addItems(sorted(DEFAULT_BLOCKED_GENRES))
        builtin_list.addItems(f"(pattern) {pattern}" for pattern in DEFAULT_BLOCKED_PATTERNS)
        builtin_list.setEnabled(False)
        layout.addWidget(builtin_list)

        layout.addWidget(QLabel("Also block these (one per line):"))
        self.extra_edit = QPlainTextEdit("\n".join(extra_blocked))
        self.extra_edit.setPlaceholderText("Featured Actress\nMinimal Mosaic")
        layout.addWidget(self.extra_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def use_defaults(self) -> bool:
        return self.use_defaults_checkbox.isChecked()

    def extra_blocked(self) -> list[str]:
        lines = self.extra_edit.toPlainText().splitlines()
        return [line.strip() for line in lines if line.strip()]
