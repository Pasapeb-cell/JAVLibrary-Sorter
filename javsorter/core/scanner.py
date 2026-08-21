from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .id_extractor import extract_id
from .models import ExtractedId, MatchStatus, ScanItem

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".wmv", ".mov", ".ts", ".m2ts", ".flv", ".iso",
}


def find_video_files(
    source_folder: Path, should_cancel: Callable[[], bool] | None = None
) -> list[Path]:
    files = []
    for root, _dirs, names in os.walk(source_folder):
        if should_cancel is not None and should_cancel():
            break
        for name in names:
            if Path(name).suffix.lower() in VIDEO_EXTENSIONS:
                files.append(Path(root) / name)
    return files


def scan_folder(
    source_folder: Path, should_cancel: Callable[[], bool] | None = None
) -> list[ScanItem]:
    """Scan a folder for video files, extract content IDs, and group
    multi-part releases (same base ID, different -cd1/-cd2/-A/-B/-C files)
    into single ScanItems.

    `should_cancel` is polled during the walk so a scan over a slow network
    share can be interrupted; returns whatever was found so far.
    """
    files = find_video_files(Path(source_folder), should_cancel=should_cancel)
    extracted_by_path = {path: extract_id(path.name) for path in files}

    groups: dict[str, list[Path]] = {}
    for path, extracted in extracted_by_path.items():
        base_id = extracted.base_id
        key = base_id if base_id is not None else f"__no_id__::{path}"
        groups.setdefault(key, []).append(path)

    items: list[ScanItem] = []
    for paths in groups.values():
        extracted_list = [extracted_by_path[p] for p in paths]
        resolved = _resolve_ambiguous_markers(extracted_list)
        items.append(_build_item(paths, resolved))
    return items


def _resolve_ambiguous_markers(extracted_list: list[ExtractedId]) -> list[ExtractedId]:
    """If sibling -A/-B files exist for this base ID, a -C sibling is the
    third part of the split, not an uncensored marker.
    """
    has_ab_sibling = any(e.part_label in ("a", "b") for e in extracted_list)
    if not has_ab_sibling:
        return extracted_list

    resolved = []
    for extracted in extracted_list:
        if extracted.ambiguous_part_marker and extracted.uncensored:
            resolved.append(
                replace(
                    extracted,
                    content_id=extracted.base_id,
                    uncensored=False,
                    part_label="c",
                    ambiguous_part_marker=False,
                )
            )
        else:
            resolved.append(extracted)
    return resolved


def _build_item(paths: list[Path], resolved: list[ExtractedId]) -> ScanItem:
    representative = resolved[0]
    has_parts = any(e.part_label for e in resolved)

    if has_parts:
        ordered = sorted(zip(paths, resolved), key=lambda pair: pair[1].part_label or "")
    else:
        ordered = list(zip(paths, resolved))

    ordered_paths = [p for p, _ in ordered]
    ordered_labels = [e.part_label for _, e in ordered]

    duplicates: list[Path] = []
    note = None
    if not has_parts and len(ordered_paths) > 1:
        # Same ID, no part markers: these are competing copies, not discs
        # of one release. Renaming them all would collide, so keep the
        # largest as the real one and set the rest aside untouched.
        ordered_paths.sort(key=_file_size, reverse=True)
        duplicates = ordered_paths[1:]
        ordered_paths = ordered_paths[:1]
        ordered_labels = [None]
        note = (
            f"{len(duplicates)} other file(s) share this ID; keeping the largest. "
            "The rest are left where they are."
        )

    return ScanItem(
        parts=ordered_paths,
        extracted=representative,
        status=_status_for(representative),
        part_labels=ordered_labels,
        duplicates=duplicates,
        note=note,
    )


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _status_for(extracted: ExtractedId) -> MatchStatus:
    if extracted.content_id is None:
        return MatchStatus.NO_ID
    if extracted.ambiguous_part_marker:
        return MatchStatus.AMBIGUOUS_ID
    return MatchStatus.ID_FOUND
