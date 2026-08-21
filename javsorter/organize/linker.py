from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from javsorter.organize.longpath import extended

# Windows: "A required privilege is not held by the client" -- raised by
# os.symlink() when the process has neither admin elevation nor Developer
# Mode's unprivileged symlink creation enabled.
_WINERROR_PRIVILEGE_NOT_HELD = 1314


class SymlinkCapability:
    OK = "ok"
    DENIED = "denied"


@dataclass
class LinkResult:
    success: bool
    reason: str | None = None
    is_permission_error: bool = False

    @classmethod
    def ok(cls) -> "LinkResult":
        return cls(success=True)

    @classmethod
    def failed(cls, reason: str, is_permission_error: bool = False) -> "LinkResult":
        return cls(success=False, reason=reason, is_permission_error=is_permission_error)


def probe_symlink_capability(probe_dir: Path) -> str:
    """Create and immediately remove a throwaway symlink to check, once
    up front, whether this process can create symlinks at all -- so the
    GUI can warn the user before committing to a long batch run rather
    than failing midway through.
    """
    probe_dir.mkdir(parents=True, exist_ok=True)
    target = probe_dir / f".javsorter_probe_target_{uuid.uuid4().hex}"
    link = probe_dir / f".javsorter_probe_link_{uuid.uuid4().hex}"
    target.write_bytes(b"")
    try:
        os.symlink(target, link)
        link.unlink()
        return SymlinkCapability.OK
    except OSError:
        return SymlinkCapability.DENIED
    finally:
        target.unlink(missing_ok=True)


def create_symlink(target: Path, link_path: Path) -> LinkResult:
    """Create a symlink at link_path pointing to target's absolute path.

    Never falls back to a hardlink or copy on failure -- per product
    requirements the caller (pipeline/GUI) must surface the failure
    explicitly rather than silently substituting another link type.
    """
    Path(extended(link_path.parent)).mkdir(parents=True, exist_ok=True)
    absolute_target = target.resolve()

    if link_path.is_symlink() or link_path.exists():
        try:
            if link_path.resolve() == absolute_target:
                return LinkResult.ok()
        except OSError:
            pass
        link_path.unlink()

    try:
        os.symlink(extended(absolute_target), extended(link_path))
        return LinkResult.ok()
    except OSError as exc:
        is_permission_error = getattr(exc, "winerror", None) == _WINERROR_PRIVILEGE_NOT_HELD
        return LinkResult.failed(reason=str(exc), is_permission_error=is_permission_error)
