from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from javsorter.core.actress_identity import IdentityResolution


class MatchStatus(Enum):
    NO_ID = auto()
    AMBIGUOUS_ID = auto()
    ID_FOUND = auto()
    MATCHED = auto()
    MULTIPLE_CANDIDATES = auto()
    NO_MATCH = auto()
    REVIEW_REQUIRED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ExtractedId:
    raw_filename: str
    content_id: str | None
    studio: str | None
    number: str | None
    uncensored: bool
    part_label: str | None
    ambiguous_part_marker: bool
    high_confidence: bool

    @property
    def base_id(self) -> str | None:
        """content_id without an uncensored/part suffix, used to group multi-part releases."""
        if self.studio and self.number:
            return f"{self.studio}-{self.number}"
        return None


@dataclass
class MetadataRecord:
    content_id: str
    title: str
    actresses: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    studio: str | None = None
    release_date: str | None = None
    cover_url: str | None = None
    rating: float | None = None
    director: str | None = None
    runtime_minutes: int | None = None


@dataclass
class ScanItem:
    parts: list[Path]
    extracted: ExtractedId
    status: MatchStatus
    # Resolved part label for each entry in `parts`, same order/length.
    # Populated by the scanner, since disambiguating an ambiguous "-C"
    # marker into a genuine third part (vs. uncensored) depends on sibling
    # files and can't be re-derived from a single filename in isolation.
    part_labels: list[str | None] = field(default_factory=list)
    # Other files that resolved to the same content ID but aren't parts of
    # a multi-disc release. Deliberately left untouched by the organizer
    # rather than renamed into collisions -- surfaced for the user to sort
    # out, since only they know which copy to keep.
    duplicates: list[Path] = field(default_factory=list)
    metadata: MetadataRecord | None = None
    note: str | None = None
    # Identity resolution is kept alongside (not folded into) filename match
    # status so review-required rows can be displayed and edited safely.
    resolution: IdentityResolution | None = None

    @property
    def primary_path(self) -> Path:
        return self.parts[0]
