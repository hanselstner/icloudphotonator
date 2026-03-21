from __future__ import annotations

import asyncio
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from .db import Database
from .dedup import DeduplicationEngine
from .importer import PhotoImporter
from .job import Job
from .scanner import FileInfo, MediaType, Scanner
from .staging import StagingManager
from .state import FileStatus, JobState, transition
from .throttle import ThrottleController


REMAINING_FILE_STATUSES = {
    FileStatus.PENDING.value,
    FileStatus.SCANNING.value,
    FileStatus.STAGED.value,
    FileStatus.IMPORTING.value,
    FileStatus.RETRYING.value,
}


class ImportOrchestrator:
    """Orchestrates the full import workflow."""

    def __init__(self, db_path: Path, staging_dir: Path | None = None):
        self.db = Database(db_path)
        self.throttle = ThrottleController()
        self.staging = StagingManager(staging_dir)
        self.importer = PhotoImporter()
        self._paused = asyncio.Event()
        self._paused.set()
        self._cancelled = False
        self._progress_callbacks: list[Callable] = []
        self._log_callbacks: list[Callable[[str], None]] = []
        self._active_job: Job | None = None
        self.logger = logging.getLogger("icloudphotonator.orchestrator")

    async def start_import(self, source_path: Path, job_id: str | None = None):
        """Main entry point. Runs the full import workflow."""
        source_path = Path(source_path)
        self._cancelled = False
        self._paused.set()
        job = Job(self.db, job_id) if job_id else Job(self.db)
        self._active_job = job

        try:
            is_new_job = job.source_path is None or job.stats["total"] == 0
            if is_new_job:
                if job.state == JobState.IDLE:
                    job.start(source_path)
                    self._emit_log(f"Scanne Quelle: {source_path}")
                await self._scan_phase(job, source_path)
            elif job.state == JobState.PAUSED:
                job.resume()
                self._emit_log("Import wird fortgesetzt.")

            if not self._cancelled and job.state != JobState.CANCELLED:
                await self._import_phase(job)

            if not self._cancelled and job.state not in {JobState.CANCELLED, JobState.COMPLETED}:
                if job.state == JobState.DEDUPLICATING:
                    self._transition_job(job, JobState.IMPORTING, "import_ready")
                if job.state == JobState.STAGING:
                    self._transition_job(job, JobState.IMPORTING, "import_ready")
                if job.state == JobState.IMPORTING:
                    self._transition_job(job, JobState.VERIFYING, "verify")
                if job.state == JobState.VERIFYING:
                    job.complete()
                    self._emit_log("Import abgeschlossen.")

            self._sync_job_counts(job)
            self._notify_progress(self.get_job_stats(job.job_id))
            return job.job_id
        except Exception as exc:
            self.logger.exception("Import failed for job %s", job.job_id)
            try:
                job.fail(str(exc))
            except Exception:
                self.db.update_job_state(job.job_id, JobState.ERROR)
                self.db.log_action(job.job_id, None, "error", str(exc))
            raise

    def pause(self):
        """Pause the import."""
        self._paused.clear()
        if self._active_job and self._active_job.state in {
            JobState.SCANNING,
            JobState.DEDUPLICATING,
            JobState.STAGING,
            JobState.IMPORTING,
            JobState.VERIFYING,
        }:
            self._active_job.pause()
            self._emit_log("Import pausiert.")

    def resume(self):
        """Resume the import."""
        self._paused.set()
        if self._active_job and self._active_job.state == JobState.PAUSED:
            self._active_job.resume()
            self._emit_log("Import fortgesetzt.")

    def cancel(self):
        """Cancel the import."""
        self._cancelled = True
        self._paused.set()
        if self._active_job and self._active_job.state not in {JobState.CANCELLED, JobState.COMPLETED}:
            self._active_job.cancel()
            self._emit_log("Import gestoppt.")

    def stop(self):
        """Compatibility alias for UI bridge stop handling."""
        self.cancel()

    def on_progress(self, callback: Callable):
        """Register a progress callback. Called with (job_stats_dict)."""
        self._progress_callbacks.append(callback)

    def on_log(self, callback: Callable[[str], None]) -> None:
        """Register a log callback."""
        self._log_callbacks.append(callback)

    def _notify_progress(self, stats: dict):
        for callback in list(self._progress_callbacks):
            try:
                callback(stats)
            except Exception:
                self.logger.exception("Progress callback failed")

    def _emit_log(self, message: str) -> None:
        self.logger.info(message)
        for callback in list(self._log_callbacks):
            try:
                callback(message)
            except Exception:
                self.logger.exception("Log callback failed")

    async def _wait_if_paused(self):
        """Block if paused."""
        await self._paused.wait()

    async def _scan_phase(self, job: Job, source_path: Path):
        """Scan source and populate DB."""
        discovered = {"count": 0}

        def _on_file(file_info: FileInfo) -> None:
            discovered["count"] += 1
            self._notify_progress(
                {
                    "job_id": job.job_id,
                    "state": JobState.SCANNING.value,
                    "discovered": discovered["count"],
                    "total": discovered["count"],
                    "duplicates": 0,
                    "skipped": 0,
                    "errors": 0,
                    "remaining": 0,
                    "scanned_files": discovered["count"],
                    "current_file": str(file_info.path),
                }
            )

        manifest = await asyncio.to_thread(Scanner(source_path).scan, _on_file)
        for file_info in manifest.files:
            self.db.add_file(
                job.job_id,
                file_info.path,
                file_info.size,
                file_info.hash or "",
                file_info.media_type.value,
            )
        self.db.log_action(
            job.job_id,
            None,
            "scan_complete",
            f"files={len(manifest.files)}; network_source={manifest.is_network_source}",
        )
        self._emit_log(f"Scan abgeschlossen: {len(manifest.files)} Dateien gefunden.")
        self._transition_job(job, JobState.DEDUPLICATING, "dedup_ready")
        self._notify_progress(self.get_job_stats(job.job_id))

    async def _import_phase(self, job: Job):
        """Run the import loop."""
        dedup = DeduplicationEngine(self.db, job.job_id)
        self._deduplicate_pending_files(job, dedup)

        while not self._cancelled:
            await self._wait_if_paused()
            pending_rows = self.db.get_pending_files(job.job_id, limit=self.throttle.get_batch_size())
            if not pending_rows:
                break

            file_infos = [self._row_to_file_info(row) for row in pending_rows]
            unique_files, duplicate_files = dedup.check_duplicates(file_infos)
            if duplicate_files:
                self._mark_duplicates(job, duplicate_files)

            if not unique_files:
                self._sync_job_counts(job)
                continue

            if job.state == JobState.DEDUPLICATING:
                next_state = (
                    JobState.STAGING
                    if any(self.staging._requires_staging(file_info.path) for file_info in unique_files)
                    else JobState.IMPORTING
                )
                self._transition_job(job, next_state, "staging" if next_state == JobState.STAGING else "importing")
                phase_label = "Staging vorbereitet." if next_state == JobState.STAGING else "Import gestartet."
                self._emit_log(phase_label)

            staged_pairs = await asyncio.to_thread(self.staging.stage_files, unique_files)
            if job.state == JobState.STAGING:
                self._transition_job(job, JobState.IMPORTING, "importing")
                self._emit_log("Staging abgeschlossen. Import startet.")

            row_by_path = {row["path"]: row for row in pending_rows}
            staged_lookup = {str(staged_path): file_info for file_info, staged_path in staged_pairs}
            staged_paths = [staged_path for _, staged_path in staged_pairs]
            for file_info in unique_files:
                self.db.update_file_status(row_by_path[str(file_info.path)]["id"], FileStatus.IMPORTING)

            result = await asyncio.to_thread(
                self.importer.import_batch,
                staged_paths,
                True,
                True,
                True,
                None,
                600,
            )

            cleanup_paths: list[Path] = []
            processed_paths = self._apply_report(job, row_by_path, staged_lookup, result)

            for file_info, staged_path in staged_pairs:
                if str(file_info.path) in processed_paths and staged_path != file_info.path:
                    cleanup_paths.append(staged_path)

            if cleanup_paths:
                await asyncio.to_thread(self.staging.cleanup_staged, cleanup_paths)

            if result.error_count > 0:
                self.throttle.report_failure(len(unique_files))
            else:
                self.throttle.report_success(len(unique_files))

            self._sync_job_counts(job)
            self._notify_progress(self.get_job_stats(job.job_id))
            if self._cancelled:
                break

            await self._wait_if_paused()
            if self.db.get_pending_files(job.job_id, limit=1):
                await asyncio.sleep(self.throttle.get_cooldown())

    def get_job_stats(self, job_id: str) -> dict:
        """Get current stats for a job."""
        job = self.db.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id!r} does not exist.")

        file_stats = self.db.get_job_stats(job_id)
        duplicate_count = file_stats[FileStatus.SKIPPED_DUPLICATE.value]
        skipped_total = file_stats[FileStatus.SKIPPED_ERROR.value]
        remaining = sum(file_stats[status] for status in REMAINING_FILE_STATUSES)
        return {
            "job_id": job_id,
            "state": job["state"],
            "source_path": job["source_path"],
            "discovered": file_stats["total"],
            "total": file_stats["total"],
            "pending": file_stats[FileStatus.PENDING.value],
            "imported": file_stats[FileStatus.IMPORTED.value],
            "duplicates": duplicate_count,
            "skipped": skipped_total,
            "errors": file_stats[FileStatus.ERROR.value],
            "remaining": remaining,
            "current_batch_size": self.throttle.current_batch_size,
            "total_processed": self.throttle.total_processed,
            "paused": not self._paused.is_set(),
            "cancelled": self._cancelled,
        }

    def _transition_job(self, job: Job, target: JobState, action: str, details: str | None = None) -> None:
        current = job.state
        if current == target:
            return
        next_state = transition(current, target)
        self.db.update_job_state(job.job_id, next_state)
        self.db.log_action(job.job_id, None, action, details or target.value)

    def _deduplicate_pending_files(self, job: Job, dedup: DeduplicationEngine) -> None:
        pending_rows = self._get_pending_rows(job.job_id)
        unique_files, duplicate_files = dedup.check_duplicates([self._row_to_file_info(row) for row in pending_rows])
        if not duplicate_files:
            return

        unique_paths = {str(file_info.path) for file_info in unique_files}
        for row in pending_rows:
            if row["path"] not in unique_paths:
                self.db.update_file_status(row["id"], FileStatus.SKIPPED_DUPLICATE)
                self.db.log_action(job.job_id, row["id"], "duplicate", row["path"])

    def _mark_duplicates(self, job: Job, duplicate_files: list[FileInfo]) -> None:
        duplicate_paths = {str(file_info.path) for file_info in duplicate_files}
        for row in self._get_pending_rows(job.job_id):
            if row["path"] in duplicate_paths:
                self.db.update_file_status(row["id"], FileStatus.SKIPPED_DUPLICATE)
                self.db.log_action(job.job_id, row["id"], "duplicate", row["path"])

    def _apply_report(
        self,
        job: Job,
        row_by_path: dict[str, dict],
        staged_lookup: dict[str, FileInfo],
        result,
    ) -> set[str]:
        processed_paths: set[str] = set()
        rows = self._read_report_rows(result.report_path) if result.report_path else []

        for report_row in rows:
            staged_file = report_row.get("filepath")
            if not staged_file or staged_file not in staged_lookup:
                continue

            original_info = staged_lookup[staged_file]
            file_row = row_by_path[str(original_info.path)]
            processed_paths.add(str(original_info.path))

            if self._report_bool(report_row.get("imported")):
                self.db.update_file_status(file_row["id"], FileStatus.IMPORTED)
                self.db.log_action(job.job_id, file_row["id"], "imported", staged_file)
                staged_lookup[staged_file] = original_info
                DeduplicationEngine(self.db, job.job_id).mark_as_imported(original_info, report_row.get("uuid") or None)
            elif self._report_bool(report_row.get("error")):
                message = next(
                    (item["error"] for item in result.errors if item.get("file") == staged_file),
                    "osxphotos reported an error",
                )
                self.db.update_file_status(file_row["id"], FileStatus.ERROR, message)
                self.db.log_action(job.job_id, file_row["id"], "import_error", message)
            else:
                self.db.update_file_status(file_row["id"], FileStatus.SKIPPED_DUPLICATE)
                self.db.log_action(job.job_id, file_row["id"], "skipped_duplicate", staged_file)

        if rows:
            return processed_paths

        generic_error = result.errors[0]["error"] if result.errors else "Import failed without a generated report"
        for file_row in row_by_path.values():
            self.db.update_file_status(file_row["id"], FileStatus.ERROR, generic_error)
            processed_paths.add(file_row["path"])
        return processed_paths

    def _row_to_file_info(self, row: dict) -> FileInfo:
        path = Path(row["path"])
        try:
            stat_result = path.stat()
            created = datetime.fromtimestamp(stat_result.st_ctime)
            modified = datetime.fromtimestamp(stat_result.st_mtime)
        except OSError:
            created = datetime.now()
            modified = datetime.now()

        media_type = MediaType(row["media_type"]) if row.get("media_type") in MediaType._value2member_map_ else MediaType.UNKNOWN
        return FileInfo(
            path=path,
            size=row["size"],
            hash=row.get("hash") or None,
            created=created,
            modified=modified,
            media_type=media_type,
            format=path.suffix.lstrip(".").upper(),
        )

    def _sync_job_counts(self, job: Job) -> None:
        stats = self.db.get_job_stats(job.job_id)
        self.db.update_job_counts(
            job.job_id,
            stats[FileStatus.IMPORTED.value],
            stats[FileStatus.SKIPPED_DUPLICATE.value] + stats[FileStatus.SKIPPED_ERROR.value],
            stats[FileStatus.ERROR.value],
        )

    def _get_pending_rows(self, job_id: str) -> list[dict]:
        rows = self.db._connection.execute(
            """
            SELECT *
            FROM files
            WHERE job_id = ? AND status = ?
            ORDER BY id ASC
            """,
            (job_id, FileStatus.PENDING.value),
        ).fetchall()
        return [dict(row) for row in rows]

    def _read_report_rows(self, report_path: Path) -> list[dict[str, str]]:
        with Path(report_path).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _report_bool(value: object) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes"}