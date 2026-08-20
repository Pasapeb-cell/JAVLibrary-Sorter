from javsorter.core.models import MetadataRecord
from javsorter.scraping.cache import MetadataCache


def _record(content_id="ABC-123"):
    return MetadataRecord(content_id=content_id, title="Test Title", actresses=["A"], genres=["G"])


def test_cache_miss_returns_none(tmp_path):
    cache = MetadataCache(tmp_path / "cache.sqlite3")

    assert cache.get("ABC-123") is None
    assert cache.has_not_found("ABC-123") is False


def test_cache_put_and_get_roundtrip(tmp_path):
    cache = MetadataCache(tmp_path / "cache.sqlite3")
    record = _record()

    cache.put("ABC-123", record)

    assert cache.get("ABC-123") == record


def test_cache_put_not_found(tmp_path):
    cache = MetadataCache(tmp_path / "cache.sqlite3")

    cache.put_not_found("ZZZZ-999")

    assert cache.has_not_found("ZZZZ-999") is True
    assert cache.get("ZZZZ-999") is None


def test_cache_persists_across_instances(tmp_path):
    db_path = tmp_path / "cache.sqlite3"
    cache1 = MetadataCache(db_path)
    cache1.put("ABC-123", _record())
    cache1.close()

    cache2 = MetadataCache(db_path)

    assert cache2.get("ABC-123") == _record()
