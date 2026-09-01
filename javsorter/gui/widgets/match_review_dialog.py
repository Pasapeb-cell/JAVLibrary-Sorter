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
from javsorter.core.actress_identity import (
    DecisionKind,
    IdentityResolution,
    ResolutionState,
    canonical_release_key,
    normalize_actress_names,
)
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
        self._owns_identity_store = False
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
        # If the user changed the release ID, refresh all metadata before
        # persisting a decision.  Keeping the old title/cover/genres under a
        # new ID would create an internally inconsistent NFO and folder.
        if (
            self.result_record is not None
            and canonical_release_key(content_id)
            != canonical_release_key(self.result_record.content_id)
        ):
            if not self._lookup_content_id(content_id):
                return
            QMessageBox.information(
                self,
                "Metadata refreshed",
                "The content ID changed, so metadata was refreshed. Review it and press Save again.",
            )
            return
        try:
            names = normalize_actress_names(self.actresses_edit.toPlainText().splitlines())
        except ValueError as exc:
            if self.fallback_checkbox.isChecked() and not self.actresses_edit.toPlainText().strip():
                names = ()
            else:
                QMessageBox.warning(self, "Invalid actresses", str(exc))
                return

        fallback = self.fallback_checkbox.isChecked()
        if fallback:
            captured = normalize_actress_names(self.result_record.actresses)
            if names != captured:
                QMessageBox.warning(
                    self,
                    "Fallback must match R18",
                    "An explicit fallback must preserve the captured R18 actress list. "
                    "Uncheck fallback to save an edited correction.",
                )
                self.fallback_checkbox.setChecked(False)
                return

        if fallback and not names:
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
            self._owns_identity_store = True
        try:
            kind = DecisionKind.FALLBACK if fallback else DecisionKind.CORRECTION
            reuse = (
                kind is DecisionKind.CORRECTION
                and self.reuse_identity_checkbox.isChecked()
                and self.result_resolution is not None
            )
            stable_ids = self.result_resolution.stable_identity_candidates if reuse and self.result_resolution else ()
            if reuse and len(stable_ids) != len(names):
                QMessageBox.warning(
                    self,
                    "Identity reuse unavailable",
                    "Keep the actress count and order unchanged when reusing registry identities.",
                )
                return
            if reuse:
                saved = self._identity_store.save_release_decision_with_aliases(
                    content_id,
                    kind=kind,
                    actresses=names,
                    stable_ids=stable_ids,
                    captured_r18_actresses=self.result_record.actresses,
                    alias_overrides=[(stable_id, name, ()) for stable_id, name in zip(stable_ids, names)],
                )
            else:
                saved = self._identity_store.save_release_decision(
                    content_id,
                    kind=kind,
                    actresses=names,
                    captured_r18_actresses=self.result_record.actresses,
                )
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
        self._lookup_content_id(content_id)

    def _lookup_content_id(self, content_id: str) -> bool:
        try:
            record = lookup_metadata(self._cache, self._client, content_id)
            resolution = (
                self._resolver.resolve(record, release_id=content_id, genre_filter=self._genre_filter)
                if self._resolver is not None
                else None
            )
        except NoMatchError:
            QMessageBox.warning(self, "No match", f"No metadata found for {content_id} on r18.dev.")
            return False
        except NetworkError as exc:
            QMessageBox.critical(self, "Network error", str(exc))
            return False
        except DecisionStoreUnavailable as exc:
            QMessageBox.critical(self, "Decision store unavailable", str(exc))
            return False
        self._set_record(resolution.record if resolution is not None else record, resolution)
        return True

    def closeEvent(self, event) -> None:
        if self._owns_identity_store and self._identity_store is not None:
            self._identity_store.close()
            self._identity_store = None
        super().closeEvent(event)
