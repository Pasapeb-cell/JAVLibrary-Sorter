from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from javsorter.core.models import MetadataRecord, ScanItem
from javsorter.organize import category_builder, namer
from javsorter.organize.cover_downloader import download_cover
from javsorter.organize.filemover import move_file
from javsorter.organize.linker import LinkResult
from javsorter.organize.nfo_writer import write_nfo
from javsorter.scraping.client import ScraperClient


@dataclass
class ProcessResult:
    content_id: str
    canonical_paths: list[Path] = field(default_factory=list)
    nfo_written: bool = False
    cover_downloaded: bool = False
    link_results: dict[str, LinkResult] = field(default_factory=dict)

    @property
    def skipped_links(self) -> list[str]:
        return [path for path, result in self.link_results.items() if not result.success]


def process_item(
    item: ScanItem,
    record: MetadataRecord,
    library_root: Path,
    sort_in_place: bool,
    enabled_categories: list[str],
    client: ScraperClient,
) -> ProcessResult:
    """Move/rename the file(s), write NFO + cover, and fan out category
    symlinks for one matched ScanItem. Both sort-in-place and import modes
    converge here once the canonical path is decided.
    """
    result = ProcessResult(content_id=record.content_id)

    canonical_paths = [
        move_file(
            source_path,
            _destination_for(source_path, record.content_id, part_label, library_root, sort_in_place),
        )
        for source_path, part_label in zip(item.parts, item.part_labels)
    ]
    result.canonical_paths = canonical_paths

    primary = canonical_paths[0]
    nfo_path = primary.with_name(namer.nfo_filename(record.content_id))
    cover_path = primary.with_name(namer.cover_filename(record.content_id))

    write_nfo(record, nfo_path, cover_filename=cover_path.name if record.cover_url else None)
    result.nfo_written = True

    if record.cover_url:
        result.cover_downloaded = download_cover(client, record.cover_url, cover_path)

    for canonical_path in canonical_paths:
        result.link_results.update(
            category_builder.build_category_links(library_root, canonical_path, record, enabled_categories)
        )

    return result


def _destination_for(
    source_path: Path,
    content_id: str,
    part_label: str | None,
    library_root: Path,
    sort_in_place: bool,
) -> Path:
    filename = namer.library_filename(content_id, source_path.suffix, part_label)
    if sort_in_place:
        return source_path.with_name(filename)
    return namer.library_path(library_root, content_id) / filename
