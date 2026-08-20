from __future__ import annotations

import re
from dataclasses import replace

from javsorter.core.models import MetadataRecord

# r18.dev returns promotional and technical tags mixed in with real genres,
# e.g. "JET Video 40% Off Sale", "Prestige Group Autumn Planning Festival",
# "Sample Video", "Hi-Def". Left alone they each become a category folder
# (and a <genre> in the NFO), burying the genres you actually browse by.

DEFAULT_BLOCKED_GENRES = (
    # Storefront flags rather than descriptions of the content.
    "Sample Video",
    "Exclusive Distribution",
    "Independent Works",
    "Download Only",
    "Streaming Only",
    "Mail Delivery",
    "Digital Mosaic",
    # Technical/format tags.
    "Hi-Def",
    "High-Definition",
    "Blu-ray",
    "4K",
    "VR Exclusive",
)

# Promotional campaigns are endlessly varied ("New Year's Eve Sale",
# "Autumn Planning Festival", ...), so match them by shape rather than
# trying to enumerate every one.
DEFAULT_BLOCKED_PATTERNS = (
    r"\d+%\s*off",
    r"\bsale\b",
    r"\bcampaign\b",
    r"\bfestival\b",
    r"\bcoupon\b",
    r"\bdiscount\b",
    r"\bbargain\b",
    r"limited\s+time",
    r"special\s+price",
)


class GenreFilter:
    """Drops promotional/technical tags from a genre list.

    Applied to the metadata record itself, so blocked tags are kept out of
    both the category folders and the NFO -- "40% Off Sale" is no more a
    genre in Jellyfin than it is on disk.
    """

    def __init__(
        self,
        use_defaults: bool = True,
        extra_blocked: list[str] | None = None,
        extra_patterns: list[str] | None = None,
    ):
        blocked = list(DEFAULT_BLOCKED_GENRES) if use_defaults else []
        blocked.extend(extra_blocked or [])
        self._blocked = {name.strip().casefold() for name in blocked if name.strip()}

        patterns = list(DEFAULT_BLOCKED_PATTERNS) if use_defaults else []
        patterns.extend(extra_patterns or [])
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns if p.strip()]

    def is_blocked(self, genre: str) -> bool:
        if genre.strip().casefold() in self._blocked:
            return True
        return any(pattern.search(genre) for pattern in self._patterns)

    def filter_genres(self, genres: list[str]) -> list[str]:
        return [genre for genre in genres if not self.is_blocked(genre)]

    def apply(self, record: MetadataRecord) -> MetadataRecord:
        kept = self.filter_genres(record.genres)
        if kept == record.genres:
            return record
        return replace(record, genres=kept)
