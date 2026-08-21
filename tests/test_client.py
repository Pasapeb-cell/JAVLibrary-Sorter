import pytest
import requests

from javsorter.scraping.client import ScraperClient
from javsorter.scraping.exceptions import NetworkError


@pytest.fixture
def client():
    c = ScraperClient(base_delay=0, jitter=0, retry_backoff=0)
    yield c
    c.close()


def test_connection_error_becomes_network_error(client):
    """Raw requests exceptions must not escape: they'd kill the background
    worker threads that drive the GUI.
    """

    def boom(*args, **kwargs):
        raise requests.exceptions.ConnectionError("network is down")

    client._session.get = boom

    with pytest.raises(NetworkError) as excinfo:
        client.get("https://example.invalid/thing")

    assert "network is down" in str(excinfo.value)


def test_timeout_becomes_network_error(client):
    def boom(*args, **kwargs):
        raise requests.exceptions.Timeout("timed out")

    client._session.get = boom

    with pytest.raises(NetworkError):
        client.get("https://example.invalid/thing")


def test_transient_failure_is_retried_then_succeeds(client, requests_mock):
    requests_mock.get(
        "https://example.invalid/thing",
        [
            {"exc": requests.exceptions.ConnectionError},
            {"text": "recovered", "status_code": 200},
        ],
    )

    response = client.get("https://example.invalid/thing")

    assert response.text == "recovered"


def test_gives_up_after_max_attempts(requests_mock):
    client = ScraperClient(base_delay=0, jitter=0, max_attempts=3, retry_backoff=0)
    matcher = requests_mock.get(
        "https://example.invalid/thing", exc=requests.exceptions.ConnectionError
    )

    with pytest.raises(NetworkError):
        client.get("https://example.invalid/thing")

    assert matcher.call_count == 3
    client.close()


def test_http_error_status_is_not_retried(requests_mock):
    """A 404 is a definitive answer, not a transient fault -- retrying it
    would just be rude to the server.
    """
    client = ScraperClient(base_delay=0, jitter=0, retry_backoff=0)
    matcher = requests_mock.get("https://example.invalid/thing", status_code=404)

    response = client.get("https://example.invalid/thing")

    assert response.status_code == 404
    assert matcher.call_count == 1
    client.close()
