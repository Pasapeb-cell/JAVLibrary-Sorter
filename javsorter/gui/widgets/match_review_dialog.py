from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from javsorter.core.genre_filter import GenreFilter
from javsorter.core.models import MetadataRecord
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NetworkError, NoMatchError
from javsorter.scraping.lookup import lookup_metadata


class MatchReviewDialog(QDialog):
    """Lets the user type/correct a content ID and look it up immediately,
    for rows the automatic matcher couldn't resolve (no ID parsed, an
    ambiguous -C marker, or no match on r18.dev).

    The lookup runs synchronously on the GUI thread: it's a rare,
    single-item, user-initiated action, so a brief pause for the
    rate-limited request is an acceptable trade-off against the added
    complexity of another background worker for this one dialog.
    """

    def __init__(
        self,
        parent: QWidget,
        filename: str,
        guessed_id: str | None,
        cache: MetadataCache,
        client: ScraperClient,
        genre_filter: GenreFilter | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Resolve match")
        self._cache = cache
        self._client = client
        self._genre_filter = genre_filter
        self.result_record: MetadataRecord | None = None
        self.result_content_id: str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"File: {filename}"))
        layout.addWidget(QLabel("Content ID:"))
        self.id_edit = QLineEdit(guessed_id or "")
        layout.addWidget(self.id_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_look_up)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_look_up(self) -> None:
        content_id = self.id_edit.text().strip().upper()
        if not content_id:
            QMessageBox.warning(self, "Missing ID", "Enter a content ID first.")
            return

        try:
            record = lookup_metadata(
                self._cache, self._client, content_id, genre_filter=self._genre_filter
            )
        except NoMatchError:
            QMessageBox.warning(self, "No match", f"No metadata found for {content_id} on r18.dev.")
            return
        except NetworkError as exc:
            QMessageBox.critical(self, "Network error", str(exc))
            return

        self.result_record = record
        self.result_content_id = content_id
        self.accept()
