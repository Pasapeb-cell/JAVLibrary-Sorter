import os

import pytest

from javsorter.core.models import MetadataRecord
from javsorter.organize.journal import RunJournal, undo
from javsorter.organize.rescan import find_library_releases, rescan_library
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NoMatchError

ALL = ["Actress", "Genre", "Studio", "Year"]


@pytest.fixture(autouse=True)
def _needs_symlinks(tmp_path):
    """Rescan is all about links, so skip rather than pass vacuously where
    symlink creation isn't permitted.
    """
    probe = tmp_path / "_probe"
    probe.write_bytes(b"")
    try:
        os.symlink(probe, tmp_path / "_probe_link")
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")


@pytest.fixture
def client():
    c = ScraperClient(base_delay=0, jitter=0, retry_backoff=0)
    yield c
    c.close()


def _record(content_id="ABC-123", **overrides):
    values = dict(
        content_id=content_id,
        title="Some Title",
        actresses=["Actress One"],
        genres=["Genre One"],
        studio="Studio One",
        release_date="2022-05-01",
        cover_url=None,
    )
    values.update(overrides)
    return MetadataRecord(**values)


def _make_library(tmp_path, content_id="ABC-123", suffix=".mp4"):
    library = tmp_path / "Library"
    video = library / content_id / f"{content_id}{suffix}"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video data")
    return library, video


def _resolver(record):
    def resolve(content_id):
        if record is None or record.content_id != content_id:
            raise NoMatchError(content_id)
        return record

    return resolve


def test_find_library_releases_ignores_category_links(tmp_path, client):
    library, video = _make_library(tmp_path)
    link_dir = library / "Actress" / "Actress One"
    link_dir.mkdir(parents=True)
    os.symlink(video, link_dir / video.name)

    groups = find_library_releases(library)

    assert list(groups) == ["ABC-123"]
    assert groups["ABC-123"] == [video]


def test_rescan_creates_links_for_a_newly_enabled_category(tmp_path, client):
    library, video = _make_library(tmp_path)

    report = rescan_library(library, ["Actress"], _resolver(_record()), client)
    assert report.links_created == 1
    assert (library / "Actress" / "Actress One" / "ABC-123.mp4").is_symlink()

    # Now the user turns on Year as well.
    report = rescan_library(library, ["Actress", "Year"], _resolver(_record()), client)

    assert report.links_created == 1
    assert (library / "Year" / "2022" / "ABC-123.mp4").is_symlink()
    assert (library / "Actress" / "Actress One" / "ABC-123.mp4").is_symlink()


def test_rescan_removes_links_for_a_disabled_category(tmp_path, client):
    library, _video = _make_library(tmp_path)
    rescan_library(library, ALL, _resolver(_record()), client)
    assert (library / "Year" / "2022" / "ABC-123.mp4").is_symlink()

    report = rescan_library(library, ["Actress"], _resolver(_record()), client)

    assert report.stale_links_removed >= 1
    assert not (library / "Year").exists()
    assert (library / "Actress" / "Actress One" / "ABC-123.mp4").is_symlink()


def test_rescan_drops_a_genre_folder_that_is_no_longer_in_the_metadata(tmp_path, client):
    """The case that motivated this: editing the genre blocklist should be
    able to clear out folders it now excludes.
    """
    library, _video = _make_library(tmp_path)
    rescan_library(library, ["Genre"], _resolver(_record(genres=["Genre One", "Sample Video"])), client)
    assert (library / "Genre" / "Sample Video" / "ABC-123.mp4").is_symlink()

    report = rescan_library(library, ["Genre"], _resolver(_record(genres=["Genre One"])), client)

    assert report.stale_links_removed == 1
    assert not (library / "Genre" / "Sample Video").exists()
    assert (library / "Genre" / "Genre One" / "ABC-123.mp4").is_symlink()


def test_rescan_prunes_links_whose_target_is_gone(tmp_path, client):
    library, video = _make_library(tmp_path)
    rescan_library(library, ["Actress"], _resolver(_record()), client)
    link = library / "Actress" / "Actress One" / "ABC-123.mp4"
    assert link.is_symlink()

    video.unlink()  # the user deleted the video outside the app

    report = rescan_library(library, ["Actress"], _resolver(_record()), client)

    assert report.broken_links_removed == 1
    assert not link.is_symlink()


