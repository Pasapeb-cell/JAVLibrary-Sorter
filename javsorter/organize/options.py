from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from javsorter.core.models import MetadataRecord
from javsorter.organize import category_builder

# How the library is laid out on disk.
TAG_FOLDERS = "tag_folders"
LIBRARY_LINKS = "library_links"

# Used when the chosen tag has no value for a release (no genres listed,
# no release date, ...). Better than skipping the file silently.
UNKNOWN_TAG = "Unknown"


@dataclass(frozen=True)
class OrganizeOptions:
    """Where files go and how the library is shaped.

    `root` already encodes "sort in place": point it at the source folder
    and the tag folders are built there. That's why there's no separate
    in-place flag -- having one was the source of the bug where in-place
    still demanded a library folder.
    """

    root: Path
    layout: str = TAG_FOLDERS
    # TAG_FOLDERS: which single category decides the folder.
    sort_by: str = category_builder.CATEGORY_GENRE
    # LIBRARY_LINKS: which categories get symlink folders.
    enabled_categories: list[str] = field(default_factory=list)
    # LIBRARY_LINKS: leave the video where it is and only create links.
    link_only: bool = False

    @property
    def is_tag_folders(self) -> bool:
        return self.layout == TAG_FOLDERS


def tag_value_for(record: MetadataRecord, sort_by: str) -> str:
    """The single tag value that decides this release's folder.

    Multi-valued tags (genre, actress) take the first entry, which is the
    order the metadata source lists them in.
    """
    values = category_builder.category_values(record, sort_by)
    return values[0] if values else UNKNOWN_TAG
