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


def registry_dir() -> Path:
    """Where downloaded and imported R18.dev registry generations live."""
    return app_data_dir() / "registry"


def registry_pointer_path() -> Path:
    """The small pointer naming the last completely validated generation."""
    return registry_dir() / "active"


def registry_download_url() -> str:
    """Stable R18.dev endpoint for the latest public database dump."""
    return "https://r18.dev/dumps/latest"


def identity_store_path() -> Path:
    """Durable user decisions, kept separate from disposable HTTP/cache data."""
    return app_data_dir() / "identity-decisions.sqlite3"
