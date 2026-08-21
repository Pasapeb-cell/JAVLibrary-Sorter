from __future__ import annotations

import shutil
from pathlib import Path

from javsorter.organize.longpath import extended


def move_file(source: Path, destination: Path) -> Path:
    """Move source to destination.

    No-ops if they're already the same file (e.g. sort-in-place with a
    filename that was already clean). If a different file already exists
    at destination, appends " (2)", " (3)", ... rather than overwriting it.
    """
    if source.resolve() == destination.resolve():
        return destination

    Path(extended(destination.parent)).mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination = _next_available_name(destination)

    shutil.move(str(extended(source)), str(extended(destination)))
    return destination


def _next_available_name(path: Path) -> Path:
    counter = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    return candidate
