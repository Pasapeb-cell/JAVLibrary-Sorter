from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from javsorter.core.models import MetadataRecord, ScanItem
from javsorter.organize import category_builder, namer
from javsorter.organize.longpath import is_too_long
from javsorter.organize.options import UNKNOWN_TAG, OrganizeOptions, tag_value_for


@dataclass
class ItemPlan:
    """What a run would do to one release, computed without touching disk."""

    content_id: str
    tag_folder: str | None = None
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


def plan_item(item: ScanItem, record: MetadataRecord, options: OrganizeOptions) -> ItemPlan:
    """Work out exactly what process_item would do, changing nothing.

    Kept deliberately separate from the pipeline rather than threaded
    through it as a flag, so there is no code path where a "preview" can
    accidentally write.
    """
    plan = ItemPlan(content_id=record.content_id)

    if options.is_tag_folders:
        plan.tag_folder = tag_value_for(record, options.sort_by)
        if plan.tag_folder == UNKNOWN_TAG:
            plan.warnings.append(
                f"no {options.sort_by.lower()} in the metadata, so it would go to "
                f"the '{UNKNOWN_TAG}' folder"
            )

    for source_path, part_label in zip(item.parts, item.part_labels):
        destination = destination_for(source_path, record, part_label, options)
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

    if not options.is_tag_folders:
        for _source_path, destination in plan.moves:
            for category in options.enabled_categories:
                for value in category_builder.category_values(record, category):
                    folder = options.root / category / namer.sanitize_component(value)
                    plan.link_paths.append(folder / destination.name)

        if options.enabled_categories and not plan.link_paths:
            plan.warnings.append("no category values in the metadata, so no links would be created")

    return plan


def destination_for(
    source_path: Path,
    record: MetadataRecord,
    part_label: str | None,
    options: OrganizeOptions,
) -> Path:
    """Where one video file ends up.

    Tag-folder layout puts it straight into the folder for its tag;
    library layout gives each release its own folder (or leaves the file
    alone when only links are wanted).
    """
    filename = namer.library_filename(record.content_id, source_path.suffix, part_label)

    if options.is_tag_folders:
        folder = namer.sanitize_component(tag_value_for(record, options.sort_by))
        return options.root / folder / filename

    if options.link_only:
        return source_path.with_name(filename)
    return namer.library_path(options.root, record.content_id) / filename


def format_plan(plan: ItemPlan) -> list[str]:
    """Human-readable preview lines for the log panel."""
    header = f"{plan.content_id}:"
    if plan.tag_folder is not None:
        header += f"  -> folder '{plan.tag_folder}'"
    lines = [header]
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
