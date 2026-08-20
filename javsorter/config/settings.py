from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from javsorter.organize.category_builder import ALL_CATEGORIES


@dataclass
class Settings:
    last_source_folder: str = ""
    last_library_folder: str = ""
    sort_in_place: bool = False
    enabled_categories: list[str] = field(default_factory=lambda: list(ALL_CATEGORIES))
    dev_mode_dialog_acknowledged: bool = False

    @classmethod
    def load(cls, path: Path) -> "Settings":
        """Never raises: falls back to defaults on a missing or corrupt file."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known_fields = set(cls.__dataclass_fields__)
            return cls(**{k: v for k, v in data.items() if k in known_fields})
        except (json.JSONDecodeError, OSError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
