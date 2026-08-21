from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from javsorter.logging_setup import get_logger
from javsorter.organize.longpath import extended

logger = get_logger("journal")

MOVE = "move"
CREATE_FILE = "create_file"
CREATE_LINK = "create_link"


@dataclass
class JournalEntry:
    action: str
    path: str
    source: str | None = None


@dataclass
class RunJournal:
    """Records what a run did to disk so it can be reversed.

    Only records actions that are actually reversible. Overwriting a file
    that already existed is deliberately NOT recorded as a creation --
    undoing it would delete the user's pre-existing file rather than put
    the old contents back, which is worse than leaving it alone.
    """

    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    library_root: str = ""
    entries: list[JournalEntry] = field(default_factory=list)

    def record_move(self, source: Path, destination: Path) -> None:
        if Path(source) == Path(destination):
            return
        self.entries.append(JournalEntry(MOVE, str(destination), str(source)))

    def record_created_file(self, path: Path) -> None:
        self.entries.append(JournalEntry(CREATE_FILE, str(path)))

    def record_created_link(self, path: Path) -> None:
        self.entries.append(JournalEntry(CREATE_LINK, str(path)))

    def is_empty(self) -> bool:
        return not self.entries

    def save(self, runs_dir: Path) -> Path:
        runs_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.replace(":", "-")
        path = runs_dir / f"run-{stamp}.json"
        payload = {
            "started_at": self.started_at,
            "library_root": self.library_root,
            "entries": [asdict(e) for e in self.entries],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "RunJournal":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            started_at=data.get("started_at", ""),
            library_root=data.get("library_root", ""),
            entries=[JournalEntry(**e) for e in data.get("entries", [])],
        )


@dataclass
class UndoReport:
    links_removed: int = 0
    files_removed: int = 0
    files_restored: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def total_reversed(self) -> int:
        return self.links_removed + self.files_removed + self.files_restored


def latest_journal(runs_dir: Path) -> Path | None:
    if not runs_dir.exists():
        return None
    journals = sorted(runs_dir.glob("run-*.json"))
    return journals[-1] if journals else None


def undo(journal: RunJournal) -> UndoReport:
    """Reverse a recorded run, newest action first."""
    report = UndoReport()

    for entry in reversed(journal.entries):
        try:
            if entry.action == CREATE_LINK:
                _remove_link(Path(entry.path), report)
            elif entry.action == CREATE_FILE:
                _remove_file(Path(entry.path), report)
            elif entry.action == MOVE:
                _restore_move(Path(entry.path), Path(entry.source or ""), report)
        except OSError as exc:
            report.failures.append(f"{entry.path}: {exc}")

    if journal.library_root:
        _prune_empty_dirs(Path(journal.library_root))

    return report


def _remove_link(path: Path, report: UndoReport) -> None:
    if path.is_symlink():
        path.unlink()
        report.links_removed += 1


def _remove_file(path: Path, report: UndoReport) -> None:
    # is_symlink guard: never delete a real file through a link we didn't make.
    if path.exists() and not path.is_symlink():
        Path(extended(path)).unlink()
        report.files_removed += 1


def _restore_move(destination: Path, source: Path, report: UndoReport) -> None:
    if not destination.exists() or not source:
        return
    if source.exists():
        report.failures.append(f"{source}: something is already there, left {destination} in place")
        return
    Path(extended(source.parent)).mkdir(parents=True, exist_ok=True)
    Path(extended(destination)).replace(extended(source))
    report.files_restored += 1


def _prune_empty_dirs(root: Path) -> None:
    """Remove directories the run left behind, deepest first."""
    if not root.exists():
        return
    for directory in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                pass  # Not empty: something else lives there, leave it.
    try:
        root.rmdir()
    except OSError:
        pass
