from __future__ import annotations

from pathlib import Path

from javsorter.core.actress_identity import DecisionKind, ResolutionState
from javsorter.core.models import MetadataRecord
from javsorter.scraping.actress_registry import RegistryManager
from javsorter.scraping.identity_lookup import IdentityResolver
from javsorter.scraping.identity_store import IdentityDecisionStore


FIXTURE = Path(__file__).parent / "fixtures" / "registry" / "minimal.sql"


def _resolver(tmp_path):
    manager = RegistryManager(tmp_path / "registry")
    with FIXTURE.open(encoding="utf-8") as stream:
        manager.import_dump(stream, "fixture")
    return IdentityResolver(IdentityDecisionStore(tmp_path / "decisions.sqlite3"), manager)


def test_registry_repairs_missing_r18_cast(tmp_path):
    resolver = _resolver(tmp_path)
    record = MetadataRecord(content_id="ABC-1", title="Title", actresses=[])
    result = resolver.resolve(record, release_id="ABC-1")
    assert result.state is ResolutionState.RESOLVED
    assert result.eligible
    assert result.record.actresses == ["Alice Example", "Bob Example"]


def test_manual_correction_wins_over_registry(tmp_path):
    resolver = _resolver(tmp_path)
    resolver.decision_store.save_release_decision("ABC-1", kind=DecisionKind.CORRECTION, actresses=["Manual Name"])
    result = resolver.resolve(MetadataRecord("ABC-1", "Title", []), release_id="ABC-1")
    assert result.record.actresses == ["Manual Name"]
    assert result.provenance == "manual correction"


def test_unavailable_registry_holds_r18_baseline(tmp_path):
    resolver = IdentityResolver(
        IdentityDecisionStore(tmp_path / "decisions.sqlite3"), RegistryManager(tmp_path / "empty")
    )
    result = resolver.resolve(MetadataRecord("ABC-1", "Title", ["R18 Name"]), release_id="ABC-1")
    assert result.state is ResolutionState.NEEDS_REVIEW
    assert result.eligible is False
