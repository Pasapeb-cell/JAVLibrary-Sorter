import pytest

from javsorter.core.genre_filter import GenreFilter
from javsorter.core.models import MetadataRecord


@pytest.mark.parametrize(
    "genre",
    [
        # Real promotional tags observed in live r18.dev responses.
        "JET Video 40% Off Sale",
        "Prestige Group Autumn Planning Festival",
        "New Year's Eve Sale",
        "Sample Video",
        "Hi-Def",
        "Exclusive Distribution",
    ],
)
def test_default_blocklist_drops_promotional_and_technical_tags(genre):
    assert GenreFilter().is_blocked(genre) is True


@pytest.mark.parametrize(
    "genre",
    [
        "Beautiful Tits",
        "Cheating Wife",
        "Drama",
        "Threesome / Foursome",
        "Nurse",
        "Slender",
        # Must not be caught by the \bsale\b pattern.
        "Female Salesman",
    ],
)
def test_default_blocklist_keeps_real_genres(genre):
    assert GenreFilter().is_blocked(genre) is False


def test_matching_is_case_insensitive():
    assert GenreFilter().is_blocked("sample video") is True
    assert GenreFilter().is_blocked("SAMPLE VIDEO") is True


def test_disabling_defaults_keeps_everything():
    genre_filter = GenreFilter(use_defaults=False)

    assert genre_filter.is_blocked("Sample Video") is False
    assert genre_filter.is_blocked("40% Off Sale") is False


def test_extra_blocked_genres_are_applied():
    genre_filter = GenreFilter(extra_blocked=["Featured Actress"])

    assert genre_filter.is_blocked("Featured Actress") is True
    assert genre_filter.is_blocked("Drama") is False


def test_extra_blocked_works_without_defaults():
    genre_filter = GenreFilter(use_defaults=False, extra_blocked=["Drama"])

    assert genre_filter.is_blocked("Drama") is True
    assert genre_filter.is_blocked("Sample Video") is False


def test_filter_genres_preserves_order_of_survivors():
    genre_filter = GenreFilter()
    genres = ["Beautiful Tits", "Sample Video", "Drama", "Hi-Def", "Nurse"]

    assert genre_filter.filter_genres(genres) == ["Beautiful Tits", "Drama", "Nurse"]


def test_apply_returns_record_with_filtered_genres():
    record = MetadataRecord(
        content_id="ABC-123",
        title="Title",
        genres=["Drama", "Sample Video", "Exclusive Distribution"],
    )

    filtered = GenreFilter().apply(record)

    assert filtered.genres == ["Drama"]
    # Other fields untouched, and the original is not mutated.
    assert filtered.content_id == "ABC-123"
    assert record.genres == ["Drama", "Sample Video", "Exclusive Distribution"]


def test_apply_returns_same_object_when_nothing_blocked():
    record = MetadataRecord(content_id="ABC-123", title="Title", genres=["Drama"])

    assert GenreFilter().apply(record) is record


def test_blank_extra_entries_are_ignored():
    genre_filter = GenreFilter(extra_blocked=["", "   "])

    assert genre_filter.is_blocked("Drama") is False
    assert genre_filter.is_blocked("") is False
