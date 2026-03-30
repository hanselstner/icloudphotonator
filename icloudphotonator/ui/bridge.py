from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Callable

from icloudphotonator.db import Database
from icloudphotonator.persistence import (
    DEFAULT_ACTIVE_JOB_PATH,
    DEFAULT_DB_PATH,
    clear_active_job,
    load_active_job,
)

logger = logging.getLogger("icloudphotonator.bridge")


class BackendBridge:
    """Bridge the Tk UI on the main thread to a background orchestrator."""

    def __init__(
        self,
        db_path: Path | None = None,
        staging_dir: Path | None = None,
        active_job_path: Path | None = None,
    ):
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._staging_dir = staging_dir
        self._active_job_path = Path(active_job_path) if active_job_path else DEFAULT_ACTIVE_JOB_PATH
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._orchestrator: object | None = None
        self._on_progress: Callable[..., None] | None = None
        self._on_log: Callable[[str], None] | None = None
        self._on_complete: Callable[[], None] | None = None
        self._on_error: Callable[[str], None] | None = None
        self._on_permission_error: Callable[[], None] | None = None

    def set_callbacks(self, on_progress=None, on_log=None, on_complete=None, on_error=None, on_permission_error=None):
        self._on_progress = on_progress
        self._on_log = on_log
        self._on_complete = on_complete
        self._on_error = on_error
        self._on_permission_error = on_permission_error

    def start_import(self, source_path: Path, library: Path | None = None, album: str | None = None) -> None:
        """Start an import in a dedicated background thread."""
        if self._thread and self._thread.is_alive():
            self._emit_log("Ein Import läuft bereits.")
            return
        self._thread = threading.Thread(
            target=self._run_import,
            args=(source_path, None, library, album),
            daemon=True,
        )
        self._thread.start()

    def resume_import(self, job_id: str) -> None:
        """Resume an existing import in a dedicated background thread."""
        if self._thread and self._thread.is_alive():
            self._emit_log("Ein Import läuft bereits.")
            return

        db = Database(self._db_path)
        job = db.get_job(job_id)
        if not job or not job.get("source_path"):
            clear_active_job(self._active_job_path)
            self._emit_error("Der gespeicherte Import konnte nicht gefunden werden.")
            return

        self._thread = threading.Thread(
            target=self._run_import,
            args=(Path(job["source_path"]), job_id),
            daemon=True,
        )
        self._thread.start()

    def get_incomplete_jobs(self) -> list[dict]:
        """Return incomplete jobs, preferring the last active job if present."""
        jobs = Database(self._db_path).get_incomplete_jobs()
        active_job = load_active_job(self._active_job_path)
        if not active_job:
            return jobs

        active_job_id = active_job.get("job_id")
        active_db_path = active_job.get("db_path")
        if active_db_path and Path(active_db_path).resolve(strict=False) != self._db_path.resolve(strict=False):
            clear_active_job(self._active_job_path)
            return jobs

        if not any(job["id"] == active_job_id for job in jobs):
            clear_active_job(self._active_job_path)
            return jobs

        return sorted(jobs, key=lambda job: job["id"] != active_job_id)

    def retry_errors(self, job_id: str) -> None:
        """Reset error files to pending and restart the import."""
        if self._thread and self._thread.is_alive():
            self._emit_log("Ein Import läuft bereits.")
            return

        db = Database(self._db_path)
        job = db.get_job(job_id)
        if not job or not job.get("source_path"):
            self._emit_error("Der gespeicherte Import konnte nicht gefunden werden.")
            return

        error_count = db.get_job_stats(job_id).get("error", 0)
        self._emit_log(f"Setze {error_count} fehlerhafte Dateien zurück...")
        db.reset_error_files(job_id)

        self._thread = threading.Thread(
            target=self._run_import,
            args=(Path(job["source_path"]), job_id),
            daemon=True,
        )
        self._thread.start()

    def pause(self) -> None:
        self._dispatch_to_orchestrator("pause")

    def resume(self) -> None:
        self._dispatch_to_orchestrator("resume")

    def stop(self) -> None:
        self._dispatch_to_orchestrator("stop")

    def restart_photos(self) -> None:
        """Restart Photos.app and resume import."""
        orchestrator = self._orchestrator
        if orchestrator is None:
            return
        restart = getattr(orchestrator, "restart_photos", None)
        resume = getattr(orchestrator, "resume", None)
        if not callable(restart) or not callable(resume):
            return

        async def _restart_and_resume() -> None:
            try:
                await restart()
                resume()
            except Exception as exc:
                logger.exception("restart_photos failed")
                self._emit_error(str(exc))

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(_restart_and_resume())
            )
            return

    def _dispatch_to_orchestrator(self, method_name: str) -> None:
        orchestrator = self._orchestrator
        method = getattr(orchestrator, method_name, None) if orchestrator else None
        if not callable(method):
            return

        def _invoke() -> None:
            try:
                result = method()
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as exc:
                logger.exception("Backend action %s failed", method_name)
                self._emit_error(str(exc))

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(_invoke)
            return
        _invoke()

    def _register_callback(self, target: object, registrar_name: str, callback: Callable | None) -> None:
        if callback is None:
            return
        registrar = getattr(target, registrar_name, None)
        if callable(registrar):
            registrar(callback)

    def _run_import(
        self,
        source_path: Path,
        job_id: str | None = None,
        library: Path | None = None,
        album: str | None = None,
    ) -> None:
        """Import worker executed on a background thread."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            from icloudphotonator.orchestrator import ImportOrchestrator

            orchestrator = ImportOrchestrator(
                self._db_path,
                self._staging_dir,
                active_job_path=self._active_job_path,
                library=library,
                album=album,
            )
            self._orchestrator = orchestrator
            self._register_callback(orchestrator, "on_progress", self._on_progress)
            self._register_callback(orchestrator, "on_log", self._on_log)
            self._register_callback(orchestrator, "on_permission_error", self._emit_permission_error)

            start_import = getattr(orchestrator, "start_import", None)
            if not callable(start_import):
                raise AttributeError("ImportOrchestrator.start_import() ist nicht verfügbar.")

            self._emit_log(f"Starte Import für: {source_path}")
            result = start_import(source_path, job_id=job_id)
            if asyncio.iscoroutine(result):
                result = self._loop.run_until_complete(result)

            stats = None
            if isinstance(result, str):
                get_job_stats = getattr(orchestrator, "get_job_stats", None)
                if callable(get_job_stats):
                    stats = get_job_stats(result)

            should_emit_complete = not (isinstance(stats, dict) and (stats.get("cancelled") or stats.get("state") == "cancelled"))
            if self._on_complete and should_emit_complete:
                self._on_complete()
        except Exception as exc:
            logger.exception("Import failed")
            self._emit_error(str(exc))
        finally:
            if self._loop is not None:
                try:
                    self._loop.close()
                finally:
                    self._loop = None
            self._orchestrator = None

    def _emit_log(self, message: str) -> None:
        if self._on_log:
            self._on_log(message)

    def _emit_error(self, message: str) -> None:
        if self._on_error:
            self._on_error(message)

    def _emit_permission_error(self) -> None:
        if self._on_permission_error:
            self._on_permission_error()
