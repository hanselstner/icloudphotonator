import asyncio
from pathlib import Path

import pytest

from icloudphotonator.resilience import (
    FileOperationGuard,
    NetworkMonitor,
    RetryPolicy,
    retry_with_policy,
)


def test_retry_policy_delay_calculation() -> None:
    policy = RetryPolicy(base_delay=2.0, backoff_factor=2.0, max_delay=60.0)

    assert policy.get_delay(0) == 2.0
    assert policy.get_delay(1) == 4.0
    assert policy.get_delay(2) == 8.0


def test_retry_policy_max_delay_cap() -> None:
    policy = RetryPolicy(base_delay=10.0, backoff_factor=3.0, max_delay=25.0)

    assert policy.get_delay(1) == 25.0
    assert policy.get_delay(4) == 25.0


@pytest.mark.parametrize("exists", [True, False])
def test_network_monitor_check_path(tmp_path: Path, exists: bool) -> None:
    path = tmp_path / "network-share"
    if exists:
        path.mkdir()

    monitor = NetworkMonitor(path)

    assert monitor._check_path() is exists


@pytest.mark.asyncio
async def test_file_operation_guard_copy_with_timeout(tmp_path: Path) -> None:
    src = tmp_path / "source.jpg"
    dst = tmp_path / "nested" / "copy.jpg"
    src.write_bytes(b"image-bytes")

    guard = FileOperationGuard(timeout=1.0)

    assert await guard.copy_with_timeout(src, dst) is True
    assert dst.read_bytes() == b"image-bytes"


@pytest.mark.asyncio
async def test_file_operation_guard_cleans_up_partial_file_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "source.jpg"
    dst = tmp_path / "copy.jpg"
    src.write_bytes(b"image-bytes")

    guard = FileOperationGuard(timeout=1.0)

    def broken_copy(source: Path, target: Path) -> None:
        target.write_bytes(b"partial")
        raise OSError("copy failed")

    monkeypatch.setattr(guard, "_copy_file", broken_copy)

    with pytest.raises(OSError, match="copy failed"):
        await guard.copy_with_timeout(src, dst)

    assert dst.exists() is False


@pytest.mark.asyncio
async def test_network_monitor_detects_path_becoming_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "network-share"
    path.mkdir()
    monitor = NetworkMonitor(path, check_interval=0.01)
    disconnected = asyncio.Event()
    states = iter([True, False, False])

    monitor.on_disconnect(lambda: disconnected.set())
    monkeypatch.setattr(monitor, "_check_path", lambda: next(states, False))

    monitor.start()
    try:
        await asyncio.wait_for(disconnected.wait(), timeout=0.2)
    finally:
        monitor.stop()

    assert monitor.is_available is False


@pytest.mark.asyncio
async def test_retry_with_policy_succeeds_on_first_try() -> None:
    async def succeed(value: str) -> str:
        return value

    result = await retry_with_policy(succeed, RetryPolicy(), "ok")

    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_with_policy_retries_then_succeeds() -> None:
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary failure")
        return "done"

    result = await retry_with_policy(flaky, RetryPolicy(max_retries=3, base_delay=0.0))

    assert result == "done"
    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_with_policy_raises_after_max_retries() -> None:
    attempts = 0

    def always_fail() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("permanent failure")

    with pytest.raises(ValueError, match="permanent failure"):
        await retry_with_policy(
            always_fail,
            RetryPolicy(max_retries=2, base_delay=0.0),
        )

    assert attempts == 3