from pathlib import Path

from icloudphotonator.db import Database
from icloudphotonator.persistence import clear_active_job, load_active_job, save_active_job
from icloudphotonator.state import JobState
from icloudphotonator.ui.bridge import BackendBridge


def test_active_job_persistence_round_trip(tmp_path: Path) -> None:
    active_job_path = tmp_path / "active_job.json"
    db_path = tmp_path / "jobs.db"
    source_path = tmp_path / "photos"

    save_active_job("job-123", source_path, db_path, active_job_path)

    payload = load_active_job(active_job_path)

    assert payload == {
        "job_id": "job-123",
        "source_path": str(source_path.resolve(strict=False)),
        "db_path": str(db_path.resolve(strict=False)),
    }

    clear_active_job(active_job_path)

    assert load_active_job(active_job_path) is None


def test_bridge_prioritizes_last_active_incomplete_job(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    active_job_path = tmp_path / "active_job.json"
    db = Database(db_path)

    first_job_id = db.create_job("/photos/one", {})
    second_job_id = db.create_job("/photos/two", {})
    db.update_job_state(first_job_id, JobState.IMPORTING)
    db.update_job_state(second_job_id, JobState.SCANNING)
    save_active_job(first_job_id, "/photos/one", db_path, active_job_path)

    bridge = BackendBridge(db_path=db_path, active_job_path=active_job_path)

    jobs = bridge.get_incomplete_jobs()

    assert [job["id"] for job in jobs] == [first_job_id, second_job_id]


def test_bridge_start_import_passes_library_to_worker_thread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_path = tmp_path / "photos"
    library = tmp_path / "Family.photoslibrary"
    captured: dict[str, object] = {}

    class FakeThread:
        def __init__(self, target, args, daemon) -> None:
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon

        def start(self) -> None:
            captured["started"] = True

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr("icloudphotonator.ui.bridge.threading.Thread", FakeThread)

    bridge = BackendBridge(db_path=tmp_path / "jobs.db")
    bridge.start_import(source_path, library=library)

    assert captured["target"] == bridge._run_import
    assert captured["args"] == (source_path, None, library)
    assert captured["daemon"] is True
    assert captured["started"] is True