def test_rescan_writes_a_missing_nfo(tmp_path, client):
    library, _video = _make_library(tmp_path)

    report = rescan_library(library, [], _resolver(_record()), client)

    assert report.nfos_written == 1
    assert (library / "ABC-123" / "ABC-123.nfo").exists()


def test_rescan_leaves_unmatched_releases_and_their_links_alone(tmp_path, client):
    library, video = _make_library(tmp_path)
    link_dir = library / "Actress" / "Someone"
    link_dir.mkdir(parents=True)
    os.symlink(video, link_dir / video.name)

    report = rescan_library(library, ALL, _resolver(None), client)

    assert report.unmatched == ["ABC-123"]
    assert report.stale_links_removed == 0
    assert (link_dir / video.name).is_symlink()


def test_rescan_does_not_touch_links_pointing_outside_the_library(tmp_path, client):
    """Sort-in-place puts canonical files outside the library root; a
    rescan must not treat those links as stale.
    """
    library, _video = _make_library(tmp_path)
    outside = tmp_path / "elsewhere" / "XYZ-999.mp4"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"other")
    foreign_link = library / "Actress" / "Other Person" / "XYZ-999.mp4"
    foreign_link.parent.mkdir(parents=True)
    os.symlink(outside, foreign_link)

    report = rescan_library(library, ALL, _resolver(_record()), client)

    assert foreign_link.is_symlink()
    assert report.stale_links_removed == 0


def test_rescan_never_moves_or_deletes_videos(tmp_path, client):
    library, video = _make_library(tmp_path)

    rescan_library(library, ALL, _resolver(_record()), client)

    assert video.exists()
    assert video.read_bytes() == b"video data"


def test_rescan_groups_multi_part_releases(tmp_path, client):
    library = tmp_path / "Library"
    folder = library / "ABC-123"
    folder.mkdir(parents=True)
    (folder / "ABC-123-cd1.mp4").write_bytes(b"a")
    (folder / "ABC-123-cd2.mp4").write_bytes(b"b")

    report = rescan_library(library, ["Actress"], _resolver(_record()), client)

    assert report.releases == 1
    assert report.links_created == 2
    assert (library / "Actress" / "Actress One" / "ABC-123-cd1.mp4").is_symlink()
    assert (library / "Actress" / "Actress One" / "ABC-123-cd2.mp4").is_symlink()


def test_rescan_is_idempotent(tmp_path, client):
    library, _video = _make_library(tmp_path)
    rescan_library(library, ALL, _resolver(_record()), client)

    second = rescan_library(library, ALL, _resolver(_record()), client)

    assert second.links_created == 0
    assert second.stale_links_removed == 0
    assert second.broken_links_removed == 0


def test_rescan_can_be_undone(tmp_path, client):
    library, _video = _make_library(tmp_path)
    rescan_library(library, ["Actress"], _resolver(_record()), client)
    removed_link = library / "Actress" / "Actress One" / "ABC-123.mp4"

    # A second rescan with Actress off prunes that link, journalled.
    run_journal = RunJournal(library_root=str(library))
    rescan_library(library, ["Year"], _resolver(_record()), client, journal=run_journal)
    assert not removed_link.is_symlink()

    report = undo(run_journal)

    assert not report.failures
    assert removed_link.is_symlink()
    assert not (library / "Year" / "2022" / "ABC-123.mp4").is_symlink()


def test_rescan_reports_progress_and_honours_cancellation(tmp_path, client):
    library = tmp_path / "Library"
    for content_id in ("ABC-123", "DEF-456", "GHI-789"):
        folder = library / content_id
        folder.mkdir(parents=True)
        (folder / f"{content_id}.mp4").write_bytes(b"x")

    seen = []

    def resolve(content_id):
        return _record(content_id)

    report = rescan_library(
        library,
        ["Actress"],
        resolve,
        client,
        should_cancel=lambda: len(seen) >= 1,
        progress=lambda done, total: seen.append(done),
    )

    assert report.releases == 3
    assert len(seen) == 1  # stopped before starting the second release
