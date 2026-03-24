import json
import sqlite3
from pathlib import Path

import pytest

from icloudphotonator.db import Database
from icloudphotonator.state import FileStatus, JobState


def test_create_and_get_job(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")

    job_id = db.create_job("/photos", {"mode": "import"})
    job = db.get_job(job_id)

    assert job is not None
    assert job["id"] == job_id
    assert job["source_path"] == "/photos"
    assert job["state"] == "idle"
    assert json.loads(job["config_json"]) == {"mode": "import"}


def test_add_and_update_files(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job("/photos", {})

    file_id = db.add_file(job_id, "/photos/a.jpg", 123, "hash-a", "image")
    db.update_file_status(file_id, FileStatus.IMPORTED)

    job = db.get_job(job_id)
    assert job is not None
    assert job["total_files"] == 1

    imported = db.get_job_stats(job_id)
    assert imported[FileStatus.IMPORTED.value] == 1


def test_get_pending_files_returns_only_pending(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job("/photos", {})

    pending_id = db.add_file(job_id, "/photos/a.jpg", 123, "hash-a", "image")
    imported_id = db.add_file(job_id, "/photos/b.jpg", 456, "hash-b", "image")
    db.update_file_status(imported_id, FileStatus.IMPORTED)
    db.update_file_status(pending_id, FileStatus.PENDING)

    pending_files = db.get_pending_files(job_id)

    assert [item["id"] for item in pending_files] == [pending_id]
    assert all(item["status"] == FileStatus.PENDING.value for item in pending_files)


def test_count_files_counts_all_rows_for_job(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job("/photos", {})

    db.add_file(job_id, "/photos/a.jpg", 123, "hash-a", "image")
    db.add_file(job_id, "/photos/b.jpg", 456, "hash-b", "image")

    assert db.count_files(job_id) == 2


def test_job_stats_counts_statuses(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job("/photos", {})

    imported_id = db.add_file(job_id, "/photos/a.jpg", 123, "hash-a", "image")
    skipped_id = db.add_file(job_id, "/photos/b.jpg", 456, "hash-b", "image")
    error_id = db.add_file(job_id, "/photos/c.jpg", 789, "hash-c", "image")
    db.update_file_status(imported_id, FileStatus.IMPORTED)
    db.update_file_status(skipped_id, FileStatus.SKIPPED_DUPLICATE)
    db.update_file_status(error_id, FileStatus.ERROR, error_message="bad file")

    stats = db.get_job_stats(job_id)

    assert stats["total"] == 3
    assert stats[FileStatus.IMPORTED.value] == 1
    assert stats[FileStatus.SKIPPED_DUPLICATE.value] == 1
    assert stats[FileStatus.ERROR.value] == 1


def test_get_incomplete_jobs_excludes_terminal_states(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")

    active_job_id = db.create_job("/photos/active", {})
    completed_job_id = db.create_job("/photos/completed", {})
    cancelled_job_id = db.create_job("/photos/cancelled", {})
    db.update_job_state(active_job_id, JobState.IMPORTING)
    db.update_job_state(completed_job_id, JobState.COMPLETED)
    db.update_job_state(cancelled_job_id, JobState.CANCELLED)
    db.add_file(active_job_id, "/photos/active/a.jpg", 123, "hash-a", "image")
    db.update_file_status(db.add_file(active_job_id, "/photos/active/b.jpg", 456, "hash-b", "image"), FileStatus.IMPORTED)

    jobs = db.get_incomplete_jobs()

    assert [job["id"] for job in jobs] == [active_job_id]
    assert jobs[0]["state"] == JobState.IMPORTING.value
    assert jobs[0]["stats"]["total"] == 2
    assert jobs[0]["stats"][FileStatus.IMPORTED.value] == 1


def test_get_latest_job_returns_most_recent_job(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")

    first_job_id = db.create_job("/photos/one", {})
    second_job_id = db.create_job("/photos/two", {})
    db.update_job_state(second_job_id, JobState.IMPORTING)

    latest_job = db.get_latest_job()

    assert latest_job is not None
    assert latest_job["id"] == second_job_id
    assert latest_job["source_path"] == "/photos/two"
    assert latest_job["state"] == JobState.IMPORTING.value
    assert latest_job["id"] != first_job_id


def test_reset_error_files_requeues_only_error_rows(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job("/photos", {})

    error_id = db.add_file(job_id, "/photos/a.jpg", 123, "hash-a", "image")
    pending_id = db.add_file(job_id, "/photos/b.jpg", 456, "hash-b", "image")
    db.update_file_status(error_id, FileStatus.ERROR, error_message="bad file")
    db.update_file_status(pending_id, FileStatus.PENDING)
    db._connection.execute(
        "UPDATE files SET retry_count = 2 WHERE id = ?",
        (error_id,),
    )
    db._connection.commit()

    reset_count = db.reset_error_files(job_id)
    rows = db._connection.execute(
        "SELECT status, error_message, retry_count FROM files WHERE id IN (?, ?) ORDER BY id ASC",
        (error_id, pending_id),
    ).fetchall()

    assert reset_count == 1
    assert dict(rows[0]) == {
        "status": FileStatus.PENDING.value,
        "error_message": None,
        "retry_count": 0,
    }
    assert dict(rows[1]) == {
        "status": FileStatus.PENDING.value,
        "error_message": None,
        "retry_count": 0,
    }


def test_checkpoint_and_close_methods(tmp_path: Path) -> None:
    db = Database(tmp_path / "jobs.db")
    job_id = db.create_job("/photos", {})

    db.add_file(job_id, "/photos/a.jpg", 123, "hash-a", "image")
    db.checkpoint()
    db.close()

    with pytest.raises(sqlite3.ProgrammingError):
        db.get_job(job_id)