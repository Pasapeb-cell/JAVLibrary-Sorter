"""Live checks against the real r18.dev API.

Excluded from the default test run (see `addopts` in pyproject.toml).
Run explicitly with: pytest -m live
Purpose: catch drift between the committed JSON fixtures and reality.
"""

import pytest

from javsorter.scraping.client import ScraperClient
from javsorter.scraping.parser import parse_detail
from javsorter.scraping.r18 import fetch_by_dvd_id


@pytest.mark.live
def test_live_known_id_still_resolves():
    with ScraperClient() as client:
        data = fetch_by_dvd_id(client, "SSIS-001")
    record = parse_detail(data, requested_id="SSIS-001")

    assert record.content_id == "SSIS-001"
    assert record.title
    assert record.actresses
