"""Qt-free identity decisions shared by the matcher, GUI, and rescan paths."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum

from javsorter.core.models import MetadataRecord


class DecisionKind(str, Enum):
    CORRECTION = "correction"
    FALLBACK = "fallback"


class ResolutionState(str, Enum):
    RESOLVED = "resolved"
    NEEDS_REVIEW = "needs_review"
    FALLBACK_APPROVED = "fallback_approved"


@dataclass(frozen=True)
class ActressDecision:
    release_key: str
    kind: DecisionKind
    actresses: tuple[str, ...]
    stable_ids: tuple[str, ...] = ()
    captured_r18_actresses: tuple[str, ...] = ()
    snapshot_revision: str | None = None
    updated_at: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.kind is DecisionKind.FALLBACK

    @property
    def is_correction(self) -> bool:
        return self.kind is DecisionKind.CORRECTION


@dataclass(frozen=True)
class ActressAliasOverride:
    stable_id: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    snapshot_revision: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class IdentityResolution:
    """Effective metadata plus the explicit run-eligibility decision."""

    record: MetadataRecord
    state: ResolutionState
    provenance: str
    reason: str | None = None
    registry_revision: str | None = None
    stable_identity_candidates: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.state in (ResolutionState.RESOLVED, ResolutionState.FALLBACK_APPROVED)

    @property
    def effective_record(self) -> MetadataRecord:
        return self.record


def with_actresses(record: MetadataRecord, actresses: list[str] | tuple[str, ...]) -> MetadataRecord:
    """Return an overlay copy while leaving the raw metadata cache untouched."""
    return replace(record, actresses=list(actresses))


def canonical_release_key(content_id: str | None) -> str:
    """Normalize a release to the base ID used by R18 and the metadata cache."""
    value = (content_id or "").strip().upper()
    value = re.sub(r"\s+", "", value)
    return re.sub(r"-C$", "", value)


def normalize_actress_names(names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Trim names, reject blanks, and de-duplicate without reordering."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in names:
        value = " ".join(str(raw).split())
        if not value:
            raise ValueError("actress names cannot be blank")
        marker = value.casefold()
        if marker not in seen:
            seen.add(marker)
            normalized.append(value)
    return tuple(normalized)
