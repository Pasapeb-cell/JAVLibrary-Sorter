from __future__ import annotations

import os
from pathlib import Path

# Windows' classic MAX_PATH. Paths at or beyond this fail with "path too
# long" unless either the machine has long paths enabled or the call uses
# the \\?\ extended-length prefix.
MAX_PATH = 260

# Longest a single folder/file name is allowed to get. Actress and genre
# names are short, but titles and studio names occasionally are not, and
# NTFS caps a single component at 255 anyway.
MAX_COMPONENT = 100

_EXTENDED_PREFIX = "\\\\?\\"


def truncate_component(name: str) -> str:
    """Cap one path component's length, preserving the start (which is
    the part that identifies it).
    """
    if len(name) <= MAX_COMPONENT:
        return name
    return name[:MAX_COMPONENT].rstrip(" .")


def extended(path: Path) -> Path:
    """Return a form of `path` safe to hand to the filesystem.

    Only rewrites when the path is actually long enough to be a problem,
    so ordinary paths (and the symlink targets recorded from them) stay
    clean and readable.
    """
    if os.name != "nt":
        return path

    text = str(path)
    if len(text) < MAX_PATH or text.startswith(_EXTENDED_PREFIX):
        return path

    absolute = os.path.abspath(text)
    if absolute.startswith("\\\\"):
        # UNC share: \\server\share -> \\?\UNC\server\share
        return Path(_EXTENDED_PREFIX + "UNC" + absolute[1:])
    return Path(_EXTENDED_PREFIX + absolute)


def is_too_long(path: Path) -> bool:
    return os.name == "nt" and len(str(path)) >= MAX_PATH
