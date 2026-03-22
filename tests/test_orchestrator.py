import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from icloudphotonator.db import Database
from icloudphotonator.importer import PhotoImporter
from icloudphotonator.job import Job
from icloudphotonator.orchestrator import ImportOrchestrator
from icloudphotonator.persistence import load_active_job
from icloudphotonator.scanner import ScanCancelledError
from icloudphotonator.staging import StagingManager
from icloudphotonator.state import FileStatus, JobState
from icloudphotonator.throttle import ThrottleController


@pytest.fixture(autouse=True)
def skip_osxphotos_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)


def test_orchestrator_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    staging_dir = tmp_path / "staging"
    library = tmp_path / "Shared.photoslibrary"
    library.mkdir()

    orchestrator = ImportOrchestrator(db_path, staging_dir, library=library)

    assert isinstance(orchestrator.db, Database)
    assert isinstance(orchestrator.throttle, ThrottleController)
    assert isinstance(orchestrator.staging, StagingManager)
    assert isinstance(orchestrator.importer, PhotoImporter)
    assert orchestrator.db.db_path == db_path
    assert orchestrator.staging.staging_dir == staging_dir
    assert orchestrator.library == library
    assert orchestrator._paused.is_set()
    assert orchestrator._paused_thread.is_set()
    assert orchestrator._cancelled is False
    assert orchestrator._cancel_thread.is_set() is False


def test_pause_resume_cancel_flags(tmp_path: Path) -> None:
    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")

    orchestrator.pause()
    assert orchestrator._paused.is_set() is False
    assert orchestrator._paused_thread.is_set() is False

    orchestrator.resume()
    assert orchestrator._paused.is_set() is True
    assert orchestrator._paused_thread.is_set() is True

    orchestrator.cancel()
    assert orchestrator._cancelled is True
    assert orchestrator._paused.is_set() is True
    assert orchestrator._paused_thread.is_set() is True
    assert orchestrator._cancel_thread.is_set() is True


@pytest.mark.asyncio
async def test_start_import_cancel_during_scan_stops_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    active_job_path = tmp_path / "active_job.json"
    seen_callbacks: dict[str, bool] = {}
    scan_started = threading.Event()

    def fake_scan(self, progress_callback=None, pause_check=None, cancel_check=None):
        seen_callbacks["progress"] = progress_callback is not None
        seen_callbacks["pause"] = pause_check is not None
        seen_callbacks["cancel"] = cancel_check is not None
        scan_started.set()
        while True:
            pause_check()
            if cancel_check():
                raise ScanCancelledError("scan cancelled")
            threading.Event().wait(0.01)

    async def fail_import(self, job) -> None:
        raise AssertionError("import phase should not run after scan cancellation")

    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner.scan", fake_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", fail_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db", active_job_path=active_job_path)

    task = asyncio.create_task(orchestrator.start_import(source_path))
    await asyncio.to_thread(scan_started.wait, 1)
    orchestrator.cancel()
    job_id = await task

    assert job_id
    assert seen_callbacks == {"progress": True, "pause": True, "cancel": True}
    assert orchestrator.db.get_job(job_id)["state"] == JobState.CANCELLED.value
    assert orchestrator.db.get_job_stats(job_id)["total"] == 0
    assert active_job_path.exists() is False


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


@pytest.mark.asyncio
async def test_resume_existing_job_requeues_files_skips_scan_and_clears_active_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        (source_path / name).write_bytes(b"image-bytes")

    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job(source_path, {})
    db.update_job_state(job_id, JobState.ERROR)
    error_id = db.add_file(job_id, source_path / "a.jpg", 1, "hash-a", "image")
    importing_id = db.add_file(job_id, source_path / "b.jpg", 1, "hash-b", "image")
    pending_id = db.add_file(job_id, source_path / "c.jpg", 1, "hash-c", "image")
    db.update_file_status(error_id, FileStatus.ERROR, error_message="failed")
    db.update_file_status(importing_id, FileStatus.IMPORTING)
    db.update_file_status(pending_id, FileStatus.PENDING)

    active_job_path = tmp_path / "active_job.json"
    seen_pending: dict[str, list[str]] = {}

    async def fail_scan(self, job, source_path: Path) -> None:
        raise AssertionError("scan phase should be skipped for persisted jobs")

    async def complete_import(self, job) -> None:
        pending_rows = self.db.get_pending_files(job.job_id, limit=10)
        seen_pending["statuses"] = [row["status"] for row in pending_rows]
        seen_pending["paths"] = [Path(row["path"]).name for row in pending_rows]
        active_payload = load_active_job(active_job_path)
        assert active_payload is not None
        assert active_payload["job_id"] == job.job_id
        for row in pending_rows:
            self.db.update_file_status(row["id"], FileStatus.IMPORTED)
        self.db.update_job_state(job.job_id, JobState.VERIFYING)

    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", fail_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db", active_job_path=active_job_path)

    resumed_job_id = await orchestrator.start_import(source_path, job_id=job_id)

    assert resumed_job_id == job_id
    assert seen_pending["statuses"] == [FileStatus.PENDING.value, FileStatus.PENDING.value, FileStatus.PENDING.value]
    assert seen_pending["paths"] == ["a.jpg", "b.jpg", "c.jpg"]
    assert db.get_job(job_id)["state"] == JobState.COMPLETED.value
    assert db.get_job_stats(job_id)[FileStatus.IMPORTED.value] == 3
    assert active_job_path.exists() is False


@pytest.mark.asyncio
async def test_resume_existing_job_scans_when_no_files_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job(source_path, {})
    db.update_job_state(job_id, JobState.ERROR)

    calls: dict[str, int] = {"scan": 0, "import": 0}

    async def complete_scan(self, job, source_path: Path) -> None:
        calls["scan"] += 1
        self.db.add_file(job.job_id, source_path / "new.jpg", 1, "hash-new", "image")
        self.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    async def complete_import(self, job) -> None:
        calls["import"] += 1
        for row in self.db.get_pending_files(job.job_id, limit=10):
            self.db.update_file_status(row["id"], FileStatus.IMPORTED)
        self.db.update_job_state(job.job_id, JobState.VERIFYING)

    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", complete_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db", active_job_path=tmp_path / "active_job.json")

    await orchestrator.start_import(source_path, job_id=job_id)

    assert calls == {"scan": 1, "import": 1}
    assert db.get_job(job_id)["state"] == JobState.COMPLETED.value


@pytest.mark.asyncio
async def test_import_phase_passes_library_to_importer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "a.jpg"
    file_path.write_bytes(b"image-bytes")
    library = tmp_path / "Family.photoslibrary"
    library.mkdir()

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db", library=library)
    job = Job(orchestrator.db)
    job.start(source_path)
    orchestrator.db.add_file(job.job_id, file_path, 1, "hash-a", "image")
    orchestrator.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    captured: dict[str, Path | None] = {}

    monkeypatch.setattr(
        "icloudphotonator.orchestrator.DeduplicationEngine.check_duplicates",
        lambda self, file_infos: (file_infos, []),
    )

    async def fake_stage_files(unique_files):
        return [(file_info, file_info.path) for file_info in unique_files], []

    def fake_import_batch(
        file_paths,
        skip_dups=True,
        auto_live=True,
        use_exiftool=True,
        report_dir=None,
        timeout=600,
        library=None,
    ):
        captured["library"] = library
        return SimpleNamespace(error_count=0)

    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)
    monkeypatch.setattr(
        orchestrator,
        "_apply_report",
        lambda *args, **kwargs: {str(file_path)},
    )

    await orchestrator._import_phase(job)

    assert captured["library"] == library