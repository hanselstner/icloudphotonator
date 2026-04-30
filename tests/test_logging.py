from datetime import datetime
import logging
import logging.handlers
from pathlib import Path

import pytest

from icloudphotonator.logging_config import LogBuffer, read_log_tail, setup_logging


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


def test_read_log_tail_returns_last_n_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "icloudphotonator.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(1, 101)) + "\n", encoding="utf-8")

    tail = read_log_tail(log_file, max_lines=10)

    assert tail == [f"line {i}" for i in range(91, 101)]


def test_read_log_tail_handles_missing_file(tmp_path: Path) -> None:
    assert read_log_tail(tmp_path / "does_not_exist.log") == []


def test_read_log_tail_caps_lines_for_large_file(tmp_path: Path) -> None:
    log_file = tmp_path / "huge.log"
    with open(log_file, "w", encoding="utf-8") as fh:
        for i in range(50_000):
            fh.write(f"entry {i}\n")

    tail = read_log_tail(log_file, max_lines=40)

    assert len(tail) == 40
    assert tail[0] == "entry 49960"
    assert tail[-1] == "entry 49999"