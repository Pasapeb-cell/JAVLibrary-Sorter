from pathlib import Path

from javsorter.organize.namer import (
    cover_filename,
    library_filename,
    library_path,
    nfo_filename,
    sanitize_component,
)


def test_sanitize_component_strips_illegal_characters():
    # Real genre name from r18.dev containing a path separator.
    assert sanitize_component("Threesome / Foursome") == "Threesome _ Foursome"


def test_sanitize_component_strips_trailing_dots_and_spaces():
    assert sanitize_component("Some Name. ") == "Some Name"


def test_sanitize_component_empty_falls_back():
    assert sanitize_component("...") == "_"


def test_library_filename_without_part():
    assert library_filename("ABC-123", ".mp4") == "ABC-123.mp4"


def test_library_filename_with_part():
    assert library_filename("ABC-123", ".mp4", "cd1") == "ABC-123-cd1.mp4"


def test_library_path():
    assert library_path(Path("Library"), "ABC-123") == Path("Library/ABC-123")


def test_nfo_and_cover_filenames_ignore_part_label():
    assert nfo_filename("ABC-123") == "ABC-123.nfo"
    assert cover_filename("ABC-123") == "ABC-123-thumb.jpg"
