from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
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


class SettingsPanel(QWidget):
    def __init__(self):
        super().__init__()

        self.source_edit = QLineEdit()
        self.library_edit = QLineEdit()
        self.sort_in_place_radio = QRadioButton("Sort in place")
        self.import_radio = QRadioButton("Import into library")
        self.import_radio.setChecked(True)
        self.category_checkboxes = {name: QCheckBox(name) for name in ALL_CATEGORIES}
        for checkbox in self.category_checkboxes.values():
            checkbox.setChecked(True)
        self.blocked_genres_button = QPushButton("Blocked genres...")
        self.scan_button = QPushButton("Scan")
        self.run_button = QPushButton("Run")
        self.run_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.undo_button = QPushButton("Undo last run")

        layout = QVBoxLayout(self)
        layout.addLayout(self._folder_row("Source folder:", self.source_edit))
        layout.addLayout(self._folder_row("Library folder:", self.library_edit))

        mode_box = QGroupBox("Sort mode")
        mode_layout = QHBoxLayout(mode_box)
        mode_layout.addWidget(self.sort_in_place_radio)
        mode_layout.addWidget(self.import_radio)
        layout.addWidget(mode_box)

        category_box = QGroupBox("Category folders")
        category_layout = QHBoxLayout(category_box)
        for checkbox in self.category_checkboxes.values():
            category_layout.addWidget(checkbox)
        category_layout.addStretch()
        category_layout.addWidget(self.blocked_genres_button)
        layout.addWidget(category_box)

        button_row = QHBoxLayout()
        button_row.addWidget(self.scan_button)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch()
        button_row.addWidget(self.undo_button)
        layout.addLayout(button_row)

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

    def sort_in_place(self) -> bool:
        return self.sort_in_place_radio.isChecked()

    def enabled_categories(self) -> list[str]:
        return [name for name, checkbox in self.category_checkboxes.items() if checkbox.isChecked()]
