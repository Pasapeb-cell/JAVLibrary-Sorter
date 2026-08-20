from __future__ import annotations

import random
import time

import requests

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
    ):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._rate_limiter = RateLimiter(base_delay=base_delay, jitter=jitter)

    def get(self, url: str, timeout: float = 20.0) -> requests.Response:
        self._rate_limiter.wait()
        return self._session.get(url, timeout=timeout)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "ScraperClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
