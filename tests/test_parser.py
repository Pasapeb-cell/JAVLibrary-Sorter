import json
from pathlib import Path

from javsorter.scraping.parser import parse_detail

FIXTURES = Path(__file__).parent / "fixtures" / "json"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_detail_multi_actress():
    data = _load("ssis-001.json")

    record = parse_detail(data, requested_id="SSIS-001")

    assert record.content_id == "SSIS-001"
    assert record.title.startswith("After Abstaining")
    assert record.actresses == ["Tsukasa Aoi", "Sayaka Otoshiro"]
    assert "Cheating Wife" in record.genres
    assert record.studio == "S1 NO.1 STYLE"
    assert record.release_date == "2021-02-19"
    assert record.director == "Ichigohara"
    assert record.runtime_minutes == 147
    # jacket_image.large is a blank placeholder (" "); must fall back to large2.
    assert record.cover_url == "https://pics.dmm.co.jp/digital/video/ssis00001/ssis00001pl.jpg"


def test_parse_detail_reduced_schema_falls_back_to_requested_id():
    """Neither real fixture includes a "dvd_id" field, and the primary
    image URL is a blank placeholder -- the parser must not assume a
    single fixed shape and must fall back to the requested ID / large2.
    """
    data = _load("midv-751.json")

    record = parse_detail(data, requested_id="MIDV-751")

    assert record.content_id == "MIDV-751"
    assert record.actresses == ["Arina Arata"]
    assert record.studio == "MOODYZ"
    assert record.director == "Captain Ehara"
    assert record.release_date == "2024-10-15"
    assert record.runtime_minutes == 120
    # cover_image.large was blank (" "); must fall back to jacket_image.large2.
    assert record.cover_url == "https://pics.dmm.co.jp/mono/movie/adult/midv751/midv751pl.jpg"


def test_parse_detail_missing_optional_fields():
    record = parse_detail({}, requested_id="ABC-123")

    assert record.content_id == "ABC-123"
    assert record.title == ""
    assert record.actresses == []
    assert record.genres == []
    assert record.studio is None
    assert record.cover_url is None
