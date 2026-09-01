from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from javsorter.config.paths import identity_store_path
from javsorter.core.actress_identity import DecisionKind, IdentityResolution, ResolutionState, normalize_actress_names
from javsorter.core.genre_filter import GenreFilter
from javsorter.core.models import MetadataRecord
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NetworkError, NoMatchError
from javsorter.scraping.identity_lookup import IdentityResolver
from javsorter.scraping.identity_store import DecisionStoreUnavailable, IdentityDecisionStore
from javsorter.scraping.lookup import lookup_metadata


class MatchReviewDialog(QDialog):
    """Review a matched or held row and persist an explicit actress decision."""

    def __init__(
        self,
        parent: QWidget,
        filename: str,
        guessed_id: str | None,
        cache: MetadataCache,
        client: ScraperClient,
        genre_filter: GenreFilter | None = None,
        *,
        record: MetadataRecord | None = None,
        resolution: IdentityResolution | None = None,
        resolver: IdentityResolver | None = None,
        identity_store: IdentityDecisionStore | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Review metadata")
        self._cache = cache
        self._client = client
        self._genre_filter = genre_filter
        self._resolver = resolver
        self._identity_store = identity_store
        self.result_record: MetadataRecord | None = record
        self.result_resolution: IdentityResolution | None = resolution
        self.result_content_id: str | None = guessed_id

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"File: {filename}"))
        layout.addWidget(QLabel("Content ID:"))
        self.id_edit = QLineEdit(guessed_id or "")
        layout.addWidget(self.id_edit)
        layout.addWidget(QLabel("Actresses (one per line, in credit order):"))
        self.actresses_edit = QPlainTextEdit()
        self.actresses_edit.setAccessibleName("Actresses")
        layout.addWidget(self.actresses_edit)
        self.fallback_checkbox = QCheckBox("Approve the current R18 list as an explicit fallback")
        self.fallback_checkbox.setAccessibleName("Approve R18 fallback")
        layout.addWidget(self.fallback_checkbox)
        self.reuse_identity_checkbox = QCheckBox(
            "Reuse this correction for the recognized actress identities"
        )
        self.reuse_identity_checkbox.setAccessibleName("Reuse actress identity correction")
        self.reuse_identity_checkbox.setEnabled(bool(resolution and resolution.stable_identity_candidates))
        layout.addWidget(self.reuse_identity_checkbox)
        self.provenance_label = QLabel()
        layout.addWidget(self.provenance_label)

        if record is not None:
            self._set_record(record, resolution)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_record(self, record: MetadataRecord, resolution: IdentityResolution | None) -> None:
        self.result_record = record
        self.result_resolution = resolution
        self.result_content_id = record.content_id
        self.actresses_edit.setPlainText("\n".join(record.actresses))
        if resolution is not None:
            self.provenance_label.setText(
                f"Source: {resolution.provenance}"
                + (f" — {resolution.reason}" if resolution.reason else "")
            )

    def _on_save(self) -> None:
        if self.result_record is None:
            self._on_look_up()
            return
        content_id = self.id_edit.text().strip().upper()
        if not content_id:
            QMessageBox.warning(self, "Missing ID", "Enter a content ID first.")
            return
        try:
            names = normalize_actress_names(self.actresses_edit.toPlainText().splitlines())
        except ValueError as exc:
            if self.fallback_checkbox.isChecked() and not self.actresses_edit.toPlainText().strip():
                names = ()
            else:
                QMessageBox.warning(self, "Invalid actresses", str(exc))
                return

        if self.fallback_checkbox.isChecked() and not names:
            confirmation = QMessageBox.question(
                self,
                "Approve empty actress list?",
                "This release will remain eligible with no actress folders. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                return

        if self._identity_store is None:
            self._identity_store = IdentityDecisionStore(identity_store_path())
        try:
            kind = DecisionKind.FALLBACK if self.fallback_checkbox.isChecked() else DecisionKind.CORRECTION
            saved = self._identity_store.save_release_decision(
                content_id,
                kind=kind,
                actresses=names,
                captured_r18_actresses=self.result_record.actresses,
            )
            if (
                kind is DecisionKind.CORRECTION
                and self.reuse_identity_checkbox.isChecked()
                and self.result_resolution is not None
            ):
                for stable_id, name in zip(self.result_resolution.stable_identity_candidates, names):
                    self._identity_store.save_alias_override(stable_id, name, snapshot_revision=saved.snapshot_revision)
        except (DecisionStoreUnavailable, OSError, ValueError) as exc:
            QMessageBox.critical(self, "Can't save decision", str(exc))
            return

        self.result_record = MetadataRecord(
            content_id=content_id,
            title=self.result_record.title,
            actresses=list(names),
            genres=list(self.result_record.genres),
            studio=self.result_record.studio,
            release_date=self.result_record.release_date,
            cover_url=self.result_record.cover_url,
            rating=self.result_record.rating,
            director=self.result_record.director,
            runtime_minutes=self.result_record.runtime_minutes,
        )
        self.result_content_id = content_id
        self.result_resolution = IdentityResolution(
            self.result_record,
            ResolutionState.FALLBACK_APPROVED if kind is DecisionKind.FALLBACK else ResolutionState.RESOLVED,
            "explicit R18 fallback" if kind is DecisionKind.FALLBACK else "manual correction",
            registry_revision=saved.snapshot_revision,
        )
        self.accept()

    def _on_look_up(self) -> None:
        """Compatibility and first step for unresolved-ID review."""
        content_id = self.id_edit.text().strip().upper()
        if not content_id:
            QMessageBox.warning(self, "Missing ID", "Enter a content ID first.")
            return
        try:
            record = lookup_metadata(self._cache, self._client, content_id)
        except NoMatchError:
            QMessageBox.warning(self, "No match", f"No metadata found for {content_id} on r18.dev.")
            return
        except NetworkError as exc:
            QMessageBox.critical(self, "Network error", str(exc))
            return
        self._set_record(record, None)
