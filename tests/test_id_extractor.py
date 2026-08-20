import pytest

from javsorter.core.id_extractor import extract_id


@pytest.mark.parametrize(
    "filename, expected_content_id, expected_uncensored, expected_part_label, expected_ambiguous",
    [
        ("ABC-123.mp4", "ABC-123", False, None, False),
        ("abc-123.mkv", "ABC-123", False, None, False),
        ("SSNI-999 [1080p].mkv", "SSNI-999", False, None, False),
        # Leading site-tag/watermark prefix.
        ("hhd800.com@MIAB-369.mp4", "MIAB-369", False, None, False),
        # Uncensored marker plus a trailing release-group suffix.
        ("MIDV-751-C_GG5.mp4", "MIDV-751-C", True, None, True),
        # Dot-attached resolution tag rather than bracketed/spaced.
        ("MIST-435.1080p.mp4", "MIST-435", False, None, False),
        # Standalone uncensored marker, no A/B siblings in this test.
        ("def-456-C.mp4", "DEF-456-C", True, None, True),
        # Multi-CD release.
        ("ghi-789-cd1.mp4", "GHI-789", False, "cd1", False),
        ("ghi-789-cd2.mp4", "GHI-789", False, "cd2", False),
        # Unambiguous A/B part markers.
        ("xyz-123-A.mp4", "XYZ-123", False, "a", False),
        ("xyz-123-B.mp4", "XYZ-123", False, "b", False),
    ],
)
def test_extract_id_cases(
    filename, expected_content_id, expected_uncensored, expected_part_label, expected_ambiguous
):
    result = extract_id(filename)
    assert result.content_id == expected_content_id
    assert result.uncensored == expected_uncensored
    assert result.part_label == expected_part_label
    assert result.ambiguous_part_marker == expected_ambiguous


def test_extract_id_no_id_found():
    result = extract_id("random_video_file_2024.mp4")
    assert result.content_id is None
    assert result.high_confidence is False


def test_base_id_strips_uncensored_suffix():
    result = extract_id("def-456-C.mp4")
    assert result.content_id == "DEF-456-C"
    assert result.base_id == "DEF-456"
