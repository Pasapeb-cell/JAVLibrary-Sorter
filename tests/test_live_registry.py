import os

import pytest

from javsorter.scraping.actress_registry import RegistryManager
from javsorter.scraping.client import ScraperClient
from javsorter.scraping.registry_download import download_and_activate
from javsorter.scraping.r18 import fetch_by_dvd_id
from javsorter.scraping.parser import parse_detail


@pytest.mark.live
def test_live_registry_recovers_known_bad_title(tmp_path):
    """Opt-in effectiveness gate for a user-supplied known-bad title.

    Set ``JAVSORTER_LIVE_BAD_ID`` and pipe-delimited
    ``JAVSORTER_LIVE_EXPECTED_ACTRESSES`` before running ``pytest -m live``.
    The dump is large, so this remains an explicit user-triggered check.
    """
    content_id = os.getenv("JAVSORTER_LIVE_BAD_ID")
    expected_value = os.getenv("JAVSORTER_LIVE_EXPECTED_ACTRESSES")
    if not content_id or not expected_value:
        pytest.skip("set JAVSORTER_LIVE_BAD_ID and JAVSORTER_LIVE_EXPECTED_ACTRESSES")
    expected = tuple(name.strip() for name in expected_value.split("|") if name.strip())
    assert expected

    with ScraperClient() as client:
        baseline = parse_detail(fetch_by_dvd_id(client, content_id), requested_id=content_id)
        manager = RegistryManager(tmp_path / "registry")
        download_and_activate(manager, client, "https://r18.dev/dumps/latest")
    index = manager.open_active()
    assert index is not None
    try:
        match = index.lookup(content_id)
        assert match.is_exact
        assert tuple(identity.canonical_name for identity in match.actresses) == expected
        assert tuple(baseline.actresses) != expected
    finally:
        index.close()
