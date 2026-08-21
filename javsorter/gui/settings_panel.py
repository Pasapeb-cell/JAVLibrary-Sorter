from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from javsorter.organize.category_builder import ALL_CATEGORIES
from javsorter.organize.options import LIBRARY_LINKS, TAG_FOLDERS, OrganizeOptions


class SettingsPanel(QWidget):
    def __init__(self):
        super().__init__()

        self.source_edit = QLineEdit()
        self.destination_edit = QLineEdit()

        # Where the organised folders are built. "In the source folder" is
        # a root choice, not a separate mode -- which is what stops it from
        # pointlessly demanding a destination folder.
        self.in_source_radio = QRadioButton("In the source folder")
        self.into_folder_radio = QRadioButton("Into this folder:")
        self.into_folder_radio.setChecked(True)

        self.tag_layout_radio = QRadioButton("Move each file into one tag folder")
        self.tag_layout_radio.setChecked(True)
        self.links_layout_radio = QRadioButton("Release folders + shortcuts in every category")
        self.links_layout_radio.setToolTip(
            "One copy per release plus a symlink in every matching Actress, "
            "Genre, Studio and Year folder. Needs Windows Developer Mode."
        )

        self.sort_by_combo = QComboBox()
        self.sort_by_combo.addItems(ALL_CATEGORIES)
        self.sort_by_combo.setCurrentText("Genre")
        self.sort_by_combo.setToolTip(
            "Which tag decides the folder. Where a release has several "
            "(genres, actresses), the first one listed is used."
        )

        self.link_only_checkbox = QCheckBox("Leave videos where they are (shortcuts only)")

        self.dry_run_checkbox = QCheckBox("Dry run (preview only)")
        self.dry_run_checkbox.setToolTip(
            "Show exactly what Run would do without moving, renaming, "
            "downloading, or linking anything."
        )

        self.category_checkboxes = {name: QCheckBox(name) for name in ALL_CATEGORIES}
        for checkbox in self.category_checkboxes.values():
            checkbox.setChecked(True)

        self.blocked_genres_button = QPushButton("Blocked genres...")
        self.scan_button = QPushButton("Scan")
        self.run_button = QPushButton("Run")
        self.run_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.rescan_button = QPushButton("Rescan library")
        self.rescan_button.setToolTip(
            "Rebuild category folders and refresh NFOs for a library organised "
            "with shortcuts. Never moves or deletes videos."
        )
        self.undo_button = QPushButton("Undo last run")

        layout = QVBoxLayout(self)
        layout.addLayout(self._folder_row("Source folder:", self.source_edit))

        destination_box = QGroupBox("Organise")
        destination_layout = QVBoxLayout(destination_box)
        destination_layout.addWidget(self.in_source_radio)
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.into_folder_radio)
        destination_row.addWidget(self.destination_edit)
        self.destination_browse_button = QPushButton("Browse...")
        self.destination_browse_button.clicked.connect(
            lambda: self._browse(self.destination_edit)
        )
        destination_row.addWidget(self.destination_browse_button)
        destination_layout.addLayout(destination_row)
        layout.addWidget(destination_box)

        layout_box = QGroupBox("Layout")
        layout_layout = QVBoxLayout(layout_box)
        tag_row = QHBoxLayout()
        tag_row.addWidget(self.tag_layout_radio)
        tag_row.addWidget(QLabel("by"))
        tag_row.addWidget(self.sort_by_combo)
        tag_row.addStretch()
        tag_row.addWidget(self.dry_run_checkbox)
        layout_layout.addLayout(tag_row)
        layout_layout.addWidget(self.links_layout_radio)

        self.category_box = QGroupBox("Shortcut folders")
        category_layout = QHBoxLayout(self.category_box)
        for checkbox in self.category_checkboxes.values():
            category_layout.addWidget(checkbox)
        category_layout.addWidget(self.link_only_checkbox)
        category_layout.addStretch()
        layout_layout.addWidget(self.category_box)
        layout.addWidget(layout_box)

        genre_row = QHBoxLayout()
        genre_row.addStretch()
        genre_row.addWidget(self.blocked_genres_button)
        layout.addLayout(genre_row)

        button_row = QHBoxLayout()
        button_row.addWidget(self.scan_button)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch()
        button_row.addWidget(self.rescan_button)
        button_row.addWidget(self.undo_button)
        layout.addLayout(button_row)

        self.in_source_radio.toggled.connect(self._update_enabled_state)
        self.tag_layout_radio.toggled.connect(self._update_enabled_state)
        self._update_enabled_state()

    def _update_enabled_state(self) -> None:
        """Only show inputs that apply, so nothing asks for a folder it
        won't use.
        """
        into_folder = self.into_folder_radio.isChecked()
        self.destination_edit.setEnabled(into_folder)
        self.destination_browse_button.setEnabled(into_folder)

        tag_layout = self.tag_layout_radio.isChecked()
        self.sort_by_combo.setEnabled(tag_layout)
        self.category_box.setEnabled(not tag_layout)
        self.rescan_button.setEnabled(not tag_layout)

    def _folder_row(self, label_text: str, line_edit: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        row.addWidget(line_edit)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(lambda: self._browse(line_edit))
        row.addWidget(browse_button)
        return row

    def _browse(self, line_edit: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            line_edit.setText(folder)

    def organises_in_source(self) -> bool:
        return self.in_source_radio.isChecked()

    def enabled_categories(self) -> list[str]:
        return [name for name, checkbox in self.category_checkboxes.items() if checkbox.isChecked()]

    def root_folder(self) -> Path | None:
        """The folder the organised structure is built in, or None if the
        user still has to choose one.
        """
        if self.organises_in_source():
            source = self.source_edit.text().strip()
            return Path(source) if source else None
        destination = self.destination_edit.text().strip()
        return Path(destination) if destination else None

    def organize_options(self) -> OrganizeOptions | None:
        root = self.root_folder()
        if root is None:
            return None
        if self.tag_layout_radio.isChecked():
            return OrganizeOptions(
                root=root, layout=TAG_FOLDERS, sort_by=self.sort_by_combo.currentText()
            )
        return OrganizeOptions(
            root=root,
            layout=LIBRARY_LINKS,
            enabled_categories=self.enabled_categories(),
            link_only=self.link_only_checkbox.isChecked(),
        )
