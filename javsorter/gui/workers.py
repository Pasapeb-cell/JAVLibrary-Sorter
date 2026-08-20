from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from javsorter.core.genre_filter import GenreFilter
from javsorter.core.models import MatchStatus, ScanItem
from javsorter.core.scanner import scan_folder
from javsorter.organize.pipeline import process_item
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NetworkError, NoMatchError
from javsorter.scraping.lookup import lookup_for_item


class ScanWorker(QThread):
    finished_scan = Signal(list)  # list[ScanItem]
    failed = Signal(str)

    def __init__(self, source_folder: Path):
        super().__init__()
        self._source_folder = source_folder

    def run(self) -> None:
        try:
            items = scan_folder(self._source_folder)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_scan.emit(items)


class MatchWorker(QThread):
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
        for done, (index, item) in enumerate(lookupable, start=1):
            try:
                record = lookup_for_item(
                    self._cache, self._client, item.extracted, genre_filter=self._genre_filter
                )
                self.item_matched.emit(index, record)
            except NoMatchError:
                self.item_failed.emit(index, "No match found on r18.dev")
            except NetworkError as exc:
                self.item_failed.emit(index, str(exc))
            self.progress.emit(done, total)
        self.finished_matching.emit()


class ExecuteWorker(QThread):
    """Runs organize.pipeline.process_item for every matched row."""

    item_done = Signal(int, object)  # row index, ProcessResult
    item_error = Signal(int, str)
    progress = Signal(int, int)
    finished_run = Signal()

    def __init__(
        self,
        matched: list[tuple[int, ScanItem, object]],
        library_root: Path,
        sort_in_place: bool,
        enabled_categories: list[str],
        client: ScraperClient,
    ):
        super().__init__()
        self._matched = matched
        self._library_root = library_root
        self._sort_in_place = sort_in_place
        self._enabled_categories = enabled_categories
        self._client = client
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Cooperative cancellation: finishes the item in progress, then
        stops before starting the next one.
        """
        self._cancel_requested = True

    def run(self) -> None:
        total = len(self._matched)
        for done, (index, item, record) in enumerate(self._matched, start=1):
            if self._cancel_requested:
                break
            try:
                result = process_item(
                    item,
                    record,
                    self._library_root,
                    self._sort_in_place,
                    self._enabled_categories,
                    self._client,
                )
                self.item_done.emit(index, result)
            except OSError as exc:
                self.item_error.emit(index, str(exc))
            self.progress.emit(done, total)
        self.finished_run.emit()
