from datetime import datetime
import logging
import logging.handlers
from pathlib import Path

import pytest

from icloudphotonator.logging_config import LogBuffer, setup_logging


@pytest.fixture
def app_logger() -> logging.Logger:
    logger = logging.getLogger("icloudphotonator")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    yield logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_setup_logging_creates_logger_with_handlers(
    tmp_path: Path, app_logger: logging.Logger
) -> None:
    logger = setup_logging(tmp_path / "logs")

    logger.info("hello")

    assert logger is app_logger
    assert len(logger.handlers) == 2
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)
    assert any(
        isinstance(handler, logging.handlers.RotatingFileHandler)
        for handler in logger.handlers
    )
    assert (tmp_path / "logs" / "icloudphotonator.log").exists()


def test_log_buffer_add_and_get_recent() -> None:
    buffer = LogBuffer()
    timestamp = datetime(2024, 1, 2, 3, 4, 5)

    buffer.add("INFO", "hello", timestamp=timestamp)

    assert buffer.get_recent() == [
        {
            "timestamp": timestamp.isoformat(),
            "level": "INFO",
            "message": "hello",
        }
    ]


def test_log_buffer_max_entries_limit() -> None:
    buffer = LogBuffer(max_entries=2)

    buffer.add("INFO", "first")
    buffer.add("WARNING", "second")
    buffer.add("ERROR", "third")

    assert [entry["message"] for entry in buffer.get_recent()] == ["second", "third"]


def test_log_buffer_as_handler_works_with_logging() -> None:
    buffer = LogBuffer()
    logger = logging.getLogger("tests.log_buffer")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        existing.close()

    handler = buffer.as_handler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    logger.info("buffered message")

    assert buffer.get_recent(1)[0]["level"] == "INFO"
    assert buffer.get_recent(1)[0]["message"] == "buffered message"

    logger.removeHandler(handler)
    handler.close()