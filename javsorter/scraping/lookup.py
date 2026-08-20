from __future__ import annotations

from dataclasses import replace

from javsorter.core.genre_filter import GenreFilter
from javsorter.core.models import ExtractedId, MetadataRecord
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NoMatchError
from javsorter.scraping.parser import parse_detail
from javsorter.scraping.r18 import fetch_by_dvd_id


def lookup_metadata(
    cache: MetadataCache,
    client: ScraperClient,
    lookup_id: str,
    genre_filter: GenreFilter | None = None,
) -> MetadataRecord:
    """Resolve metadata for a content ID, checking the cache (including the
    negative cache) before making a rate-limited network request.

    The cache stores the unfiltered record and genre_filter is applied on
    the way out, so changing the blocklist takes effect immediately rather
    than requiring the cache to be cleared.

    Raises NoMatchError / NetworkError, same as fetch_by_dvd_id.
    """
    record = cache.get(lookup_id)
    if record is None:
        if cache.has_not_found(lookup_id):
            raise NoMatchError(lookup_id)

        try:
            data = fetch_by_dvd_id(client, lookup_id)
        except NoMatchError:
            cache.put_not_found(lookup_id)
            raise

        record = parse_detail(data, requested_id=lookup_id)
        cache.put(lookup_id, record)

    if genre_filter is not None:
        record = genre_filter.apply(record)
    return record


def lookup_for_item(
    cache: MetadataCache,
    client: ScraperClient,
    extracted: ExtractedId,
    genre_filter: GenreFilter | None = None,
) -> MetadataRecord:
    """Look up metadata for a scanned file.

    Uses the base ID for the lookup, since an uncensored release ("-C")
    isn't a separate entry on r18.dev -- it shares the original's
    metadata. The returned record keeps the extracted content ID, so an
    uncensored file is still named "ABC-123-C" and stays distinguishable
    from the censored release on disk.
    """
    lookup_id = extracted.base_id or extracted.content_id
    record = lookup_metadata(cache, client, lookup_id, genre_filter=genre_filter)
    if extracted.content_id and record.content_id != extracted.content_id:
        record = replace(record, content_id=extracted.content_id)
    return record
