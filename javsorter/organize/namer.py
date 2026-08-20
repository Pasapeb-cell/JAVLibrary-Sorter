from __future__ import annotations

import re
from pathlib import Path

_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*]')


def sanitize_component(name: str) -> str:
    """Make a string safe to use as a single Windows path component, e.g.
    a genre like "Threesome / Foursome" containing a path separator.
    """
    cleaned = _ILLEGAL_CHARS_RE.sub("_", name)
    cleaned = cleaned.strip(" .")
    return cleaned or "_"


def library_filename(content_id: str, extension: str, part_label: str | None = None) -> str:
    """Canonical video filename for one file of a (possibly multi-part) release."""
    if part_label:
        return f"{content_id}-{part_label}{extension}"
    return f"{content_id}{extension}"


def library_path(library_root: Path, content_id: str) -> Path:
    """Folder for one release inside the Library, e.g. Library/ABC-123/."""
    return library_root / sanitize_component(content_id)


def nfo_filename(content_id: str) -> str:
    """Kodi pairs one shared .nfo per release, never per multi-CD part."""
    return f"{content_id}.nfo"


def cover_filename(content_id: str) -> str:
    return f"{content_id}-thumb.jpg"
