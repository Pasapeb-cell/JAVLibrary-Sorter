from pathlib import Path

from javsorter.core.models import MatchStatus, MetadataRecord
from javsorter.core.scanner import scan_folder
from javsorter.organize.journal import RunJournal, undo
from javsorter.organize.pipeline import process_item
from javsorter.scraping.client import ScraperClient


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _assert_links_are_consistent(link_results):
    # Symlink creation may succeed or fail depending on whether this
    # environment has Developer Mode/admin -- either is legitimate, but a
    # failure must always be flagged as a permission error, never silent.
    for link_path_str, link_result in link_results.items():
        if link_result.success:
            assert Path(link_path_str).is_symlink()
        else:
            assert link_result.is_permission_error is True
            assert not Path(link_path_str).exists()


def test_pipeline_sort_in_place(tmp_path):
    source = tmp_path / "source"
    _touch(source / "hhd800.com@ABC-123.mp4")

    items = scan_folder(source)
    assert len(items) == 1
    item = items[0]
    assert item.status == MatchStatus.ID_FOUND
    assert item.extracted.content_id == "ABC-123"

    record = MetadataRecord(
        content_id="ABC-123",
        title="Some Title",
        actresses=["Actress One"],
        genres=["Genre One"],
        studio="Studio One",
        release_date="2022-05-01",
        cover_url=None,
    )

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(
            item,
            record,
            library_root=source,
            sort_in_place=True,
            enabled_categories=["Actress", "Genre", "Studio", "Year"],
            client=client,
        )

    canonical = source / "ABC-123.mp4"
    assert canonical.exists()
    assert result.canonical_paths == [canonical]
    assert (source / "ABC-123.nfo").exists()
    assert not (source / "hhd800.com@ABC-123.mp4").exists()
    _assert_links_are_consistent(result.link_results)


def test_pipeline_import_into_library(tmp_path):
    source = tmp_path / "source"
    library = tmp_path / "Library"
    _touch(source / "MIST-435.1080p.mp4")

    items = scan_folder(source)
    item = items[0]

    record = MetadataRecord(content_id="MIST-435", title="Title", cover_url=None)

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(
            item,
            record,
            library_root=library,
            sort_in_place=False,
            enabled_categories=[],
            client=client,
        )

    expected = library / "MIST-435" / "MIST-435.mp4"
    assert expected.exists()
    assert result.canonical_paths == [expected]
    assert not (source / "MIST-435.1080p.mp4").exists()
    assert (library / "MIST-435" / "MIST-435.nfo").exists()


def test_pipeline_run_can_be_fully_undone(tmp_path):
    """Organize for real, then reverse it: the source folder should look
    like it did before, and the library should be gone.
    """
    source = tmp_path / "source"
    library = tmp_path / "Library"
    original = source / "hhd800.com@ABC-123.mp4"
    _touch(original)
    original.write_bytes(b"the video")

    items = scan_folder(source)
    record = MetadataRecord(
        content_id="ABC-123",
        title="Some Title",
        actresses=["Actress One"],
        genres=["Genre One"],
        studio="Studio One",
        release_date="2022-05-01",
        cover_url=None,
    )

    run_journal = RunJournal(library_root=str(library))
    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(
            items[0], record, library,
            sort_in_place=False,
            enabled_categories=["Actress", "Genre", "Studio", "Year"],
            client=client,
            journal=run_journal,
        )

    assert (library / "ABC-123" / "ABC-123.mp4").exists()
    assert not original.exists()

    report = undo(run_journal)

    assert not report.failures
    assert original.exists()
    assert original.read_bytes() == b"the video"
    assert not library.exists()


def test_pipeline_undo_leaves_untouched_source_files_alone(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ABC-123.mp4")
    unrelated = source / "holiday.mp4"
    _touch(unrelated)

    items = [i for i in scan_folder(source) if i.extracted.content_id == "ABC-123"]
    record = MetadataRecord(content_id="ABC-123", title="T", cover_url=None)

    run_journal = RunJournal(library_root=str(tmp_path / "Library"))
    with ScraperClient(base_delay=0, jitter=0) as client:
        process_item(
            items[0], record, tmp_path / "Library",
            sort_in_place=False, enabled_categories=[], client=client, journal=run_journal,
        )

    undo(run_journal)

    assert unrelated.exists()


def test_pipeline_skips_duplicates_rather_than_colliding(tmp_path):
    source = tmp_path / "source"
    source.mkdir(parents=True)
    (source / "ABC-123.mp4").write_bytes(b"x" * 100)
    (source / "ABC-123 [FHD].mkv").write_bytes(b"x" * 900)

    items = scan_folder(source)
    record = MetadataRecord(content_id="ABC-123", title="T", cover_url=None)

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(
            items[0], record, tmp_path / "Library",
            sort_in_place=False, enabled_categories=[], client=client,
        )

    # Only the largest was taken into the library...
    assert len(result.canonical_paths) == 1
    assert (tmp_path / "Library" / "ABC-123" / "ABC-123.mkv").exists()
    # ...and the smaller copy is still sitting where it was, untouched.
    assert (source / "ABC-123.mp4").exists()


def test_pipeline_multi_cd_shares_one_nfo(tmp_path):
    source = tmp_path / "source"
    _touch(source / "ghi-789-cd1.mp4")
    _touch(source / "ghi-789-cd2.mp4")

    items = scan_folder(source)
    item = items[0]

    record = MetadataRecord(content_id="GHI-789", title="Title", cover_url=None)

    with ScraperClient(base_delay=0, jitter=0) as client:
        result = process_item(
            item,
            record,
            library_root=source,
            sort_in_place=True,
            enabled_categories=[],
            client=client,
        )

    assert len(result.canonical_paths) == 2
    assert {p.name for p in result.canonical_paths} == {"GHI-789-cd1.mp4", "GHI-789-cd2.mp4"}
    assert (source / "GHI-789.nfo").exists()
    assert not (source / "GHI-789-cd1.nfo").exists()
