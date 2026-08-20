from __future__ import annotations

from pathlib import Path

from javsorter.core.models import MetadataRecord
from javsorter.organize.linker import LinkResult, create_symlink
from javsorter.organize.namer import sanitize_component

CATEGORY_ACTRESS = "Actress"
CATEGORY_GENRE = "Genre"
CATEGORY_STUDIO = "Studio"
CATEGORY_YEAR = "Year"

ALL_CATEGORIES = (CATEGORY_ACTRESS, CATEGORY_GENRE, CATEGORY_STUDIO, CATEGORY_YEAR)


def category_values(record: MetadataRecord, category: str) -> list[str]:
    if category == CATEGORY_ACTRESS:
        return record.actresses
    if category == CATEGORY_GENRE:
        return record.genres
    if category == CATEGORY_STUDIO:
        return [record.studio] if record.studio else []
    if category == CATEGORY_YEAR:
        if record.release_date:
            return [record.release_date.split("-")[0]]
        return []
    raise ValueError(f"Unknown category: {category}")


def build_category_links(
    library_root: Path,
    canonical_path: Path,
    record: MetadataRecord,
    enabled_categories: list[str],
) -> dict[str, LinkResult]:
    """Create one symlink per enabled-category value, pointing back at
    canonical_path (a video can have several actresses/genres, so it fans
    out to several folders). Returns every attempted link path -> result,
    including failures, so callers can summarize what was skipped.
    """
    results: dict[str, LinkResult] = {}
    for category in enabled_categories:
        for value in category_values(record, category):
            folder = library_root / category / sanitize_component(value)
            link_path = folder / canonical_path.name
            results[str(link_path)] = create_symlink(canonical_path, link_path)
    return results
