from __future__ import annotations

from typing import Any

from javsorter.core.models import MetadataRecord

# r18.dev's JSON shape isn't consistent across every title (observed:
# fields like "dvd_id", "gallery", "channels" are sometimes entirely absent,
# and image URLs can be a blank placeholder like " " with the real URL under
# an alternate key such as "large2"), so every field here is read
# defensively rather than assumed present.


def parse_detail(data: dict[str, Any], requested_id: str) -> MetadataRecord:
    """Convert a raw r18.dev detail JSON payload into a MetadataRecord.

    `requested_id` (the content ID we looked up, e.g. "SSIS-001") is used as
    the canonical content_id whenever the payload's own "dvd_id" field is
    missing, since some entries omit it.
    """
    content_id = (data.get("dvd_id") or requested_id).upper()

    release_date = data.get("release_date")
    if release_date:
        release_date = release_date.split(" ")[0]

    maker = data.get("maker") or {}
    cover_url = _extract_cover_url(data)

    return MetadataRecord(
        content_id=content_id,
        title=data.get("title") or "",
        actresses=[a["name"] for a in data.get("actresses") or [] if a.get("name")],
        genres=[c["name"] for c in data.get("categories") or [] if c.get("name")],
        studio=maker.get("name"),
        release_date=release_date,
        cover_url=cover_url,
        rating=data.get("rating"),
        director=data.get("director"),
        runtime_minutes=data.get("runtime_minutes"),
    )


def _extract_cover_url(data: dict[str, Any]) -> str | None:
    images = data.get("images") or {}
    candidates = []
    for image_key in ("cover_image", "jacket_image"):
        image = images.get(image_key) or {}
        for size_key in ("large", "large2", "medium", "small"):
            candidates.append(image.get(size_key))

    gallery = data.get("gallery") or []
    if gallery:
        candidates.append(gallery[0].get("large"))

    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return None
