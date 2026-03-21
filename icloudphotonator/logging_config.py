from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path


def setup_logging(
    log_dir: Path | None = None, level: int = logging.INFO
) -> logging.Logger:
    """Configure structured logging for iCloudPhotonator."""

    logger = logging.getLogger("icloudphotonator")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))

    if log_dir is None:
        log_dir = Path.home() / ".icloudphotonator" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "icloudphotonator.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger


class LogBuffer:
    """In-memory ring buffer for recent log entries, used by the UI."""

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[dict[str, str]] = []
        self._max = max_entries

    def add(
        self, level: str, message: str, timestamp: datetime | None = None
    ) -> None:
        entry = {
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "level": level,
            "message": message,
        }
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries.pop(0)

    def get_recent(self, count: int = 100) -> list[dict[str, str]]:
        return self._entries[-count:]

    def clear(self) -> None:
        self._entries.clear()

    def as_handler(self) -> logging.Handler:
        """Return a logging.Handler that feeds into this buffer."""

        handler = _BufferHandler(self)
        handler.setLevel(logging.INFO)
        return handler


class _BufferHandler(logging.Handler):
    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.add(record.levelname, self.format(record))