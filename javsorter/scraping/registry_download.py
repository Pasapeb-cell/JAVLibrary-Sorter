"""Streaming acquisition of the public R18.dev actress registry."""

from __future__ import annotations

import gzip
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from javsorter.scraping.actress_registry import RegistryManager, RegistryProvenance
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NetworkError


class RegistryDownloadError(NetworkError):
    """The archive was rejected before it could become active evidence."""


def download_and_activate(
    manager: RegistryManager,
    client: ScraperClient,
    url: str,
    *,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> RegistryProvenance:
    """Download, validate, import, and atomically activate one dump.

    The compressed bytes are streamed to a temporary file first.  This keeps
    cancellation and a broken connection from ever exposing partial data to
    readers, and also lets us derive provenance from the final redirect URL
    and local SHA-256 digest.
    """
    try:
        with client.get_stream(url) as response:
            if response.status_code < 200 or response.status_code >= 300:
                raise RegistryDownloadError(f"registry download returned HTTP {response.status_code}")
            content_type = (response.headers.get("Content-Type") or "").lower()
            final_url = response.url or url
            if not (final_url.lower().endswith((".gz", "/latest")) or "gzip" in content_type):
                raise RegistryDownloadError("registry response is not a gzipped SQL dump")
            total = int(response.headers.get("Content-Length") or 0)
            temporary = manager.root / ".download.sql.gz.tmp"
            digest = hashlib.sha256()
            transferred = 0
            try:
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if should_cancel and should_cancel():
                            raise InterruptedError("registry download cancelled")
                        if not chunk:
                            continue
                        output.write(chunk)
                        digest.update(chunk)
                        transferred += len(chunk)
                        if progress:
                            progress(transferred, total)
                with gzip.open(temporary, "rb") as decompressed:
                    revision = _revision_from_url(final_url)
                    return manager.import_dump(
                        decompressed,
                        revision,
                        source_url=final_url,
                        source_digest=digest.hexdigest(),
                        imported_at=datetime.now(timezone.utc).isoformat(),
                        should_cancel=should_cancel,
                    )
            finally:
                temporary.unlink(missing_ok=True)
    except (InterruptedError, OSError, gzip.BadGzipFile, EOFError, ValueError) as exc:
        if isinstance(exc, InterruptedError):
            raise
        raise RegistryDownloadError(f"invalid registry archive: {exc}") from exc


def _revision_from_url(url: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", url)
    if match:
        return match.group(1)
    # A test mirror may not use the dated filename.  A content-addressed
    # revision is still stable and avoids replacing an existing generation.
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"url-{digest}"
