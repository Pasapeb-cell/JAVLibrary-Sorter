from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from javsorter.core.id_extractor import extract_id
from javsorter.core.models import MetadataRecord
from javsorter.core.scanner import VIDEO_EXTENSIONS
from javsorter.logging_setup import get_logger
from javsorter.organize import category_builder, namer
from javsorter.organize.category_builder import ALL_CATEGORIES
from javsorter.organize.cover_downloader import download_cover
from javsorter.organize.journal import RunJournal
from javsorter.organize.linker import create_symlink
from javsorter.organize.nfo_writer import write_nfo
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import ScrapeError

logger = get_logger("rescan")

Resolver = Callable[[str], MetadataRecord]


@dataclass
class RescanReport:
    releases: int = 0
    links_created: int = 0
    stale_links_removed: int = 0
    broken_links_removed: int = 0
    nfos_written: int = 0
    covers_downloaded: int = 0
    unmatched: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return (
            self.links_created
            + self.stale_links_removed
            + self.broken_links_removed
            + self.nfos_written
            + self.covers_downloaded
        )


def find_library_releases(library_root: Path) -> dict[str, list[Path]]:
    """Group the library's real video files by content ID.

    Category folders hold only symlinks, so they're skipped -- what's left
    is the canonical copy of each release.
    """
    groups: dict[str, list[Path]] = {}
    if not library_root.exists():
        return groups

    for path in sorted(library_root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if _is_under_category(path, library_root):
            continue
        extracted = extract_id(path.name)
        if extracted.content_id is None:
            continue
        groups.setdefault(extracted.content_id, []).append(path)
    return groups


def find_category_links(library_root: Path) -> list[Path]:
    links: list[Path] = []
    for category in ALL_CATEGORIES:
        base = library_root / category
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_symlink():
                links.append(path)
    return links


def _is_under_category(path: Path, library_root: Path) -> bool:
    try:
        relative = path.relative_to(library_root)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] in ALL_CATEGORIES


def _link_is_broken(link: Path) -> bool:
    try:
        return not link.exists()
    except OSError:
        return True


def rescan_library(
    library_root: Path,
    enabled_categories: list[str],
    resolve: Resolver,
    client: ScraperClient,
    journal: RunJournal | None = None,
    should_cancel: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> RescanReport:
    """Bring an already-sorted library back in line with current metadata.

    Rebuilds category links (so newly enabled categories appear and ones
    dropped by a changed genre blocklist go away), refreshes NFOs, fills
    in missing covers, and prunes links whose target no longer exists.

    Only the library's own structure is touched -- videos are never moved
    and never deleted.
    """
    report = RescanReport()
    groups = find_library_releases(library_root)
    report.releases = len(groups)
    total = len(groups)

    # Keyed by a case-normalised path for lookups, but holding the real
    # cased paths -- building a link from the normalised key would create
    # lowercase folder names on Windows.
    expected_links: dict[str, tuple[Path, Path]] = {}
    known_targets: set[str] = set()

    for done, (content_id, paths) in enumerate(sorted(groups.items()), start=1):
        if should_cancel is not None and should_cancel():
            logger.info("Rescan cancelled after %d/%d release(s)", done - 1, total)
            break

        for path in paths:
            known_targets.add(os.path.normcase(str(path.resolve())))

        try:
            record = resolve(content_id)
        except ScrapeError:
            # Leave this release and its existing links exactly as they are;
            # without metadata we can't tell a stale link from a good one.
            report.unmatched.append(content_id)
            known_targets.difference_update(
                os.path.normcase(str(p.resolve())) for p in paths
            )
            if progress is not None:
                progress(done, total)
            continue

        try:
            _refresh_sidecars(record, paths[0], client, journal, report)
        except OSError as exc:
            report.failures.append(f"{content_id}: {exc}")

        for path in paths:
            for category in enabled_categories:
                for value in category_builder.category_values(record, category):
                    folder = library_root / category / namer.sanitize_component(value)
                    link_path = folder / path.name
                    expected_links[os.path.normcase(str(link_path))] = (link_path, path)

        if progress is not None:
            progress(done, total)

    _prune_links(library_root, expected_links, known_targets, journal, report)
    _create_missing_links(expected_links, journal, report)
    _remove_empty_category_dirs(library_root)

    return report


def _refresh_sidecars(
    record: MetadataRecord,
    primary: Path,
    client: ScraperClient,
    journal: RunJournal | None,
    report: RescanReport,
) -> None:
    nfo_path = primary.with_name(namer.nfo_filename(record.content_id))
    cover_path = primary.with_name(namer.cover_filename(record.content_id))

    nfo_existed = nfo_path.exists()
    write_nfo(record, nfo_path, cover_filename=cover_path.name if record.cover_url else None)
    report.nfos_written += 1
    if journal is not None and not nfo_existed:
        journal.record_created_file(nfo_path)

    # Only fetch a cover that's actually missing: a rescan shouldn't
    # re-download every image in the library.
    if record.cover_url and not cover_path.exists():
        if download_cover(client, record.cover_url, cover_path):
            report.covers_downloaded += 1
            if journal is not None:
                journal.record_created_file(cover_path)


def _prune_links(
    library_root: Path,
    expected_links: dict[str, tuple[Path, Path]],
    known_targets: set[str],
    journal: RunJournal | None,
    report: RescanReport,
) -> None:
    for link in find_category_links(library_root):
        key = os.path.normcase(str(link))
        if key in expected_links:
            continue

        try:
            target = os.readlink(link)
        except OSError:
            target = ""

        if _link_is_broken(link):
            _remove_link(link, target, journal, report)
            report.broken_links_removed += 1
            continue

        # A link that still resolves is only stale if it points at a release
        # we actually rescanned -- anything else was put there by something
        # we don't know about, so leave it alone.
        resolved = os.path.normcase(str(Path(link).resolve()))
        if resolved in known_targets:
            _remove_link(link, target, journal, report)
            report.stale_links_removed += 1


def _remove_link(
    link: Path, target: str, journal: RunJournal | None, report: RescanReport
) -> None:
    try:
        link.unlink()
        if journal is not None and target:
            journal.record_removed_link(link, target)
    except OSError as exc:
        report.failures.append(f"{link}: {exc}")


def _create_missing_links(
    expected_links: dict[str, tuple[Path, Path]],
    journal: RunJournal | None,
    report: RescanReport,
) -> None:
    for link_path, target in expected_links.values():
        if link_path.is_symlink():
            continue
        result = create_symlink(target, link_path)
        if result.success:
            report.links_created += 1
            if journal is not None:
                journal.record_created_link(link_path)
        else:
            report.failures.append(f"{link_path}: {result.reason}")


def _remove_empty_category_dirs(library_root: Path) -> None:
    for category in ALL_CATEGORIES:
        base = library_root / category
        if not base.exists():
            continue
        for directory in sorted(base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if directory.is_dir():
                try:
                    directory.rmdir()
                except OSError:
                    pass
        try:
            base.rmdir()
        except OSError:
            pass
