from javsorter.core.models import MetadataRecord
from javsorter.core.scanner import scan_folder
from javsorter.organize.options import LIBRARY_LINKS, TAG_FOLDERS, OrganizeOptions
from javsorter.organize.pipeline import process_item
from javsorter.organize.plan import format_plan, plan_item
from javsorter.scraping.client import ScraperClient

ALL = ["Actress", "Genre", "Studio", "Year"]


def _touch(path, content=b"x" * 64):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _record(**overrides):
    values = dict(
        content_id="ABC-123",
        title="Some Title",
        actresses=["Actress One", "Actress Two"],
        genres=["Genre One"],
        studio="Studio One",
        release_date="2022-05-01",
        cover_url="https://example.invalid/cover.jpg",
    )
    values.update(overrides)
    return MetadataRecord(**values)


def test_plan_describes_an_import(tmp_path):
    source = tmp_path / "source"
    _touch(source / "hhd800.com@ABC-123.mp4")
    library = tmp_path / "Library"
    item = scan_folder(source)[0]

    result = plan_item(item, _record(), OrganizeOptions(root=library, layout=LIBRARY_LINKS, enabled_categories=ALL))

    assert result.moves == [(source / "hhd800.com@ABC-123.mp4", library / "ABC-123" / "ABC-123.mp4")]
    assert result.nfo_path == library / "ABC-123" / "ABC-123.nfo"
    assert result.cover_path == library / "ABC-123" / "ABC-123-thumb.jpg"
    # 2 actresses + 1 genre + 1 studio + 1 year
    assert len(result.link_paths) == 5


def test_plan_changes_nothing_on_disk(tmp_path):
    source = tmp_path / "source"
    original = _touch(source / "hhd800.com@ABC-123.mp4")
    library = tmp_path / "Library"
    item = scan_folder(source)[0]

    plan_item(item, _record(), OrganizeOptions(root=library, layout=LIBRARY_LINKS, enabled_categories=ALL))

    assert original.exists()
    assert not library.exists()
    assert sorted(p.name for p in source.iterdir()) == ["hhd800.com@ABC-123.mp4"]


def test_plan_matches_what_the_pipeline_actually_does(tmp_path):
    """The preview is worthless if it can drift from the real run."""
    source = tmp_path / "source"
    _touch(source / "hhd800.com@ABC-123.mp4")
    library = tmp_path / "Library"
    item = scan_folder(source)[0]
    record = _record(cover_url=None)

    predicted = plan_item(item, record, OrganizeOptions(root=library, layout=LIBRARY_LINKS, enabled_categories=ALL))

    with ScraperClient(base_delay=0, jitter=0) as client:
        actual = process_item(item, record, OrganizeOptions(root=library, layout=LIBRARY_LINKS, enabled_categories=ALL), client)

    assert actual.canonical_paths == [dst for _src, dst in predicted.moves]
    assert predicted.nfo_path.exists()
    # Every predicted link was attempted (they may fail without privileges).
    assert sorted(str(p) for p in predicted.link_paths) == sorted(actual.link_results)


def test_plan_for_sort_in_place_renames_without_moving(tmp_path):
    source = tmp_path / "source"
    _touch(source / "MIST-435.1080p.mp4")
    item = scan_folder(source)[0]

    result = plan_item(
        item,
        _record(content_id="MIST-435"),
        OrganizeOptions(root=source, layout=LIBRARY_LINKS, link_only=True),
    )

    src, dst = result.moves[0]
    assert src.parent == dst.parent == source
    assert dst.name == "MIST-435.mp4"


def test_plan_warns_when_the_destination_is_taken(tmp_path):
    source = tmp_path / "source"
    _touch(source / "hhd800.com@ABC-123.mp4")
    library = tmp_path / "Library"
    _touch(library / "ABC-123" / "ABC-123.mp4", b"already here")
    item = scan_folder(source)[0]

    result = plan_item(item, _record(), OrganizeOptions(root=library, layout=LIBRARY_LINKS))

    assert any("already exists" in w for w in result.warnings)


def test_plan_reports_duplicates_that_would_be_left_alone(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4", b"x" * 100)
    _touch(source / "ABC-123 [FHD].mkv", b"x" * 900)
    item = scan_folder(source)[0]

    result = plan_item(item, _record(), OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS))

    assert [p.name for p in result.skipped_duplicates] == ["ABC-123.mp4"]


def test_plan_covers_every_part_of_a_multi_part_release(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123-cd1.mp4")
    _touch(source / "ABC-123-cd2.mp4")
    item = scan_folder(source)[0]

    result = plan_item(item, _record(), OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS, enabled_categories=["Actress"]))

    assert len(result.moves) == 2
    assert len(result.link_paths) == 4  # 2 files x 2 actresses
    # One shared NFO, named for the release rather than a part.
    assert result.nfo_path.name == "ABC-123.nfo"


def test_plan_warns_when_metadata_has_no_category_values(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]
    bare = MetadataRecord(content_id="ABC-123", title="T", cover_url=None)

    result = plan_item(item, bare, OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS, enabled_categories=ALL))

    assert result.link_paths == []
    assert any("no category values" in w for w in result.warnings)


def test_format_plan_is_readable(tmp_path):
    source = tmp_path / "source"
    _touch(source / "hhd800.com@ABC-123.mp4")
    item = scan_folder(source)[0]

    lines = format_plan(plan_item(item, _record(), OrganizeOptions(root=tmp_path / "Library", layout=LIBRARY_LINKS, enabled_categories=ALL)))
    text = "\n".join(lines)

    assert "ABC-123:" in text
    assert "move" in text
    assert "ABC-123.nfo" in text
