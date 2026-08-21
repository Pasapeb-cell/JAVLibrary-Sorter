from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "JAVSorter"


def app_data_dir() -> Path:
    base = Path(os.getenv("APPDATA", str(Path.home())))
    return base / APP_NAME


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def cache_path() -> Path:
    return app_data_dir() / "cache.sqlite3"


def log_dir() -> Path:
    return app_data_dir() / "logs"


def runs_dir() -> Path:
    """Where per-run journals live, so a run can be undone later."""
    return app_data_dir() / "runs"
