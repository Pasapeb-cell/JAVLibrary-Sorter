class ScrapeError(Exception):
    """Base class for errors talking to the metadata source."""


class NoMatchError(ScrapeError):
    """No metadata exists for this content ID."""


class NetworkError(ScrapeError):
    """A non-2xx, non-404 response was returned by the metadata source."""
