from __future__ import annotations

from .db import Database
from .scanner import FileInfo
from .state import FileStatus


class DeduplicationEngine:
    """Checks for duplicates using file hash and osxphotos fingerprint."""

    def __init__(self, db: Database, job_id: str):
        self.db = db
        self.job_id = job_id
        self._imported_hashes = self._load_imported_hashes()

    def check_duplicates(self, files: list[FileInfo]) -> tuple[list[FileInfo], list[FileInfo]]:
        """Returns (unique_files, duplicate_files).

        Checks against:
        1. Already-imported files in this job (by hash)
        2. Files already in the current batch (by hash)
        """
        unique_files: list[FileInfo] = []
        duplicate_files: list[FileInfo] = []
        batch_hashes: set[str] = set()

        for file_info in files:
            if not file_info.hash:
                unique_files.append(file_info)
                continue

            if file_info.hash in self._imported_hashes or file_info.hash in batch_hashes:
                duplicate_files.append(file_info)
                continue

            batch_hashes.add(file_info.hash)
            unique_files.append(file_info)

        return unique_files, duplicate_files

    def mark_as_imported(self, file_info: FileInfo, photos_uuid: str | None = None) -> None:
        """Record that this file has been imported."""
        if file_info.hash:
            self._imported_hashes.add(file_info.hash)
        self.db.log_action(
            self.job_id,
            None,
            "dedup_mark_imported",
            f"path={file_info.path}; photos_uuid={photos_uuid or ''}",
        )

    def _load_imported_hashes(self) -> set[str]:
        rows = self.db._connection.execute(
            """
            SELECT DISTINCT hash
            FROM files
            WHERE job_id = ? AND status = ? AND hash IS NOT NULL
            """,
            (self.job_id, FileStatus.IMPORTED.value),
        ).fetchall()
        return {row["hash"] for row in rows}