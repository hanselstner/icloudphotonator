from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("icloudphotonator.resilience")


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 5.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0

    def get_delay(self, attempt: int) -> float:
        return min(self.base_delay * (self.backoff_factor**attempt), self.max_delay)


class NetworkMonitor:
    """Monitors network path availability."""

    def __init__(
        self,
        path: Path,
        check_interval: float = 10.0,
        on_disconnect: Callable[[], Any] | None = None,
        on_reconnect: Callable[[], Any] | None = None,
    ) -> None:
        self._path = path
        self._check_interval = check_interval
        self._disconnect_callbacks: list[Callable[[], Any]] = []
        self._reconnect_callbacks: list[Callable[[], Any]] = []
        if on_disconnect is not None:
            self._disconnect_callbacks.append(on_disconnect)
        if on_reconnect is not None:
            self._reconnect_callbacks.append(on_reconnect)
        self._is_available = True
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def is_available(self) -> bool:
        return self._is_available

    def on_disconnect(self, callback: Callable[[], Any]) -> None:
        """Register a callback for disconnect events."""

        self._disconnect_callbacks.append(callback)

    def on_reconnect(self, callback: Callable[[], Any]) -> None:
        """Register a callback for reconnect events."""

        self._reconnect_callbacks.append(callback)

    def start(self) -> None:
        """Start monitoring in the background."""

        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        """Stop monitoring."""

        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _monitor_loop(self) -> None:
        try:
            while self._running:
                available = self._check_path()
                if available != self._is_available:
                    self._is_available = available
                    if available:
                        logger.info("Network path available: %s", self._path)
                        await self._notify_callbacks(self._reconnect_callbacks)
                    else:
                        logger.warning("Network path unavailable: %s", self._path)
                        await self._notify_callbacks(self._disconnect_callbacks)
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            raise

    async def _notify_callbacks(self, callbacks: list[Callable[[], Any]]) -> None:
        for callback in list(callbacks):
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                logger.exception("Network monitor callback failed for %s", self._path)

    def _check_path(self) -> bool:
        """Check if the network path is accessible."""

        try:
            os.stat(self._path)
        except (OSError, PermissionError):
            return False
        return True


async def retry_with_policy(
    func: Callable[..., Any], policy: RetryPolicy, *args: Any, **kwargs: Any
) -> Any:
    """Execute ``func`` with retry logic. ``func`` can be sync or async."""

    last_error: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < policy.max_retries:
                delay = policy.get_delay(attempt)
                logger.warning(
                    "Attempt %s failed: %s. Retrying in %.1fs...",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %s attempts failed. Last error: %s",
                    policy.max_retries + 1,
                    exc,
                )

    if last_error is None:
        raise RuntimeError("retry_with_policy exhausted without capturing an error")
    raise last_error


class FileOperationGuard:
    """Wrap file operations with timeout and error handling."""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    async def copy_with_timeout(self, src: Path, dst: Path) -> bool:
        """Copy a file with timeout protection."""

        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, self._copy_file, src, dst),
                timeout=self.timeout,
            )
            return True
        except asyncio.TimeoutError as exc:
            logger.error("File copy timed out after %ss: %s", self.timeout, src)
            self._cleanup_partial(dst)
            raise TimeoutError(f"File copy timed out after {self.timeout}s: {src}") from exc
        except OSError as exc:
            logger.error("File copy failed: %s → %s: %s", src, dst, exc)
            self._cleanup_partial(dst)
            raise

    @staticmethod
    def _copy_file(src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        if src.stat().st_size != dst.stat().st_size:
            raise OSError(f"Copied file size mismatch for {src}")

    @staticmethod
    def _cleanup_partial(dst: Path) -> None:
        try:
            if dst.exists():
                dst.unlink()
        except OSError:
            logger.warning("Failed to clean up partial file: %s", dst)