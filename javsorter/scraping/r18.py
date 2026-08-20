from __future__ import annotations

from typing import Any

from .client import ScraperClient
from .exceptions import NetworkError, NoMatchError

_DETAIL_URL_TEMPLATE = "https://r18.dev/videos/vod/movies/detail/-/dvd_id={content_id}/json"


def fetch_by_dvd_id(client: ScraperClient, content_id: str) -> dict[str, Any]:
    """Fetch raw metadata JSON for a content ID (e.g. "SSIS-001") from r18.dev.

    Raises NoMatchError if the ID doesn't exist (HTTP 404), NetworkError on
    any other non-2xx response.
    """
    url = _DETAIL_URL_TEMPLATE.format(content_id=content_id)
    response = client.get(url)

    if response.status_code == 404:
        raise NoMatchError(content_id)
    if not response.ok:
        raise NetworkError(f"{content_id}: HTTP {response.status_code}")

    return response.json()
