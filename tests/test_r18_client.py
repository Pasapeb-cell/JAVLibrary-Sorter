import json
from pathlib import Path

import pytest

from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NetworkError, NoMatchError
from javsorter.scraping.r18 import fetch_by_dvd_id

FIXTURES = Path(__file__).parent / "fixtures" / "json"


@pytest.fixture
def client():
    c = ScraperClient(base_delay=0, jitter=0)
    yield c
    c.close()


def test_fetch_by_dvd_id_success(requests_mock, client):
    payload = json.loads((FIXTURES / "ssis-001.json").read_text(encoding="utf-8"))
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        json=payload,
    )

    data = fetch_by_dvd_id(client, "SSIS-001")

    assert data["title"] == payload["title"]


def test_fetch_by_dvd_id_not_found(requests_mock, client):
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=ZZZZ-999/json",
        status_code=404,
        text="Not Found",
    )

    with pytest.raises(NoMatchError):
        fetch_by_dvd_id(client, "ZZZZ-999")


def test_fetch_by_dvd_id_server_error(requests_mock, client):
    requests_mock.get(
        "https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json",
        status_code=503,
        text="Service Unavailable",
    )

    with pytest.raises(NetworkError):
        fetch_by_dvd_id(client, "SSIS-001")
