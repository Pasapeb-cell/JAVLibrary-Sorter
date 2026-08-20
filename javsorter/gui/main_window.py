from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from javsorter.config.paths import cache_path as default_cache_path
from javsorter.config.paths import settings_path as default_settings_path
from javsorter.config.settings import Settings
from javsorter.core.models import MatchStatus
from javsorter.gui.scan_table import ScanTableModel
from javsorter.gui.settings_panel import SettingsPanel
from javsorter.gui.widgets.dev_mode_dialog import show_symlink_permission_dialog
from javsorter.gui.widgets.genre_blocklist_dialog import GenreBlocklistDialog
from javsorter.gui.widgets.match_review_dialog import MatchReviewDialog
from javsorter.gui.workers import ExecuteWorker, MatchWorker, ScanWorker
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import ScrapeError
from javsorter.scraping.lookup import lookup_for_item


class MainWindow(QMainWindow):
    def __init__(self, cache_path: Path | None = None, settings_path: Path | None = None):
        super().__init__()
        self.setWindowTitle("JAVLibrary Sorter")
        self.resize(900, 600)

        self._settings_path = settings_path or default_settings_path()
        self._settings = Settings.load(self._settings_path)

        self._client = ScraperClient()
        self._cache = MetadataCache(cache_path or default_cache_path())
        self._model = ScanTableModel()
        self._matched_records: dict[int, object] = {}
        self._scan_worker: ScanWorker | None = None
        self._match_worker: MatchWorker | None = None
        self._execute_worker: ExecuteWorker | None = None
        self._dev_mode_dialog_shown_this_run = False

        self.settings_panel = SettingsPanel()
        self.table_view = QTableView()
        self.table_view.setModel(self._model)
        self.progress_bar = QProgressBar()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.settings_panel)
        layout.addWidget(self.table_view)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view)
        self.setCentralWidget(central)

        self.settings_panel.scan_button.clicked.connect(self._start_scan)
        self.settings_panel.run_button.clicked.connect(self._start_run)
        self.settings_panel.blocked_genres_button.clicked.connect(self._edit_blocked_genres)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        self._apply_settings()

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _apply_settings(self) -> None:
        self.settings_panel.source_edit.setText(self._settings.last_source_folder)
        self.settings_panel.library_edit.setText(self._settings.last_library_folder)
        if self._settings.sort_in_place:
            self.settings_panel.sort_in_place_radio.setChecked(True)
        else:
            self.settings_panel.import_radio.setChecked(True)
        for name, checkbox in self.settings_panel.category_checkboxes.items():
            checkbox.setChecked(name in self._settings.enabled_categories)

    def _save_settings(self) -> None:
        self._settings.last_source_folder = self.settings_panel.source_edit.text().strip()
        self._settings.last_library_folder = self.settings_panel.library_edit.text().strip()
        self._settings.sort_in_place = self.settings_panel.sort_in_place()
        self._settings.enabled_categories = self.settings_panel.enabled_categories()
        self._settings.save(self._settings_path)

    def _edit_blocked_genres(self) -> None:
        dialog = GenreBlocklistDialog(
            self, self._settings.use_default_genre_blocklist, self._settings.extra_blocked_genres
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._settings.use_default_genre_blocklist = dialog.use_defaults()
        self._settings.extra_blocked_genres = dialog.extra_blocked()
        self._settings.save(self._settings_path)
        self._reapply_genre_filter()

    def _reapply_genre_filter(self) -> None:
        """Re-resolve already-matched rows against the new blocklist.

        Runs entirely off the cache (which stores unfiltered records), so
        this is instant and makes no network requests -- and it can widen
        the genre list again, which re-filtering the in-memory records
        could not.
        """
        if not self._matched_records:
            return

        genre_filter = self._settings.genre_filter()
        for row, _record in list(self._matched_records.items()):
            item = self._model.item_at(row)
            try:
                refreshed = lookup_for_item(
                    self._cache, self._client, item.extracted, genre_filter=genre_filter
                )
            except ScrapeError:
                continue
            item.metadata = refreshed
            self._matched_records[row] = refreshed
            self._model.update_row(row)
        self._log("Applied the updated genre blocklist to matched items.")

    def _start_scan(self) -> None:
        source = self.settings_panel.source_edit.text().strip()
        if not source:
            QMessageBox.warning(self, "Missing folder", "Choose a source folder first.")
            return

        self.settings_panel.scan_button.setEnabled(False)
        self.settings_panel.run_button.setEnabled(False)
        self._matched_records = {}
        self._log(f"Scanning {source}...")

        self._scan_worker = ScanWorker(Path(source))
        self._scan_worker.finished_scan.connect(self._on_scanned)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_failed(self, message: str) -> None:
        self.settings_panel.scan_button.setEnabled(True)
        QMessageBox.critical(self, "Scan failed", message)

    def _on_scanned(self, items) -> None:
        self._model.set_items(items)
        self._log(f"Found {len(items)} item(s). Looking up metadata...")

        self._match_worker = MatchWorker(
            items, self._cache, self._client, genre_filter=self._settings.genre_filter()
        )
        self._match_worker.item_matched.connect(self._on_item_matched)
        self._match_worker.item_failed.connect(self._on_item_failed)
        self._match_worker.progress.connect(self._on_progress)
        self._match_worker.finished_matching.connect(self._on_matching_finished)
        self.progress_bar.setValue(0)
        self._match_worker.start()

    def _on_item_matched(self, index: int, record) -> None:
        item = self._model.item_at(index)
        item.status = MatchStatus.MATCHED
        item.metadata = record
        self._matched_records[index] = record
        self._model.update_row(index)

    def _on_item_failed(self, index: int, reason: str) -> None:
        item = self._model.item_at(index)
        item.status = MatchStatus.NO_MATCH
        item.note = reason
        self._model.update_row(index)
        self._log(f"{item.extracted.content_id}: {reason}")

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress_bar.setValue(int(done / total * 100))

    def _on_matching_finished(self) -> None:
        self.settings_panel.scan_button.setEnabled(True)
        self.settings_panel.run_button.setEnabled(bool(self._matched_records))
        self._log(f"Matched {len(self._matched_records)} item(s).")

    def _on_row_double_clicked(self, index) -> None:
        row = index.row()
        item = self._model.item_at(row)
        if item.status == MatchStatus.MATCHED:
            return

        dialog = MatchReviewDialog(
            self,
            item.primary_path.name,
            item.extracted.content_id,
            self._cache,
            self._client,
            genre_filter=self._settings.genre_filter(),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_record is not None:
            item.status = MatchStatus.MATCHED
            item.metadata = dialog.result_record
            self._matched_records[row] = dialog.result_record
            self._model.update_row(row)
            self.settings_panel.run_button.setEnabled(True)
            self._log(f"Manually resolved {dialog.result_content_id}.")

    def _start_run(self) -> None:
        library = self.settings_panel.library_edit.text().strip()
        if not library:
            QMessageBox.warning(self, "Missing folder", "Choose a library folder first.")
            return

        matched = [
            (index, self._model.item_at(index), record) for index, record in self._matched_records.items()
        ]
        sort_in_place = self.settings_panel.sort_in_place()
        enabled_categories = self.settings_panel.enabled_categories()

        self.settings_panel.run_button.setEnabled(False)
        self._dev_mode_dialog_shown_this_run = False
        self._log(f"Processing {len(matched)} item(s)...")
        self.progress_bar.setValue(0)

        self._execute_worker = ExecuteWorker(
            matched, Path(library), sort_in_place, enabled_categories, self._client
        )
        self._execute_worker.item_done.connect(self._on_item_done)
        self._execute_worker.item_error.connect(self._on_item_error)
        self._execute_worker.progress.connect(self._on_progress)
        self._execute_worker.finished_run.connect(self._on_run_finished)
        self._execute_worker.start()

    def _on_item_done(self, index: int, result) -> None:
        skipped = result.skipped_links
        self._log(
            f"{result.content_id}: sorted ({len(result.canonical_paths)} file(s)); "
            f"{len(skipped)} link(s) skipped."
        )
        self._model.update_row(index)

        permission_denied = any(
            not link_result.success and link_result.is_permission_error
            for link_result in result.link_results.values()
        )
        if permission_denied and not self._settings.dev_mode_dialog_acknowledged:
            self._settings.dev_mode_dialog_acknowledged = True
            self._settings.save(self._settings_path)
            if not self._dev_mode_dialog_shown_this_run:
                self._dev_mode_dialog_shown_this_run = True
                choice = show_symlink_permission_dialog(self)
                if choice == "abort" and self._execute_worker is not None:
                    self._execute_worker.request_cancel()
                    self._log("Stopping run at the user's request (symlink permission).")
        elif skipped:
            for link_path in skipped:
                self._log(f"  skipped link: {link_path}")

    def _on_item_error(self, index: int, message: str) -> None:
        item = self._model.item_at(index)
        self._log(f"{item.extracted.content_id}: ERROR {message}")

    def _on_run_finished(self) -> None:
        self.settings_panel.run_button.setEnabled(True)
        self._log("Done.")

    def closeEvent(self, event) -> None:
        self._save_settings()
        self._cache.close()
        self._client.close()
        super().closeEvent(event)
