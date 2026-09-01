from __future__ import annotations

import sqlite3

import pytest

from javsorter.core.actress_identity import DecisionKind
from javsorter.scraping.identity_store import DecisionStoreUnavailable, IdentityDecisionStore


def test_correction_round_trips_and_normalizes_release_key(tmp_path):
    store = IdentityDecisionStore(tmp_path / "decisions.sqlite3")
    saved = store.save_release_decision(
        "abc-123-c", kind=DecisionKind.CORRECTION, actresses=["  Alice   Example  ", "Bob"]
    )
    assert saved.release_key == "ABC-123"
    assert store.get_release_decision("ABC-123") == saved
    store.close()

    reopened = IdentityDecisionStore(tmp_path / "decisions.sqlite3")
    assert reopened.get_release_decision("ABC-123-C").actresses == ("Alice Example", "Bob")
    reopened.close()


def test_fallback_can_explicitly_preserve_empty_list(tmp_path):
    store = IdentityDecisionStore(tmp_path / "decisions.sqlite3")
    decision = store.save_release_decision(
        "ABC-1", kind=DecisionKind.FALLBACK, actresses=[], captured_r18_actresses=[]
    )
    assert decision.is_fallback
    assert decision.actresses == ()
    store.close()


def test_correction_cannot_be_saved_without_an_actress(tmp_path):
    store = IdentityDecisionStore(tmp_path / "decisions.sqlite3")
    with pytest.raises(ValueError):
        store.save_release_decision("ABC-1", kind=DecisionKind.CORRECTION, actresses=[])
    store.close()


def test_alias_override_is_separate_from_release_decision(tmp_path):
    store = IdentityDecisionStore(tmp_path / "decisions.sqlite3")
    alias = store.save_alias_override("a1", "Alice Example", ["A. Example"])
    assert store.get_alias_override("a1") == alias
    assert store.get_release_decision("a1") is None
    store.close()


def test_atomic_correction_reuse_preserves_aliases(tmp_path):
    store = IdentityDecisionStore(tmp_path / "decisions.sqlite3")
    store.save_release_decision_with_aliases(
        "ABC-1",
        kind=DecisionKind.CORRECTION,
        actresses=["Alice Example"],
        stable_ids=["a1"],
        alias_overrides=[("a1", "Alice Example", ("A. Example",))],
    )
    alias = store.get_alias_override("a1")
    assert alias is not None
    assert alias.aliases == ("A. Example",)
    store.close()


def test_corrupt_store_is_unavailable_and_not_rebuilt(tmp_path):
    path = tmp_path / "decisions.sqlite3"
    path.write_bytes(b"not sqlite")
    store = IdentityDecisionStore(path)
    assert store.available is False
    with pytest.raises(DecisionStoreUnavailable):
        store.get_release_decision("ABC-1")
    assert path.read_bytes() == b"not sqlite"
