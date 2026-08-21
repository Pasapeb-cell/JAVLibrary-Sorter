from __future__ import annotations

from pathlib import Path

from javsorter.organize.longpath import extended
from javsorter.scraping.client import ScraperClient


def download_cover(client: ScraperClient, cover_url: str, destination: Path) -> bool:
    """Download the cover image to destination.

    Returns False on any failure (bad response, non-image content type,
    network error) instead of raising, so a missing cover degrades to
    "NFO written, no cover" rather than aborting the whole item.
    """
    try:
        response = client.get(cover_url)
        if not response.ok:
            return False
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            return False
        Path(extended(destination.parent)).mkdir(parents=True, exist_ok=True)
        Path(extended(destination)).write_bytes(response.content)
        return True
    except Exception:
        return False
