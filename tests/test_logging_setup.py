import logging

from javsorter.logging_setup import (
    QtLogHandler,
    attach_qt_handler,
    configure_file_logging,
    detach_qt_handler,
    get_logger,
)


def test_configure_file_logging_writes_to_a_file(tmp_path):
    log_path = configure_file_logging(tmp_path / "logs")
    try:
        get_logger("test").info("hello from the test")
        for handler in get_logger().handlers:
            handler.flush()

        assert log_path.exists()
        assert "hello from the test" in log_path.read_text(encoding="utf-8")
    finally:
        _reset_root_logger()


def test_configure_file_logging_is_idempotent(tmp_path):
    """Called twice (tests, a reopened window), it must not double every line."""
    try:
        configure_file_logging(tmp_path / "logs")
        configure_file_logging(tmp_path / "logs")

        file_handlers = [
            h for h in get_logger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 1
    finally:
        _reset_root_logger()


def test_qt_handler_forwards_records(qtbot):
    handler = QtLogHandler()
    received = []
    handler.signals.message.connect(lambda msg, lvl: received.append((msg, lvl)))
    attach_qt_handler(handler)
    logger = get_logger()
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        get_logger("test").warning("careful")

        assert received
        message, level = received[-1]
        assert message == "careful"
        assert level == logging.WARNING
    finally:
        detach_qt_handler(handler)
        logger.setLevel(previous_level)


def _reset_root_logger():
    logger = get_logger()
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
