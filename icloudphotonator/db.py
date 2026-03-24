from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .state import FileStatus, JobState


class Database:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection:
            yield self._connection

    def checkpoint(self) -> None:
        """Force WAL checkpoint to persist data to main DB file."""
        self._connection.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def create_job(self, source_path: str | Path, config: dict[str, Any] | None) -> str:
        job_id = str(uuid4())
        now = self._now()
        payload = json.dumps(config or {})
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, source_path, state, created_at, updated_at, total_files,
                    imported_count, skipped_count, error_count,
                    last_processed_file, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(source_path),
                    JobState.IDLE.value,
                    now,
                    now,
                    0,
                    0,
                    0,
                    0,
                    None,
                    payload,
                ),
            )
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_incomplete_jobs(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT id, source_path, state, created_at, updated_at
            FROM jobs
            WHERE state NOT IN (?, ?)
            ORDER BY updated_at DESC, created_at DESC
            """,
            (JobState.COMPLETED.value, JobState.CANCELLED.value),
        ).fetchall()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            job = dict(row)
            job["stats"] = self.get_job_stats(job["id"])
            jobs.append(job)
        return jobs

    def get_latest_job(self) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            SELECT *
            FROM jobs
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def update_job_state(self, job_id: str, state: JobState | str) -> None:
        state_value = state.value if isinstance(state, JobState) else state
        with self.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET state = ?, updated_at = ? WHERE id = ?",
                (state_value, self._now(), job_id),
            )

    def update_job_counts(
        self, job_id: str, imported: int, skipped: int, errors: int
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET imported_count = ?, skipped_count = ?, error_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (imported, skipped, errors, self._now(), job_id),
            )

    def update_job_source_path(self, job_id: str, source_path: str | Path) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET source_path = ?, updated_at = ? WHERE id = ?",
                (str(source_path), self._now(), job_id),
            )

    def update_job_config(self, job_id: str, config: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET config_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(config), self._now(), job_id),
            )

    def add_file(
        self,
        job_id: str,
        path: str | Path,
        size: int,
        hash: str,
        media_type: str,
    ) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO files (
                    job_id, path, size, hash, media_type, status,
                    error_message, retry_count, imported_at, live_pair_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(path),
                    size,
                    hash,
                    media_type,
                    FileStatus.PENDING.value,
                    None,
                    0,
                    None,
                    None,
                ),
            )
            connection.execute(
                """
                UPDATE jobs
                SET total_files = total_files + 1, updated_at = ?
                WHERE id = ?
                """,
                (self._now(), job_id),
            )
        return int(cursor.lastrowid)

    def update_file_status(
        self,
        file_id: int,
        status: FileStatus | str,
        error_message: str | None = None,
    ) -> None:
        status_value = status.value if isinstance(status, FileStatus) else status
        imported_at = self._now() if status_value == FileStatus.IMPORTED.value else None
        if status_value == FileStatus.RETRYING.value:
            query = """
                UPDATE files
                SET status = ?, error_message = ?, imported_at = ?, retry_count = retry_count + 1
                WHERE id = ?
            """
        else:
            query = """
                UPDATE files
                SET status = ?, error_message = ?, imported_at = ?
                WHERE id = ?
            """
        with self.transaction() as connection:
            connection.execute(query, (status_value, error_message, imported_at, file_id))

    def get_pending_files(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT * FROM files
            WHERE job_id = ? AND status = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (job_id, FileStatus.PENDING.value, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_files(self, job_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS count FROM files WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return int(row["count"] if row else 0)

    def get_job_stats(self, job_id: str) -> dict[str, int]:
        stats = {status.value: 0 for status in FileStatus}
        stats["total"] = 0
        rows = self._connection.execute(
            "SELECT status, COUNT(*) AS count FROM files WHERE job_id = ? GROUP BY status",
            (job_id,),
        ).fetchall()
        for row in rows:
            stats[row["status"]] = row["count"]
            stats["total"] += row["count"]
        return stats

    def reset_error_files(self, job_id: str) -> int:
        """Reset all error files to pending status for retry."""
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE files
                SET status = ?, error_message = NULL, retry_count = 0, imported_at = NULL
                WHERE job_id = ? AND status = ?
                """,
                (FileStatus.PENDING.value, job_id, FileStatus.ERROR.value),
            )
        return int(cursor.rowcount or 0)

    def log_action(
        self, job_id: str, file_id: int | None, action: str, details: str | None
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO import_log (job_id, file_id, timestamp, action, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, file_id, self._now(), action, details),
            )

    def get_recent_logs(self, job_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT * FROM import_log
            WHERE job_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        """Checkpoint WAL and close connection."""
        try:
            self.checkpoint()
        except Exception:
            pass
        self._connection.close()

    def _create_tables(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    source_path TEXT,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    imported_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    last_processed_file TEXT,
                    config_json TEXT
                );

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    hash TEXT,
                    media_type TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    imported_at TEXT,
                    live_pair_id INTEGER,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS import_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    file_id INTEGER,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_files_job_id ON files(job_id);
                CREATE INDEX IF NOT EXISTS idx_files_job_id_status ON files(job_id, status);
                CREATE INDEX IF NOT EXISTS idx_import_log_job_id ON import_log(job_id);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()