from __future__ import annotations

import random
import time

import requests

from .exceptions import NetworkError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class RateLimiter:
    """Enforces a minimum delay (plus jitter) between successive requests."""

    def __init__(self, base_delay: float = 1.5, jitter: float = 1.0):
        self.base_delay = base_delay
        self.jitter = jitter
        self._last_request_at: float | None = None

    def wait(self) -> None:
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            delay = self.base_delay + random.uniform(0, self.jitter)
            remaining = delay - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()


class ScraperClient:
    """Rate-limited HTTP client shared by every request to the metadata
    source, so no code path can accidentally bypass the politeness delay.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        base_delay: float = 1.5,
        jitter: float = 1.0,
        max_attempts: int = 3,
        retry_backoff: float = 1.0,
    ):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._rate_limiter = RateLimiter(base_delay=base_delay, jitter=jitter)
        self._max_attempts = max(1, max_attempts)
        self._retry_backoff = retry_backoff

    def get(self, url: str, timeout: float = 20.0) -> requests.Response:
        """Fetch a URL, retrying transient failures with a backoff.

        Connection/timeout errors surface as NetworkError rather than
        raw requests exceptions, so every caller has a single error type
        to handle -- letting requests' own exceptions escape would kill
        the background worker threads that drive the GUI.
        """
        self._rate_limiter.wait()

        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                return self._session.get(url, timeout=timeout)
            except requests.RequestException as exc:
                last_error = exc
                if attempt + 1 < self._max_attempts:
                    time.sleep(self._retry_backoff * (2**attempt))
                    self._rate_limiter.wait()

        raise NetworkError(f"{url}: {last_error}") from last_error

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "ScraperClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
