from pathlib import Path

import pytest

from icloudphotonator.db import Database
from icloudphotonator.importer import PhotoImporter
from icloudphotonator.orchestrator import ImportOrchestrator
from icloudphotonator.staging import StagingManager
from icloudphotonator.state import JobState
from icloudphotonator.throttle import ThrottleController


@pytest.fixture(autouse=True)
def skip_osxphotos_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)


def test_orchestrator_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    staging_dir = tmp_path / "staging"

    orchestrator = ImportOrchestrator(db_path, staging_dir)

    assert isinstance(orchestrator.db, Database)
    assert isinstance(orchestrator.throttle, ThrottleController)
    assert isinstance(orchestrator.staging, StagingManager)
    assert isinstance(orchestrator.importer, PhotoImporter)
    assert orchestrator.db.db_path == db_path
    assert orchestrator.staging.staging_dir == staging_dir
    assert orchestrator._paused.is_set()
    assert orchestrator._cancelled is False


def test_pause_resume_cancel_flags(tmp_path: Path) -> None:
    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")

    orchestrator.pause()
    assert orchestrator._paused.is_set() is False

    orchestrator.resume()
    assert orchestrator._paused.is_set() is True

    orchestrator.cancel()
    assert orchestrator._cancelled is True
    assert orchestrator._paused.is_set() is True


class StubNetworkMonitor:
    instances: list["StubNetworkMonitor"] = []

    def __init__(self, path: Path, check_interval: float = 10.0) -> None:
        self.path = path
        self.check_interval = check_interval
        self.disconnect_callbacks: list = []
        self.reconnect_callbacks: list = []
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def on_disconnect(self, callback) -> None:
        self.disconnect_callbacks.append(callback)

    def on_reconnect(self, callback) -> None:
        self.reconnect_callbacks.append(callback)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


async def _complete_scan(self, job, source_path: Path) -> None:
    self.db.update_job_state(job.job_id, JobState.DEDUPLICATING)


async def _complete_import(self, job) -> None:
    self.db.update_job_state(job.job_id, JobState.VERIFYING)


@pytest.mark.asyncio
async def test_start_import_creates_network_monitor_for_network_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubNetworkMonitor.instances.clear()
    monkeypatch.setattr("icloudphotonator.orchestrator.NetworkMonitor", StubNetworkMonitor)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: True)
    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", _complete_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", _complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    source_path = tmp_path / "network-source"

    await orchestrator.start_import(source_path)

    assert len(StubNetworkMonitor.instances) == 1
    monitor = StubNetworkMonitor.instances[0]
    assert monitor.path == source_path
    assert monitor.check_interval == 10
    assert monitor.started is True
    assert monitor.stopped is True
    assert len(monitor.disconnect_callbacks) == 1
    assert len(monitor.reconnect_callbacks) == 1


@pytest.mark.asyncio
async def test_start_import_skips_network_monitor_for_local_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubNetworkMonitor.instances.clear()
    monkeypatch.setattr("icloudphotonator.orchestrator.NetworkMonitor", StubNetworkMonitor)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)
    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", _complete_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", _complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")

    await orchestrator.start_import(tmp_path / "local-source")

    assert StubNetworkMonitor.instances == []