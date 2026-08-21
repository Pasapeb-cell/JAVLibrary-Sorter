from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from javsorter.core.models import MetadataRecord, ScanItem
from javsorter.organize import category_builder, namer
from javsorter.organize.cover_downloader import download_cover
from javsorter.organize.filemover import move_file
from javsorter.organize.journal import RunJournal
from javsorter.organize.linker import LinkResult
from javsorter.organize.nfo_writer import write_nfo
from javsorter.organize.plan import destination_for
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
    journal: RunJournal | None = None,
) -> ProcessResult:
    """Move/rename the file(s), write NFO + cover, and fan out category
    symlinks for one matched ScanItem. Both sort-in-place and import modes
    converge here once the canonical path is decided.

    Every reversible action is recorded in `journal` (when given) so the
    whole run can be undone later.
    """
    result = ProcessResult(content_id=record.content_id)

    canonical_paths = []
    for source_path, part_label in zip(item.parts, item.part_labels):
        destination = _destination_for(
            source_path, record.content_id, part_label, library_root, sort_in_place
        )
        moved_to = move_file(source_path, destination)
        canonical_paths.append(moved_to)
        if journal is not None:
            journal.record_move(source_path, moved_to)
    result.canonical_paths = canonical_paths

    primary = canonical_paths[0]
    nfo_path = primary.with_name(namer.nfo_filename(record.content_id))
    cover_path = primary.with_name(namer.cover_filename(record.content_id))

    nfo_existed = nfo_path.exists()
    write_nfo(record, nfo_path, cover_filename=cover_path.name if record.cover_url else None)
    result.nfo_written = True
    if journal is not None and not nfo_existed:
        journal.record_created_file(nfo_path)

    if record.cover_url:
        cover_existed = cover_path.exists()
        result.cover_downloaded = download_cover(client, record.cover_url, cover_path)
        if journal is not None and result.cover_downloaded and not cover_existed:
            journal.record_created_file(cover_path)

    for canonical_path in canonical_paths:
        links = category_builder.build_category_links(
            library_root, canonical_path, record, enabled_categories
        )
        result.link_results.update(links)
        if journal is not None:
            for link_path, link_result in links.items():
                if link_result.success:
                    journal.record_created_link(Path(link_path))

    return result


# Destination logic lives in organize.plan so the dry-run preview and the
# real run can never disagree about where a file is going.
_destination_for = destination_for
