"""The tag-folder layout: each video moves into exactly one folder,
decided by the chosen tag. No symlinks, no release folders.
"""

from javsorter.core.models import MetadataRecord
from javsorter.core.scanner import scan_folder
from javsorter.organize.options import TAG_FOLDERS, UNKNOWN_TAG, OrganizeOptions, tag_value_for
from javsorter.organize.pipeline import process_item
from javsorter.organize.plan import plan_item
from javsorter.scraping.client import ScraperClient


def _touch(path, content=b"x" * 64):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _record(**overrides):
    values = dict(
        content_id="ABC-123",
        title="Some Title",
        actresses=["First Actress", "Second Actress"],
        genres=["First Genre", "Second Genre", "Third Genre"],
        studio="Some Studio",
        release_date="2022-05-01",
        cover_url=None,
    )
    values.update(overrides)
    return MetadataRecord(**values)


def _options(root, sort_by):
    return OrganizeOptions(root=root, layout=TAG_FOLDERS, sort_by=sort_by)


def test_multi_value_tags_take_the_first_entry():
    record = _record()

    assert tag_value_for(record, "Genre") == "First Genre"
    assert tag_value_for(record, "Actress") == "First Actress"
    assert tag_value_for(record, "Studio") == "Some Studio"
    assert tag_value_for(record, "Year") == "2022"


def test_missing_tag_falls_back_to_unknown():
    bare = MetadataRecord(content_id="ABC-123", title="T")

    assert tag_value_for(bare, "Genre") == UNKNOWN_TAG
    assert tag_value_for(bare, "Year") == UNKNOWN_TAG


def test_file_moves_into_the_genre_folder(tmp_path):
    source = tmp_path / "source"
    _touch(source / "hhd800.com@ABC-123.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(item, _record(), _options(tmp_path / "Sorted", "Genre"), client)

    expected = tmp_path / "Sorted" / "First Genre" / "ABC-123.mp4"
    assert result.canonical_paths == [expected]
    assert expected.exists()
    assert not (source / "hhd800.com@ABC-123.mp4").exists()


def test_file_moves_into_the_actress_folder(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(item, _record(), _options(tmp_path / "Sorted", "Actress"), client)

    assert (tmp_path / "Sorted" / "First Actress" / "ABC-123.mp4").exists()
    # Only the first actress gets a folder -- no fan-out.
    assert not (tmp_path / "Sorted" / "Second Actress").exists()


def test_no_symlinks_are_created(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(item, _record(), _options(tmp_path / "Sorted", "Genre"), client)

    assert result.link_results == {}
    sorted_root = tmp_path / "Sorted"
    assert [p for p in sorted_root.rglob("*") if p.is_symlink()] == []
    # And exactly one folder was created, not one per genre.
    assert sorted(p.name for p in sorted_root.iterdir()) == ["First Genre"]


def test_nfo_and_cover_land_beside_the_video(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(item, _record(), _options(tmp_path / "Sorted", "Genre"), client)

    folder = tmp_path / "Sorted" / "First Genre"
    assert (folder / "ABC-123.nfo").exists()


def test_organising_inside_the_source_folder(tmp_path):
    """The reported bug: this must not need a separate destination."""
    source = tmp_path / "Videos"
    _touch(source / "hhd800.com@ABC-123.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(item, _record(), _options(source, "Genre"), client)

    assert (source / "First Genre" / "ABC-123.mp4").exists()


def test_untagged_release_goes_to_the_unknown_folder(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]
    bare = MetadataRecord(content_id="ABC-123", title="T", cover_url=None)

    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(item, bare, _options(tmp_path / "Sorted", "Genre"), client)

    assert (tmp_path / "Sorted" / UNKNOWN_TAG / "ABC-123.mp4").exists()


def test_multi_part_release_stays_together_in_one_folder(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123-cd1.mp4")
    _touch(source / "ABC-123-cd2.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(item, _record(), _options(tmp_path / "Sorted", "Genre"), client)

    folder = tmp_path / "Sorted" / "First Genre"
    assert len(result.canonical_paths) == 2
    assert (folder / "ABC-123-cd1.mp4").exists()
    assert (folder / "ABC-123-cd2.mp4").exists()
    assert (folder / "ABC-123.nfo").exists()


def test_genre_with_a_slash_is_sanitised(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]

    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(
            item,
            _record(genres=["Threesome / Foursome"]),
            _options(tmp_path / "Sorted", "Genre"),
            client,
        )

    assert (tmp_path / "Sorted" / "Threesome _ Foursome" / "ABC-123.mp4").exists()


def test_plan_previews_the_tag_folder_without_touching_disk(tmp_path):
    source = tmp_path / "source"
    original = _touch(source / "hhd800.com@ABC-123.mp4")
    item = scan_folder(source)[0]

    result = plan_item(item, _record(), _options(tmp_path / "Sorted", "Genre"))

    assert result.tag_folder == "First Genre"
    assert result.moves == [(original, tmp_path / "Sorted" / "First Genre" / "ABC-123.mp4")]
    assert result.link_paths == []
    assert original.exists()
    assert not (tmp_path / "Sorted").exists()


def test_plan_warns_about_an_untagged_release(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]
    bare = MetadataRecord(content_id="ABC-123", title="T", cover_url=None)

    result = plan_item(item, bare, _options(tmp_path / "Sorted", "Genre"))

    assert result.tag_folder == UNKNOWN_TAG
    assert any(UNKNOWN_TAG in w for w in result.warnings)


def test_plan_matches_the_real_run_for_tag_folders(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    item = scan_folder(source)[0]
    options = _options(tmp_path / "Sorted", "Actress")

    predicted = plan_item(item, _record(), options)
    with ScraperClient(base_delay=0, jitter=0) as client:
        actual = process_item(item, _record(), options, client)

    assert actual.canonical_paths == [dst for _src, dst in predicted.moves]
