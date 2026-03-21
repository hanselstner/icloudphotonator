import json
from pathlib import Path

from icloudphotonator.db import Database
from icloudphotonator.job import Job
from icloudphotonator.state import JobState


def test_job_lifecycle(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job = Job(db)

    job.start(tmp_path / "photos")
    assert job.state == JobState.SCANNING

    job.pause()
    assert job.state == JobState.PAUSED

    job.resume()
    assert job.state == JobState.SCANNING

    db.update_job_state(job.job_id, JobState.VERIFYING)
    job.complete()
    assert job.state == JobState.COMPLETED


def test_resume_restores_previous_state(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job = Job(db)

    job.start(tmp_path / "photos")
    job.pause()

    persisted = db.get_job(job.job_id)
    assert persisted is not None
    assert json.loads(persisted["config_json"])["previous_state"] == JobState.SCANNING.value

    job.resume()
    assert job.state == JobState.SCANNING


def test_persistence_across_job_instances(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    source_path = tmp_path / "photos"
    first_job = Job(db)
    first_job.start(source_path)
    first_job.pause()

    second_job = Job(db, first_job.job_id)

    assert second_job.job_id == first_job.job_id
    assert second_job.state == JobState.PAUSED
    assert second_job.source_path == source_path