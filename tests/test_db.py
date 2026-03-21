import json
from pathlib import Path

from icloudphotonator.db import Database
from icloudphotonator.state import FileStatus


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