import json
from pathlib import Path

import pytest

from javsorter.core.genre_filter import GenreFilter
from javsorter.core.id_extractor import extract_id
from javsorter.core.models import MetadataRecord
from javsorter.scraping.cache import MetadataCache
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NoMatchError
from javsorter.scraping.lookup import lookup_for_item, lookup_metadata

FIXTURES = Path(__file__).parent / "fixtures" / "json"


@pytest.fixture
def cache(tmp_path):
    c = MetadataCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


@pytest.fixture
def client():
    c = ScraperClient(base_delay=0, jitter=0)
    yield c
    c.close()


def test_uncensored_release_looks_up_base_id_but_keeps_c_suffix(requests_mock, cache, client):
    """An uncensored "-C" release isn't a separate entry on r18.dev -- it
    shares the original's metadata. Looking up "MIDV-751-C" 404s, so the
    lookup must use the base ID while the record keeps the -C marker for
    naming.
    """
    payload = json.loads((FIXTURES / "midv-751.json").read_text(encoding="utf-8"))
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=MIDV-751/json",
        json=payload,
    )
    # Deliberately unregistered: if the code looked up the -C variant,
    # requests_mock would raise NoMockAddress instead of matching.

    extracted = extract_id("MIDV-751-C_GG5.mp4")
    assert extracted.content_id == "MIDV-751-C"

    record = lookup_for_item(cache, client, extracted)

    assert record.content_id == "MIDV-751-C"
    assert record.actresses == ["Arina Arata"]
    assert record.studio == "MOODYZ"


def test_plain_id_is_unchanged(requests_mock, cache, client):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        json=payload,
    )

    record = lookup_for_item(cache, client, extract_id("hhd800.com@SSIS-001.mp4"))

    assert record.content_id == "SSIS-001"


def test_lookup_caches_result(requests_mock, cache, client):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    matcher = requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        json=payload,
    )

    lookup_metadata(cache, client, "SSIS-001")
    lookup_metadata(cache, client, "SSIS-001")

    assert matcher.call_count == 1


def test_lookup_negative_cache_avoids_refetch(requests_mock, cache, client):
    matcher = requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=ZZZZ-999/json",
        status_code=404,
    )

    with pytest.raises(NoMatchError):
        lookup_metadata(cache, client, "ZZZZ-999")
    with pytest.raises(NoMatchError):
        lookup_metadata(cache, client, "ZZZZ-999")

    assert matcher.call_count == 1


def test_lookup_applies_genre_filter(requests_mock, cache, client):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        json=payload,
    )

    unfiltered = lookup_metadata(cache, client, "SSIS-001")
    assert "Sample Video" in unfiltered.genres or "Hi-Def" in unfiltered.genres

    filtered = lookup_metadata(cache, client, "SSIS-001", genre_filter=GenreFilter())

    assert "Hi-Def" not in filtered.genres
    assert "Exclusive Distribution" not in filtered.genres
    assert "Cheating Wife" in filtered.genres


def test_cache_stores_unfiltered_so_blocklist_changes_apply_immediately(
    requests_mock, cache, client
):
    """The blocklist must be changeable without clearing the cache, which
    means the cached record has to keep every genre and the filter has to
    run on the way out.
    """
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        json=payload,
    )

    narrow = lookup_metadata(cache, client, "SSIS-001", genre_filter=GenreFilter())
    assert "Drama" in narrow.genres

    # Now block "Drama" too -- served from cache, must reflect the change.
    wider = lookup_metadata(
        cache, client, "SSIS-001", genre_filter=GenreFilter(extra_blocked=["Drama"])
    )
    assert "Drama" not in wider.genres

    # And relaxing the blocklist restores genres a cached-filtered record
    # would have lost for good.
    relaxed = lookup_metadata(cache, client, "SSIS-001", genre_filter=GenreFilter(use_defaults=False))
    assert "Hi-Def" in relaxed.genres


def test_lookup_prefers_cache_over_network(requests_mock, cache, client):
    cache.put("ABC-123", MetadataRecord(content_id="ABC-123", title="Cached Title"))
    # No mock registered -- a network call would raise NoMockAddress.

    record = lookup_metadata(cache, client, "ABC-123")

    assert record.title == "Cached Title"
