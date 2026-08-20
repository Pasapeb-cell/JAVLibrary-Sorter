from xml.etree import ElementTree as ET

from javsorter.core.models import MetadataRecord
from javsorter.organize.nfo_writer import write_nfo


def _record(**overrides):
    defaults = dict(
        content_id="ABC-123",
        title="Some Title",
        actresses=["Actress One", "Actress Two"],
        genres=["Genre One"],
        studio="Some Studio",
        release_date="2021-02-19",
        cover_url="https://example.com/cover.jpg",
        rating=None,
        director=None,
        runtime_minutes=120,
    )
    defaults.update(overrides)
    return MetadataRecord(**defaults)


def test_write_nfo_basic_fields(tmp_path):
    nfo_path = tmp_path / "ABC-123.nfo"
    write_nfo(_record(), nfo_path, cover_filename="ABC-123-thumb.jpg")

    root = ET.parse(nfo_path).getroot()
    assert root.tag == "movie"
    assert root.find("title").text == "Some Title"
    assert root.find("uniqueid").text == "ABC-123"
    assert root.find("uniqueid").get("type") == "r18"
    assert root.find("studio").text == "Some Studio"
    assert root.find("premiered").text == "2021-02-19"
    assert root.find("year").text == "2021"
    assert root.find("runtime").text == "120"
    assert root.find("thumb").text == "ABC-123-thumb.jpg"

    actors = root.findall("actor")
    assert [a.find("name").text for a in actors] == ["Actress One", "Actress Two"]
    genres = root.findall("genre")
    assert [g.text for g in genres] == ["Genre One"]


def test_write_nfo_omits_missing_optional_fields(tmp_path):
    nfo_path = tmp_path / "ABC-123.nfo"
    write_nfo(_record(studio=None, release_date=None, runtime_minutes=None, cover_url=None), nfo_path)

    root = ET.parse(nfo_path).getroot()
    assert root.find("studio") is None
    assert root.find("premiered") is None
    assert root.find("runtime") is None
    assert root.find("thumb") is None
