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