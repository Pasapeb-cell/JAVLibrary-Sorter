"""Qt-free identity decisions shared by the matcher, GUI, and rescan paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class DecisionKind(str, Enum):
    CORRECTION = "correction"
    FALLBACK = "fallback"


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
