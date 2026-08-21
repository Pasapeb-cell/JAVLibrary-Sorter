from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from javsorter.core.models import MetadataRecord, ScanItem
from javsorter.organize import category_builder, namer
from javsorter.organize.longpath import is_too_long


@dataclass
class ItemPlan:
    """What a run would do to one release, computed without touching disk."""

    content_id: str
    moves: list[tuple[Path, Path]] = field(default_factory=list)
    nfo_path: Path | None = None
    nfo_overwrites: bool = False
    cover_path: Path | None = None
    link_paths: list[Path] = field(default_factory=list)
    skipped_duplicates: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def renames(self) -> list[tuple[Path, Path]]:
        return [(src, dst) for src, dst in self.moves if src != dst]


def plan_item(
    item: ScanItem,
    record: MetadataRecord,
    library_root: Path,
    sort_in_place: bool,
    enabled_categories: list[str],
) -> ItemPlan:
    """Work out exactly what process_item would do, changing nothing.

    Kept deliberately separate from the pipeline rather than threaded
    through it as a flag, so there is no code path where a "preview" can
    accidentally write.
    """
    plan = ItemPlan(content_id=record.content_id)

    for source_path, part_label in zip(item.parts, item.part_labels):
        destination = destination_for(
            source_path, record.content_id, part_label, library_root, sort_in_place
        )
        plan.moves.append((source_path, destination))
        if destination != source_path and destination.exists():
            plan.warnings.append(
                f"{destination.name} already exists; the incoming file would be "
                "renamed rather than overwriting it"
            )
        if is_too_long(destination):
            plan.warnings.append(f"very long path, will use the extended form: {destination}")

    plan.skipped_duplicates = list(item.duplicates)

    primary_destination = plan.moves[0][1]
    plan.nfo_path = primary_destination.with_name(namer.nfo_filename(record.content_id))
    plan.nfo_overwrites = plan.nfo_path.exists()
    if record.cover_url:
        plan.cover_path = primary_destination.with_name(namer.cover_filename(record.content_id))

    for _source_path, destination in plan.moves:
        for category in enabled_categories:
            for value in category_builder.category_values(record, category):
                folder = library_root / category / namer.sanitize_component(value)
                plan.link_paths.append(folder / destination.name)

    if enabled_categories and not plan.link_paths:
        plan.warnings.append("no category values in the metadata, so no links would be created")

    return plan


def destination_for(
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


def format_plan(plan: ItemPlan) -> list[str]:
    """Human-readable preview lines for the log panel."""
    lines = [f"{plan.content_id}:"]
    for source, destination in plan.moves:
        if source == destination:
            lines.append(f"    keep   {source}")
        else:
            lines.append(f"    move   {source}")
            lines.append(f"      -->  {destination}")
    if plan.nfo_path is not None:
        verb = "overwrite" if plan.nfo_overwrites else "write"
        lines.append(f"    {verb} {plan.nfo_path.name}")
    if plan.cover_path is not None:
        lines.append(f"    fetch  {plan.cover_path.name}")
    if plan.link_paths:
        lines.append(f"    link   {len(plan.link_paths)} category shortcut(s):")
        for link_path in plan.link_paths[:5]:
            lines.append(f"             {link_path}")
        if len(plan.link_paths) > 5:
            lines.append(f"             ... and {len(plan.link_paths) - 5} more")
    for duplicate in plan.skipped_duplicates:
        lines.append(f"    skip   duplicate left in place: {duplicate}")
    for warning in plan.warnings:
        lines.append(f"    WARN   {warning}")
    return lines
