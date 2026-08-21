import pytest

from javsorter.core.models import MatchStatus
from javsorter.core.scanner import scan_folder


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_scan_single_file(tmp_path):
    _touch(tmp_path / "ABC-123.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.extracted.content_id == "ABC-123"
    assert item.status == MatchStatus.ID_FOUND
    assert len(item.parts) == 1


def test_scan_groups_multi_cd_parts_in_order(tmp_path):
    _touch(tmp_path / "ghi-789-cd2.mp4")
    _touch(tmp_path / "ghi-789-cd1.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.extracted.content_id == "GHI-789"
    assert [p.name for p in item.parts] == ["ghi-789-cd1.mp4", "ghi-789-cd2.mp4"]
    assert item.part_labels == ["cd1", "cd2"]


def test_scan_reinterprets_c_as_third_part_when_ab_siblings_exist(tmp_path):
    _touch(tmp_path / "xyz-123-A.mp4")
    _touch(tmp_path / "xyz-123-B.mp4")
    _touch(tmp_path / "xyz-123-C.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.status == MatchStatus.ID_FOUND
    assert item.extracted.uncensored is False
    assert [p.name for p in item.parts] == ["xyz-123-A.mp4", "xyz-123-B.mp4", "xyz-123-C.mp4"]
    assert item.part_labels == ["a", "b", "c"]


def test_scan_standalone_c_marker_is_ambiguous(tmp_path):
    _touch(tmp_path / "def-456-C.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.status == MatchStatus.AMBIGUOUS_ID
    assert item.extracted.uncensored is True


def test_scan_no_id_files_are_kept_separate(tmp_path):
    _touch(tmp_path / "random_video_1.mp4")
    _touch(tmp_path / "random_video_2.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 2
    assert all(item.status == MatchStatus.NO_ID for item in items)


def test_scan_keeps_largest_duplicate_and_sets_others_aside(tmp_path):
    """Same ID with no part markers means competing copies, not discs.
    Renaming them all would collide, so the largest wins and the rest are
    reported instead of being touched.
    """
    smaller = tmp_path / "ABC-123.mp4"
    larger = tmp_path / "ABC-123 [FHD].mkv"
    smaller.write_bytes(b"x" * 100)
    larger.write_bytes(b"x" * 900)

    items = scan_folder(tmp_path)

    assert len(items) == 1
    item = items[0]
    assert item.parts == [larger]
    assert item.part_labels == [None]
    assert item.duplicates == [smaller]
    assert item.note is not None


def test_scan_multi_part_release_is_not_treated_as_duplicates(tmp_path):
    (tmp_path / "ghi-789-cd1.mp4").write_bytes(b"x" * 100)
    (tmp_path / "ghi-789-cd2.mp4").write_bytes(b"x" * 900)

    items = scan_folder(tmp_path)

    assert len(items) == 1
    assert len(items[0].parts) == 2
    assert items[0].duplicates == []


def test_scan_recurses_into_subfolders(tmp_path):
    _touch(tmp_path / "sub" / "ABC-123.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    assert items[0].extracted.content_id == "ABC-123"


def test_scan_ignores_symlinks(tmp_path):
    """Regression: with the library inside the source folder, a re-scan
    used to pick up the app's own category symlinks. Because a symlink
    reports its target's size, the "largest duplicate" tie-break could
    select the symlink as the file to organize and orphan the real video.
    """
    import os

    real = tmp_path / "Library" / "SSIS-001" / "SSIS-001.mp4"
    real.parent.mkdir(parents=True)
    real.write_bytes(b"x" * 512)
    link_dir = tmp_path / "Library" / "Actress" / "Someone"
    link_dir.mkdir(parents=True)
    try:
        os.symlink(real, link_dir / "SSIS-001.mp4")
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    assert items[0].parts == [real]
    assert items[0].duplicates == []


def test_scan_handles_non_ascii_filenames(tmp_path):
    _touch(tmp_path / "【高画質】ABC-123 中文字幕.mp4")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    assert items[0].extracted.content_id == "ABC-123"


def test_scan_ignores_non_video_files(tmp_path):
    _touch(tmp_path / "ABC-123.mp4")
    _touch(tmp_path / "ABC-123.nfo")
    _touch(tmp_path / "readme.txt")

    items = scan_folder(tmp_path)

    assert len(items) == 1
    assert len(items[0].parts) == 1
