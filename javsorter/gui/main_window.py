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
from javsorter.config.paths import log_dir as default_log_dir
from javsorter.config.paths import runs_dir as default_runs_dir
from javsorter.config.paths import settings_path as default_settings_path
from javsorter.config.settings import Settings
from javsorter.core.models import MatchStatus
from javsorter.logging_setup import (
    QtLogHandler,
    attach_qt_handler,
    configure_file_logging,
    detach_qt_handler,
    get_logger,
)
from javsorter.organize import journal as journal_module
from javsorter.gui.scan_table import ScanTableModel
from javsorter.gui.settings_panel import SettingsPanel
from javsorter.gui.widgets.dev_mode_dialog import show_symlink_permission_dialog
from javsorter.gui.widgets.genre_blocklist_dialog import GenreBlocklistDialog
from javsorter.gui.widgets.match_review_dialog import MatchReviewDialog
from javsorter.gui.workers import ExecuteWorker, MatchWorker, RescanWorker, ScanWorker
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import ScrapeError
from javsorter.scraping.lookup import lookup_for_item


class MainWindow(QMainWindow):
    def __init__(
        self,
        cache_path: Path | None = None,
        settings_path: Path | None = None,
        runs_dir: Path | None = None,
        log_dir: Path | None = None,
    ):
        super().__init__()
        self.setWindowTitle("JAVLibrary Sorter")
        self.resize(900, 600)

        self._settings_path = settings_path or default_settings_path()
        self._settings = Settings.load(self._settings_path)
        self._runs_dir = runs_dir or default_runs_dir()

        self._log_path = configure_file_logging(log_dir or default_log_dir())
        self._logger = get_logger("gui")
        self._qt_log_handler = QtLogHandler()
        self._qt_log_handler.signals.message.connect(self._on_log_message)
        attach_qt_handler(self._qt_log_handler)

        self._client = ScraperClient()
        self._cache = MetadataCache(cache_path or default_cache_path())
        self._model = ScanTableModel()
        self._matched_records: dict[int, object] = {}
        self._scan_worker: ScanWorker | None = None
        self._match_worker: MatchWorker | None = None
        self._execute_worker: ExecuteWorker | None = None
        self._rescan_worker: RescanWorker | None = None
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
        self.settings_panel.stop_button.clicked.connect(self._stop_current_worker)
        self.settings_panel.rescan_button.clicked.connect(self._start_rescan)
        self.settings_panel.undo_button.clicked.connect(self._undo_last_run)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        self._apply_settings()

        if self._cache.recovered_from_corruption:
            self._log(
                "The metadata cache was unreadable and has been reset "
                "(the old file was kept alongside it with a .corrupt suffix). "
                "Lookups will be re-fetched."
            )

    def _log(self, message: str) -> None:
        """Log to the file and, via the Qt handler, to the panel."""
        self._logger.info(message)

    def _on_log_message(self, message: str, level: int) -> None:
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

    def _active_worker(self):
        for worker in (
            self._scan_worker,
            self._match_worker,
            self._execute_worker,
            self._rescan_worker,
        ):
            if worker is not None and worker.isRunning():
                return worker
        return None

    def _start_rescan(self) -> None:
        library = self.settings_panel.library_edit.text().strip()
        if not library:
            QMessageBox.warning(self, "Missing folder", "Choose a library folder first.")
            return
        if not Path(library).exists():
            QMessageBox.warning(self, "No such folder", f"{library} doesn't exist.")
            return

        self._set_busy(True)
        self.progress_bar.setValue(0)
        self._log(f"Rescanning {library}...")

        self._rescan_worker = RescanWorker(
            Path(library),
            self.settings_panel.enabled_categories(),
            self._cache,
            self._client,
            genre_filter=self._settings.genre_filter(),
            runs_dir=self._runs_dir,
        )
        self._rescan_worker.progress.connect(self._on_progress)
        self._rescan_worker.finished_rescan.connect(self._on_rescan_finished)
        self._rescan_worker.start()

    def _on_rescan_finished(self, report, journal_path) -> None:
        self._set_busy(False)
        self.settings_panel.run_button.setEnabled(bool(self._matched_records))

        if report is None:
            self._log("Rescan failed; see the log file for details.")
            return

        self._log(
            f"Rescan of {report.releases} release(s): "
            f"{report.links_created} link(s) added, "
            f"{report.stale_links_removed} stale removed, "
            f"{report.broken_links_removed} broken removed, "
            f"{report.nfos_written} NFO(s) written, "
            f"{report.covers_downloaded} cover(s) fetched."
        )
        if report.unmatched:
            self._log(f"  no metadata for: {', '.join(report.unmatched)} (left untouched)")
        for failure in report.failures:
            self._log(f"  {failure}")
        if journal_path is not None:
            self._log("This rescan can be reversed with 'Undo last run'.")

    def _stop_current_worker(self) -> None:
        worker = self._active_worker()
        if worker is None:
            return
        worker.request_cancel()
        self.settings_panel.stop_button.setEnabled(False)
        self._log("Stopping after the current item...")

    def _set_busy(self, busy: bool) -> None:
        self.settings_panel.scan_button.setEnabled(not busy)
        self.settings_panel.stop_button.setEnabled(busy)
        self.settings_panel.undo_button.setEnabled(not busy)
        self.settings_panel.rescan_button.setEnabled(not busy)
        if busy:
            self.settings_panel.run_button.setEnabled(False)

    def _undo_last_run(self) -> None:
        journal_path = journal_module.latest_journal(self._runs_dir)
        if journal_path is None:
            QMessageBox.information(self, "Nothing to undo", "No previous run was recorded.")
            return

        try:
            run_journal = journal_module.RunJournal.load(journal_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Can't read that run", str(exc))
            return

        confirmed = QMessageBox.question(
            self,
            "Undo last run",
            f"Undo the run from {run_journal.started_at}?\n\n"
            f"This reverses {len(run_journal.entries)} recorded action(s): "
            "category links are removed, generated NFO/cover files are deleted, "
            "and moved videos go back where they came from.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        report = journal_module.undo(run_journal)
        self._log(
            f"Undo complete: {report.files_restored} file(s) moved back, "
            f"{report.links_removed} link(s) removed, {report.files_removed} generated file(s) deleted."
        )
        for failure in report.failures:
            self._log(f"  could not undo: {failure}")

        # The run is spent either way -- keep it only if part of it survived,
        # so the button doesn't offer to redo an undo that fully succeeded.
        if not report.failures:
            journal_path.unlink(missing_ok=True)

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

        self._set_busy(True)
        self._matched_records = {}
        self._log(f"Scanning {source}...")

        self._scan_worker = ScanWorker(Path(source))
        self._scan_worker.finished_scan.connect(self._on_scanned)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Scan failed", message)

    def _on_scanned(self, items) -> None:
        self._model.set_items(items)
        self._log(f"Found {len(items)} item(s). Looking up metadata...")

        for item in items:
            if item.duplicates:
                self._log(f"{item.extracted.content_id}: {item.note}")
                for duplicate in item.duplicates:
                    self._log(f"  left alone: {duplicate}")

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
        self._set_busy(False)
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

        self._set_busy(True)
        self._dev_mode_dialog_shown_this_run = False
        self._log(f"Processing {len(matched)} item(s)...")
        self.progress_bar.setValue(0)

        self._execute_worker = ExecuteWorker(
            matched,
            Path(library),
            sort_in_place,
            enabled_categories,
            self._client,
            runs_dir=self._runs_dir,
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

    def _on_run_finished(self, journal_path) -> None:
        self._set_busy(False)
        self.settings_panel.run_button.setEnabled(True)
        if journal_path is not None:
            self._log("Done. This run can be reversed with 'Undo last run'.")
        else:
            self._log("Done.")

    def closeEvent(self, event) -> None:
        worker = self._active_worker()
        if worker is not None:
            worker.request_cancel()
            worker.wait(5000)
        self._save_settings()
        self._cache.close()
        self._client.close()
        detach_qt_handler(self._qt_log_handler)
        super().closeEvent(event)
