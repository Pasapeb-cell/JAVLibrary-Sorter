import os
from pathlib import Path

import pytest

from javsorter.organize.longpath import MAX_COMPONENT, extended, is_too_long, truncate_component
from javsorter.organize.namer import sanitize_component

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows path semantics")


def test_short_component_untouched():
    assert truncate_component("Tsukasa Aoi") == "Tsukasa Aoi"


def test_long_component_truncated():
    result = truncate_component("A" * 300)

    assert len(result) == MAX_COMPONENT


def test_truncation_does_not_leave_a_trailing_dot_or_space():
    # A component ending in "." or " " is invalid on Windows.
    result = truncate_component("A" * (MAX_COMPONENT - 1) + ". padding")

    assert not result.endswith((" ", "."))


def test_sanitize_component_applies_truncation():
    result = sanitize_component("Some / Very " + "Long" * 100)

    assert len(result) <= MAX_COMPONENT
    assert "/" not in result


@windows_only
def test_ordinary_path_is_not_rewritten():
    path = Path(r"C:\Library\ABC-123\ABC-123.mp4")

    assert extended(path) == path


@windows_only
def test_overlong_path_gets_the_extended_prefix():
    path = Path("C:\\Library\\" + "\\".join("d" * 40 for _ in range(10)) + "\\ABC-123.mp4")
    assert is_too_long(path)

    result = str(extended(path))

    assert result.startswith("\\\\?\\")
    assert "ABC-123.mp4" in result


@windows_only
def test_already_prefixed_path_is_left_alone():
    path = Path("\\\\?\\C:\\Library\\" + "d" * 300 + "\\ABC-123.mp4")

    assert extended(path) == path


@windows_only
def test_overlong_unc_path_uses_the_unc_form():
    path = Path("\\\\server\\share\\" + "\\".join("d" * 40 for _ in range(10)) + "\\ABC-123.mp4")

    result = str(extended(path))

    assert result.startswith("\\\\?\\UNC\\server\\share")


@windows_only
def test_can_actually_write_through_a_very_long_path(tmp_path):
    """The point of the prefix: a real write that would otherwise fail."""
    deep = tmp_path
    for _ in range(12):
        deep = deep / ("d" * 30)
    target = deep / "ABC-123.nfo"

    Path(extended(deep)).mkdir(parents=True, exist_ok=True)
    Path(extended(target)).write_text("ok", encoding="utf-8")

    assert Path(extended(target)).read_text(encoding="utf-8") == "ok"
