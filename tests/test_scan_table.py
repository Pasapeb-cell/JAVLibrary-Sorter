from __future__ import annotations

from pathlib import Path

from javsorter.core.actress_identity import IdentityResolution, ResolutionState
from javsorter.core.id_extractor import extract_id
from javsorter.core.models import MatchStatus, MetadataRecord, ScanItem
from javsorter.gui.scan_table import ScanTableModel


def test_scan_table_exposes_actress_provenance_and_review_reason():
    item = ScanItem(
        [Path("ABC-1.mp4")],
        extract_id("ABC-1.mp4"),
        MatchStatus.REVIEW_REQUIRED,
        metadata=MetadataRecord("ABC-1", "Title", ["Alice Example"]),
        note="local actress registry unavailable",
        resolution=IdentityResolution(
            MetadataRecord("ABC-1", "Title", ["Alice Example"]),
            ResolutionState.NEEDS_REVIEW,
            "r18 baseline",
            reason="local actress registry unavailable",
        ),
    )
    model = ScanTableModel([item])
    assert model.data(model.index(0, 4)) == "Alice Example"
    assert model.data(model.index(0, 5)) == "r18 baseline"
    assert model.data(model.index(0, 6)) == "local actress registry unavailable"
