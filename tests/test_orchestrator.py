import asyncio
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from icloudphotonator.db import Database
from icloudphotonator.importer import PhotoImporter
from icloudphotonator.job import Job
from icloudphotonator.orchestrator import ImportOrchestrator
from icloudphotonator.persistence import load_active_job
from icloudphotonator.scanner import FileInfo, MediaType, ScanCancelledError
from icloudphotonator.staging import StagingManager
from icloudphotonator.state import FileStatus, JobState
from icloudphotonator.throttle import ThrottleController


@pytest.fixture(autouse=True)
def skip_osxphotos_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)


@pytest.fixture(autouse=True)
def mock_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock all preflight osascript calls so tests never hit real subprocess."""
    from icloudphotonator.photos_preflight import PhotosPreflight, PreflightResult

    monkeypatch.setattr(
        PhotosPreflight,
        "run_preflight",
        lambda self: PreflightResult(passed=True, checks={"photos_responsive": True}, errors=[]),
    )
    monkeypatch.setattr(PhotosPreflight, "ensure_photos_responsive", lambda self: True)


def test_orchestrator_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    staging_dir = tmp_path / "staging"
    album = "Kristins iPhone"
    library = tmp_path / "Shared.photoslibrary"
    library.mkdir()

    orchestrator = ImportOrchestrator(db_path, staging_dir, library=library, album=album)

    assert isinstance(orchestrator.db, Database)
    assert isinstance(orchestrator.throttle, ThrottleController)
    assert isinstance(orchestrator.staging, StagingManager)
    assert isinstance(orchestrator.importer, PhotoImporter)
    assert orchestrator.db.db_path == db_path
    assert orchestrator.staging.staging_dir == staging_dir
    assert orchestrator.library == library
    assert orchestrator.album == album
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

    async def fail_import(self, job, scan_done_event=None) -> None:
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


@pytest.mark.asyncio
async def test_start_import_checkpoints_db_on_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    checkpoint_calls: list[str] = []

    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)
    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", _complete_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", _complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    monkeypatch.setattr(orchestrator.db, "checkpoint", lambda: checkpoint_calls.append("called"))

    await orchestrator.start_import(source_path)

    assert checkpoint_calls == ["called"]


class StubNetworkMonitor:
    instances: list["StubNetworkMonitor"] = []

    def __init__(self, path: Path, check_interval: float = 10.0) -> None:
        self.path = path
        self.check_interval = check_interval
        self.disconnect_callbacks: list = []
        self.reconnect_callbacks: list = []
        self.started = False
        self.stopped = False
        self.is_available = True
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


async def _complete_import(self, job, scan_done_event=None) -> None:
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
async def test_start_import_defaults_album_from_source_folder_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "Kristins iPhone"
    source_path.mkdir()
    seen: dict[str, str | None] = {"album": None}

    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)
    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", _complete_scan)

    async def capture_import(self, job, scan_done_event=None) -> None:
        seen["album"] = self.album
        self.db.update_job_state(job.job_id, JobState.VERIFYING)

    monkeypatch.setattr(ImportOrchestrator, "_import_phase", capture_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")

    await orchestrator.start_import(source_path)

    assert seen["album"] == source_path.name


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
    scanning_id = db.add_file(job_id, source_path / "a.jpg", 1, "hash-a", "image")
    staged_id = db.add_file(job_id, source_path / "b.jpg", 1, "hash-b", "image")
    pending_id = db.add_file(job_id, source_path / "c.jpg", 1, "hash-c", "image")
    db.update_file_status(scanning_id, FileStatus.SCANNING)
    db.update_file_status(staged_id, FileStatus.STAGED)
    db.update_file_status(pending_id, FileStatus.PENDING)

    active_job_path = tmp_path / "active_job.json"
    seen_pending: dict[str, list[str]] = {}

    async def fail_scan(self, job, source_path: Path) -> None:
        raise AssertionError("scan phase should be skipped for persisted jobs")

    async def complete_import(self, job, scan_done_event=None) -> None:
        pending_rows = self.db.get_pending_files(job.job_id, limit=10)
        seen_pending["statuses"] = [row["status"] for row in pending_rows]
        seen_pending["paths"] = [Path(row["path"]).name for row in pending_rows]
        assert scan_done_event is not None
        assert scan_done_event.is_set() is True
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

    async def complete_import(self, job, scan_done_event=None) -> None:
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
async def test_resume_existing_job_skips_rescan_when_file_rows_exist_but_total_counter_is_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "persisted.jpg"
    file_path.write_bytes(b"image-bytes")

    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job(source_path, {})
    db.update_job_state(job_id, JobState.ERROR)
    file_id = db.add_file(job_id, file_path, 1, "hash-persisted", "image")
    db._connection.execute("UPDATE jobs SET total_files = 0 WHERE id = ?", (job_id,))
    db._connection.commit()

    calls = {"import": 0}

    async def fail_scan(self, job, source_path: Path) -> None:
        raise AssertionError("scan phase should be skipped when persisted file rows exist")

    async def complete_import(self, job, scan_done_event=None) -> None:
        calls["import"] += 1
        pending_rows = self.db.get_pending_files(job.job_id, limit=10)
        assert [row["id"] for row in pending_rows] == [file_id]
        self.db.update_file_status(file_id, FileStatus.IMPORTED)
        self.db.update_job_state(job.job_id, JobState.VERIFYING)

    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", fail_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db", active_job_path=tmp_path / "active_job.json")

    await orchestrator.start_import(source_path, job_id=job_id)

    assert calls == {"import": 1}
    assert db.get_job(job_id)["state"] == JobState.COMPLETED.value
    assert db.get_job_stats(job_id)[FileStatus.IMPORTED.value] == 1


@pytest.mark.asyncio
async def test_scan_phase_drains_remaining_queue_items_before_cancel_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_paths = [source_path / name for name in ("a.jpg", "b.jpg")]
    for file_path in file_paths:
        file_path.write_bytes(b"image-bytes")

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    orchestrator._active_job = job
    timestamp = datetime.now()
    file_infos = [
        FileInfo(
            path=file_path,
            size=file_path.stat().st_size,
            hash=f"hash-{index}",
            created=timestamp,
            modified=timestamp,
            media_type=MediaType.PHOTO,
            format="JPG",
        )
        for index, file_path in enumerate(file_paths)
    ]

    class SentinelFirstQueue:
        def __init__(self) -> None:
            self._items: list[object] = []
            self._event = asyncio.Event()

        def put_nowait(self, item: object) -> None:
            if isinstance(item, FileInfo):
                self._items.append(item)
            else:
                self._items.insert(0, item)
            self._event.set()

        async def get(self) -> object:
            while not self._items:
                await self._event.wait()
                if not self._items:
                    self._event = asyncio.Event()
            item = self._items.pop(0)
            if not self._items:
                self._event = asyncio.Event()
            return item

        def get_nowait(self) -> object:
            if not self._items:
                raise asyncio.QueueEmpty
            item = self._items.pop(0)
            if not self._items:
                self._event = asyncio.Event()
            return item

        def empty(self) -> bool:
            return not self._items

    def fake_scan(self, progress_callback=None, pause_check=None, cancel_check=None):
        for file_info in file_infos:
            progress_callback(file_info)
        raise ScanCancelledError("scan cancelled after queueing files")

    checkpoint_counts: list[int] = []
    monkeypatch.setattr("icloudphotonator.orchestrator.asyncio.Queue", SentinelFirstQueue)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner.scan", fake_scan)
    monkeypatch.setattr(orchestrator.db, "checkpoint", lambda: checkpoint_counts.append(orchestrator.db.count_files(job.job_id)))

    await orchestrator._scan_phase(job, source_path)

    assert orchestrator.db.get_job_stats(job.job_id)["total"] == 2
    assert checkpoint_counts == [2]
    assert orchestrator._cancelled is True
    assert orchestrator.db.get_job(job.job_id)["state"] == JobState.CANCELLED.value


@pytest.mark.asyncio
async def test_import_phase_passes_library_and_album_to_importer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "a.jpg"
    retried_file_path = source_path / "b.jpg"
    file_path.write_bytes(b"image-bytes")
    retried_file_path.write_bytes(b"image-bytes")
    album = "Kristins iPhone"
    library = tmp_path / "Family.photoslibrary"
    library.mkdir()

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db", library=library, album=album)
    job = Job(orchestrator.db)
    job.start(source_path)
    orchestrator.db.add_file(job.job_id, file_path, 1, "hash-a", "image")
    error_file_id = orchestrator.db.add_file(job.job_id, retried_file_path, 1, "hash-b", "image")
    orchestrator.db.update_file_status(error_file_id, FileStatus.ERROR, error_message="failed")
    orchestrator.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    captured: dict[str, object] = {}
    emitted_logs: list[str] = []
    orchestrator.on_log(emitted_logs.append)

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
        album=None,
        report_dir=None,
        timeout=600,
        library=None,
    ):
        captured["file_paths"] = file_paths
        captured["album"] = album
        captured["library"] = library
        captured["use_exiftool"] = use_exiftool
        return SimpleNamespace(error_count=0)

    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)
    monkeypatch.setattr(
        orchestrator,
        "_apply_report",
        lambda *args, **kwargs: {str(file_path)},
    )

    await orchestrator._import_phase(job)

    # Error files should NOT be auto-reset; only the pending file is imported
    assert captured["file_paths"] == [file_path]
    assert captured["album"] == album
    assert captured["library"] == library
    assert captured["use_exiftool"] is False


@pytest.mark.asyncio
async def test_start_import_runs_scan_and_import_in_pipeline_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_paths = []
    for index in range(3):
        file_path = source_path / f"{index}.jpg"
        file_path.write_bytes(b"image-bytes")
        file_paths.append(file_path)

    import_started = threading.Event()
    scan_finished = threading.Event()

    def fake_scan(self, progress_callback=None, pause_check=None, cancel_check=None):
        manifests = []
        for path in file_paths[:2]:
            stat_result = path.stat()
            file_info = ImportOrchestrator(tmp_path / "unused.db")._row_to_file_info(
                {"path": str(path), "size": stat_result.st_size, "hash": "hash", "media_type": "image"}
            )
            manifests.append(file_info)
            progress_callback(file_info)
        assert import_started.wait(1), "import should begin before scan completes"
        for path in file_paths[2:]:
            stat_result = path.stat()
            file_info = ImportOrchestrator(tmp_path / "unused.db")._row_to_file_info(
                {"path": str(path), "size": stat_result.st_size, "hash": "hash", "media_type": "image"}
            )
            manifests.append(file_info)
            progress_callback(file_info)
        scan_finished.set()
        return SimpleNamespace(files=manifests, is_network_source=False)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    monkeypatch.setattr(orchestrator, "MIN_SCAN_BUFFER", 2)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner.scan", fake_scan)
    monkeypatch.setattr(orchestrator.throttle, "get_batch_size", lambda: 2)
    monkeypatch.setattr(orchestrator.throttle, "get_cooldown", lambda: 0)

    async def fake_stage_files(unique_files):
        return [(file_info, file_info.path) for file_info in unique_files], []

    def fake_import_batch(file_paths, **kwargs):
        import_started.set()
        return SimpleNamespace(report_path=None, errors=[], error_count=0, success=True)

    def fake_apply_report(job, row_by_path, staged_lookup, result):
        for row in row_by_path.values():
            orchestrator.db.update_file_status(row["id"], FileStatus.IMPORTED)
        return {row["path"] for row in row_by_path.values()}

    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)
    monkeypatch.setattr(orchestrator, "_apply_report", fake_apply_report)

    job_id = await orchestrator.start_import(source_path)

    assert import_started.is_set() is True
    assert scan_finished.is_set() is True
    assert orchestrator.db.get_job(job_id)["state"] == JobState.COMPLETED.value
    assert orchestrator.db.get_job_stats(job_id)[FileStatus.IMPORTED.value] == 3


@pytest.mark.asyncio
async def test_start_import_waits_for_small_scan_to_finish_before_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_paths = []
    for index in range(2):
        file_path = source_path / f"{index}.jpg"
        file_path.write_bytes(b"image-bytes")
        file_paths.append(file_path)

    scan_finished = threading.Event()
    saw_finished_scan: dict[str, bool] = {"value": False}
    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    monkeypatch.setattr(orchestrator, "MIN_SCAN_BUFFER", 5)
    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)
    monkeypatch.setattr(orchestrator.throttle, "get_batch_size", lambda: 10)
    monkeypatch.setattr(orchestrator.throttle, "get_cooldown", lambda: 0)

    def fake_scan(self, progress_callback=None, pause_check=None, cancel_check=None):
        manifests = []
        for path in file_paths:
            stat_result = path.stat()
            file_info = orchestrator._row_to_file_info(
                {"path": str(path), "size": stat_result.st_size, "hash": "hash", "media_type": "image"}
            )
            manifests.append(file_info)
            progress_callback(file_info)
        scan_finished.set()
        return SimpleNamespace(files=manifests, is_network_source=False)

    async def fake_stage_files(unique_files):
        return [(file_info, file_info.path) for file_info in unique_files], []

    def fake_import_batch(file_paths, **kwargs):
        saw_finished_scan["value"] = scan_finished.is_set()
        return SimpleNamespace(report_path=None, errors=[], error_count=0, success=True)

    def fake_apply_report(job, row_by_path, staged_lookup, result):
        for row in row_by_path.values():
            orchestrator.db.update_file_status(row["id"], FileStatus.IMPORTED)
        return {row["path"] for row in row_by_path.values()}

    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner.scan", fake_scan)
    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)
    monkeypatch.setattr(orchestrator, "_apply_report", fake_apply_report)

    job_id = await orchestrator.start_import(source_path)

    assert saw_finished_scan["value"] is True
    assert orchestrator.db.get_job(job_id)["state"] == JobState.COMPLETED.value


@pytest.mark.asyncio
async def test_import_phase_emits_batch_summary_from_db_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_paths = [source_path / name for name in ("a.jpg", "b.jpg", "c.jpg")]
    for file_path in file_paths:
        file_path.write_bytes(b"image-bytes")

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    for index, file_path in enumerate(file_paths):
        orchestrator.db.add_file(job.job_id, file_path, index + 1, f"hash-{index}", "image")
    orchestrator.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    emitted_logs: list[str] = []
    orchestrator.on_log(emitted_logs.append)

    monkeypatch.setattr(
        "icloudphotonator.orchestrator.DeduplicationEngine.check_duplicates",
        lambda self, file_infos: (file_infos, []),
    )

    async def fake_stage_files(unique_files):
        return [(file_info, file_info.path) for file_info in unique_files], []

    def fake_import_batch(file_paths, **kwargs):
        return SimpleNamespace(error_count=1, errors=[], success=False, report_path=tmp_path / "fake-report.csv")

    def fake_apply_report(job, staged_row_by_path, staged_lookup, result):
        rows = list(staged_row_by_path.values())
        orchestrator.db.update_file_status(rows[0]["id"], FileStatus.IMPORTED)
        orchestrator.db.update_file_status(rows[1]["id"], FileStatus.SKIPPED_DUPLICATE)
        orchestrator.db.update_file_status(rows[2]["id"], FileStatus.ERROR, "kaputt")
        return {row["path"] for row in rows}

    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)
    monkeypatch.setattr(orchestrator, "_apply_report", fake_apply_report)

    await orchestrator._import_phase(job)

    assert "✅ 1 importiert, ⏭️ 1 übersprungen, ❌ 1 Fehler" in emitted_logs


def test_apply_report_logs_result_errors_to_ui_and_db(tmp_path: Path) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "a.jpg"
    file_path.write_bytes(b"image-bytes")

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    file_id = orchestrator.db.add_file(job.job_id, file_path, 1, "hash-a", "image")

    emitted_logs: list[str] = []
    orchestrator.on_log(emitted_logs.append)

    result = SimpleNamespace(
        report_path=None,
        errors=[
            {"file": str(file_path), "error": "first error"},
            {"file": str(file_path), "error": "second error"},
            {"file": str(file_path), "error": "third error"},
            {"file": str(file_path), "error": "fourth error"},
        ],
    )

    processed_paths = orchestrator._apply_report(
        job,
        row_by_path={str(file_path): {"id": file_id, "path": str(file_path)}},
        staged_lookup={str(file_path): orchestrator._row_to_file_info({
            "path": str(file_path),
            "size": 1,
            "hash": "hash-a",
            "media_type": "image",
        })},
        result=result,
    )

    recent_logs = orchestrator.db.get_recent_logs(job.job_id, limit=10)

    assert processed_paths == {str(file_path)}
    assert emitted_logs == ["❌ first error", "❌ second error", "❌ third error"]
    assert any(log["action"] == "import_error" and log["details"] == "first error" for log in recent_logs)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Not authorized to send Apple events to Photos", True),
        ("AppleEvent failed with error -1743", True),
        ("boom", False),
    ],
)
def test_is_fatal_permission_error_detects_macos_automation_failures(message: str, expected: bool) -> None:
    assert ImportOrchestrator._is_fatal_permission_error(message) is expected


@pytest.mark.asyncio
async def test_import_phase_emits_permission_error_and_cancels_on_fatal_automation_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "a.jpg"
    file_path.write_bytes(b"image-bytes")

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    orchestrator._active_job = job
    file_id = orchestrator.db.add_file(job.job_id, file_path, 1, "hash-a", "image")
    orchestrator.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    permission_calls: list[str] = []
    emitted_logs: list[str] = []
    orchestrator.on_permission_error(lambda: permission_calls.append("called"))
    orchestrator.on_log(emitted_logs.append)

    monkeypatch.setattr(
        "icloudphotonator.orchestrator.DeduplicationEngine.check_duplicates",
        lambda self, file_infos: (file_infos, []),
    )

    async def fake_stage_files(unique_files):
        return [(file_info, file_info.path) for file_info in unique_files], []

    def fake_import_batch(file_paths, **kwargs):
        return SimpleNamespace(
            report_path=None,
            errors=[{"file": str(file_path), "error": "Not authorized to send Apple events (-1743)"}],
            error_count=1,
            success=False,
        )

    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)

    await orchestrator._import_phase(job)

    file_row = orchestrator.db._connection.execute(
        "SELECT status, error_message FROM files WHERE id = ?",
        (file_id,),
    ).fetchone()

    assert permission_calls == ["called"]
    assert orchestrator._cancelled is True
    assert orchestrator.db.get_job(job.job_id)["state"] == JobState.CANCELLED.value
    assert file_row["status"] == FileStatus.ERROR.value
    assert "-1743" in file_row["error_message"]
    assert any("Automation-Berechtigung" in message for message in emitted_logs)


@pytest.mark.asyncio
async def test_import_phase_resolves_staged_paths_and_always_cleans_up_staged_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "a.jpg"
    file_path.write_bytes(b"image-bytes")

    real_stage_dir = tmp_path / "real-stage"
    real_stage_dir.mkdir()
    aliased_stage_dir = tmp_path / "alias-stage"
    aliased_stage_dir.symlink_to(real_stage_dir, target_is_directory=True)
    real_staged_path = real_stage_dir / file_path.name
    real_staged_path.write_bytes(b"staged-bytes")
    aliased_staged_path = aliased_stage_dir / file_path.name

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    orchestrator.db.add_file(job.job_id, file_path, 1, "hash-a", "image")
    orchestrator.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    captured: dict[str, object] = {}
    cleanup_calls: list[list[Path]] = []

    monkeypatch.setattr(
        "icloudphotonator.orchestrator.DeduplicationEngine.check_duplicates",
        lambda self, file_infos: (file_infos, []),
    )

    async def fake_stage_files(unique_files):
        return [(unique_files[0], aliased_staged_path)], []

    def fake_import_batch(file_paths, **kwargs):
        captured["file_paths"] = file_paths
        return SimpleNamespace(error_count=0, success=True)

    def fake_apply_report(job_arg, row_by_path, staged_lookup, result):
        captured["staged_lookup_keys"] = list(staged_lookup.keys())
        return set()

    def fake_cleanup(paths):
        cleanup_calls.append(paths)

    monkeypatch.setattr(orchestrator.staging, "stage_files", fake_stage_files)
    monkeypatch.setattr(orchestrator.importer, "import_batch", fake_import_batch)
    monkeypatch.setattr(orchestrator, "_apply_report", fake_apply_report)
    monkeypatch.setattr(orchestrator.staging, "cleanup_staged", fake_cleanup)

    await orchestrator._import_phase(job)

    assert captured["file_paths"] == [real_staged_path]
    assert captured["staged_lookup_keys"] == [str(real_staged_path)]
    assert cleanup_calls == [[aliased_staged_path]]


def test_apply_report_resolves_report_filepaths_before_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    file_path = source_path / "a.jpg"
    file_path.write_bytes(b"image-bytes")

    real_stage_dir = tmp_path / "real-stage"
    real_stage_dir.mkdir()
    aliased_stage_dir = tmp_path / "alias-stage"
    aliased_stage_dir.symlink_to(real_stage_dir, target_is_directory=True)
    real_staged_path = real_stage_dir / file_path.name
    real_staged_path.write_bytes(b"staged-bytes")
    aliased_staged_path = aliased_stage_dir / file_path.name

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    file_id = orchestrator.db.add_file(job.job_id, file_path, 1, "hash-a", "image")
    file_info = orchestrator._row_to_file_info({"path": str(file_path), "size": 1, "hash": "hash-a", "media_type": "image"})

    monkeypatch.setattr(
        orchestrator,
        "_read_report_rows",
        lambda report_path: [{"filepath": str(aliased_staged_path), "imported": "true", "error": "false", "uuid": "uuid-1"}],
    )

    processed_paths = orchestrator._apply_report(
        job,
        row_by_path={str(file_path): {"id": file_id, "path": str(file_path)}},
        staged_lookup={str(real_staged_path): file_info},
        result=SimpleNamespace(report_path=tmp_path / "report.csv", errors=[], error_count=0, success=True),
    )

    row = orchestrator.db._connection.execute(
        "SELECT status FROM files WHERE id = ?",
        (file_id,),
    ).fetchone()
    recent_logs = orchestrator.db.get_recent_logs(job.job_id, limit=5)

    assert processed_paths == {str(file_path)}
    assert row["status"] == FileStatus.IMPORTED.value
    assert any(log["action"] == "imported" and log["details"] == str(real_staged_path) for log in recent_logs)


@pytest.mark.parametrize(
    ("success", "error_count", "expected_status", "expected_action"),
    [
        (True, 0, FileStatus.SKIPPED_DUPLICATE.value, "skipped_unmatched"),
        (False, 1, FileStatus.ERROR.value, "import_error"),
    ],
)
def test_apply_report_marks_unmatched_files_instead_of_leaving_them_importing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    success: bool,
    error_count: int,
    expected_status: str,
    expected_action: str,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()
    first_path = source_path / "a.jpg"
    second_path = source_path / "b.jpg"
    first_path.write_bytes(b"a")
    second_path.write_bytes(b"b")

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    job = Job(orchestrator.db)
    job.start(source_path)
    first_id = orchestrator.db.add_file(job.job_id, first_path, 1, "hash-a", "image")
    second_id = orchestrator.db.add_file(job.job_id, second_path, 1, "hash-b", "image")
    orchestrator.db.update_file_status(first_id, FileStatus.IMPORTING)
    orchestrator.db.update_file_status(second_id, FileStatus.IMPORTING)

    first_info = orchestrator._row_to_file_info({"path": str(first_path), "size": 1, "hash": "hash-a", "media_type": "image"})
    second_info = orchestrator._row_to_file_info({"path": str(second_path), "size": 1, "hash": "hash-b", "media_type": "image"})

    monkeypatch.setattr(
        orchestrator,
        "_read_report_rows",
        lambda report_path: [{"filepath": str(first_path), "imported": "true", "error": "false", "uuid": "uuid-1"}],
    )

    processed_paths = orchestrator._apply_report(
        job,
        row_by_path={
            str(first_path): {"id": first_id, "path": str(first_path)},
            str(second_path): {"id": second_id, "path": str(second_path)},
        },
        staged_lookup={
            str(first_path.resolve()): first_info,
            str(second_path.resolve()): second_info,
        },
        result=SimpleNamespace(report_path=tmp_path / "report.csv", errors=[], error_count=error_count, success=success),
    )

    second_row = orchestrator.db._connection.execute(
        "SELECT status, error_message FROM files WHERE id = ?",
        (second_id,),
    ).fetchone()
    recent_logs = orchestrator.db.get_recent_logs(job.job_id, limit=10)

    assert processed_paths == {str(first_path), str(second_path)}
    assert second_row["status"] == expected_status
    assert any(log["action"] == expected_action and log["file_id"] == second_id for log in recent_logs)


@pytest.mark.asyncio
async def test_start_import_emits_completion_summary_with_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "photos"
    source_path.mkdir()

    emitted_logs: list[str] = []

    monkeypatch.setattr("icloudphotonator.orchestrator.Scanner._is_network_path", lambda self, path: False)

    async def complete_scan(self, job, source_path: Path) -> None:
        self.db.add_file(job.job_id, source_path / "a.jpg", 1, "hash-a", "image")
        self.db.add_file(job.job_id, source_path / "b.jpg", 1, "hash-b", "image")
        self.db.add_file(job.job_id, source_path / "c.jpg", 1, "hash-c", "image")
        self.db.update_job_state(job.job_id, JobState.DEDUPLICATING)

    async def complete_import(self, job, scan_done_event=None) -> None:
        pending_rows = self.db.get_pending_files(job.job_id, limit=10)
        self.db.update_file_status(pending_rows[0]["id"], FileStatus.IMPORTED)
        self.db.update_file_status(pending_rows[1]["id"], FileStatus.SKIPPED_DUPLICATE)
        self.db.update_file_status(pending_rows[2]["id"], FileStatus.ERROR, "kaputt")
        self.db.update_job_state(job.job_id, JobState.VERIFYING)

    monkeypatch.setattr(ImportOrchestrator, "_scan_phase", complete_scan)
    monkeypatch.setattr(ImportOrchestrator, "_import_phase", complete_import)

    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")
    orchestrator.on_log(emitted_logs.append)

    await orchestrator.start_import(source_path)

    assert "Import abgeschlossen: 1 importiert, 1 übersprungen, 1 Fehler" in emitted_logs