from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, Signal

LOGGER_NAME = "javsorter"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def configure_file_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    """Send the app's log to a rotating file.

    Without this the log only ever exists in the GUI panel and dies with
    the window, which leaves a long run unauditable after the fact.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "javsorter.log"

    logger = get_logger()
    logger.setLevel(level)
    # Guard against adding a second handler if this runs twice (tests,
    # a reopened window), which would double every line in the file.
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return log_path

    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)
    return log_path


class _LogSignals(QObject):
    message = Signal(str, int)


class QtLogHandler(logging.Handler):
    """Forwards log records to the GUI via a Qt signal.

    Workers log from background threads, so the records have to cross to
    the GUI thread; a queued signal connection is what makes that safe.
    """

    def __init__(self):
        super().__init__()
        self.signals = _LogSignals()
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.signals.message.emit(self.format(record), record.levelno)
        except RuntimeError:
            # The receiving widget was destroyed (window closing).
            pass


def attach_qt_handler(handler: QtLogHandler) -> None:
    get_logger().addHandler(handler)


def detach_qt_handler(handler: QtLogHandler) -> None:
    get_logger().removeHandler(handler)
