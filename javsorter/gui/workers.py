from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from javsorter.core.genre_filter import GenreFilter
from javsorter.core.id_extractor import extract_id
from javsorter.core.models import MatchStatus, ScanItem
from javsorter.core.scanner import scan_folder
from javsorter.logging_setup import get_logger
from javsorter.organize.journal import RunJournal
from javsorter.organize.pipeline import process_item
from javsorter.organize.rescan import rescan_library
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NoMatchError, ScrapeError
from javsorter.scraping.lookup import lookup_for_item

logger = get_logger("workers")


class CancellableWorker(QThread):
    """Base for workers the user can stop from the GUI.

    Cancellation is cooperative: the current item finishes, then the loop
    stops before the next one.
    """

    def __init__(self):
        super().__init__()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    @property
    def cancelled(self) -> bool:
        return self._cancel_requested


class ScanWorker(CancellableWorker):
    finished_scan = Signal(list)  # list[ScanItem]
    failed = Signal(str)

    def __init__(self, source_folder: Path):
        super().__init__()
        self._source_folder = source_folder

    def run(self) -> None:
        try:
            items = scan_folder(self._source_folder, should_cancel=lambda: self._cancel_requested)
        except Exception as exc:
            # An escaping exception would kill the thread without ever
            # emitting, leaving the GUI's buttons disabled for good.
            logger.exception("Scan failed")
            self.failed.emit(str(exc))
            return
        logger.info("Scanned %s: %d item(s)", self._source_folder, len(items))
        self.finished_scan.emit(items)


class MatchWorker(CancellableWorker):
    """Looks up metadata for every ID_FOUND/AMBIGUOUS_ID item, checking the
    local cache before hitting the rate-limited network client.
    """

    item_matched = Signal(int, object)  # row index, MetadataRecord
    item_failed = Signal(int, str)  # row index, reason
    progress = Signal(int, int)  # done, total
    finished_matching = Signal()

    def __init__(
        self,
        items: list[ScanItem],
        cache: MetadataCache,
        client: ScraperClient,
        genre_filter: GenreFilter | None = None,
    ):
        super().__init__()
        self._items = items
        self._cache = cache
        self._client = client
        self._genre_filter = genre_filter

    def run(self) -> None:
        lookupable = [
            (index, item)
            for index, item in enumerate(self._items)
            if item.status in (MatchStatus.ID_FOUND, MatchStatus.AMBIGUOUS_ID)
        ]
        total = len(lookupable)
        try:
            for done, (index, item) in enumerate(lookupable, start=1):
                if self._cancel_requested:
                    logger.info("Metadata lookup cancelled after %d/%d", done - 1, total)
                    break
                content_id = item.extracted.content_id
                try:
                    record = lookup_for_item(
                        self._cache, self._client, item.extracted, genre_filter=self._genre_filter
                    )
                    logger.info("Matched %s: %s", content_id, record.title)
                    self.item_matched.emit(index, record)
                except NoMatchError:
                    logger.warning("No match for %s", content_id)
                    self.item_failed.emit(index, "No match found on r18.dev")
                except ScrapeError as exc:
                    logger.error("Lookup failed for %s: %s", content_id, exc)
                    self.item_failed.emit(index, str(exc))
                except Exception as exc:
                    # One bad item must not take down the whole run.
                    logger.exception("Unexpected error looking up %s", content_id)
                    self.item_failed.emit(index, f"Unexpected error: {exc}")
                self.progress.emit(done, total)
        finally:
            # Always emitted, so the GUI re-enables its buttons even if
            # something above went unexpectedly wrong.
            self.finished_matching.emit()


class RescanWorker(CancellableWorker):
    """Brings an already-sorted library back in line with current settings
    and metadata, without moving or deleting any videos.
    """

    progress = Signal(int, int)
    finished_rescan = Signal(object, object)  # RescanReport, journal path or None

    def __init__(
        self,
        library_root: Path,
        enabled_categories: list[str],
        cache: MetadataCache,
        client: ScraperClient,
        genre_filter: GenreFilter | None = None,
        runs_dir: Path | None = None,
    ):
        super().__init__()
        self._library_root = library_root
        self._enabled_categories = enabled_categories
        self._cache = cache
        self._client = client
        self._genre_filter = genre_filter
        self._runs_dir = runs_dir

    def run(self) -> None:
        journal = RunJournal(library_root=str(self._library_root))
        journal_path = None
        report = None
        try:
            report = rescan_library(
                self._library_root,
                self._enabled_categories,
                self._resolve,
                self._client,
                journal=journal,
                should_cancel=lambda: self._cancel_requested,
                progress=lambda done, total: self.progress.emit(done, total),
            )
        except Exception:
            logger.exception("Rescan failed")
        finally:
            if self._runs_dir is not None and not journal.is_empty():
                try:
                    journal_path = journal.save(self._runs_dir)
                except OSError:
                    logger.exception("Could not save the rescan journal")
            self.finished_rescan.emit(report, journal_path)

    def _resolve(self, content_id: str):
        extracted = extract_id(f"{content_id}.mp4")
        return lookup_for_item(
            self._cache, self._client, extracted, genre_filter=self._genre_filter
        )


class ExecuteWorker(CancellableWorker):
    """Runs organize.pipeline.process_item for every matched row."""

    item_done = Signal(int, object)  # row index, ProcessResult
    item_error = Signal(int, str)
    progress = Signal(int, int)
    finished_run = Signal(object)  # Path to the saved journal, or None

    def __init__(
        self,
        matched: list[tuple[int, ScanItem, object]],
        library_root: Path,
        sort_in_place: bool,
        enabled_categories: list[str],
        client: ScraperClient,
        runs_dir: Path | None = None,
    ):
        super().__init__()
        self._matched = matched
        self._library_root = library_root
        self._sort_in_place = sort_in_place
        self._enabled_categories = enabled_categories
        self._client = client
        self._runs_dir = runs_dir

    def run(self) -> None:
        total = len(self._matched)
        journal = RunJournal(library_root=str(self._library_root))
        journal_path = None
        try:
            for done, (index, item, record) in enumerate(self._matched, start=1):
                if self._cancel_requested:
                    logger.info("Run cancelled after %d/%d item(s)", done - 1, total)
                    break
                try:
                    result = process_item(
                        item,
                        record,
                        self._library_root,
                        self._sort_in_place,
                        self._enabled_categories,
                        self._client,
                        journal=journal,
                    )
                    logger.info(
                        "Organized %s: %d file(s), %d link(s), %d skipped",
                        result.content_id,
                        len(result.canonical_paths),
                        len(result.link_results) - len(result.skipped_links),
                        len(result.skipped_links),
                    )
                    self.item_done.emit(index, result)
                except Exception as exc:
                    # Keep going: a failure on one release (locked file,
                    # bad path) shouldn't abandon the rest of the batch.
                    logger.exception("Failed to organize item %d", index)
                    self.item_error.emit(index, str(exc))
                self.progress.emit(done, total)
        finally:
            # Save whatever was done, even on cancel or error -- a partial
            # run is exactly the case where undo matters most.
            if self._runs_dir is not None and not journal.is_empty():
                try:
                    journal_path = journal.save(self._runs_dir)
                    logger.info("Run journal saved to %s", journal_path)
                except OSError:
                    logger.exception("Could not save the run journal")
            self.finished_run.emit(journal_path)
