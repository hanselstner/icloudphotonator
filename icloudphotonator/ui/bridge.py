from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger("icloudphotonator.bridge")


class BackendBridge:
    """Bridge the Tk UI on the main thread to a background orchestrator."""

    def __init__(self, db_path: Path | None = None, staging_dir: Path | None = None):
        self._db_path = db_path or (Path.home() / ".icloudphotonator" / "icloudphotonator.db")
        self._staging_dir = staging_dir
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._orchestrator: object | None = None
        self._on_progress: Callable[..., None] | None = None
        self._on_log: Callable[[str], None] | None = None
        self._on_complete: Callable[[], None] | None = None
        self._on_error: Callable[[str], None] | None = None

    def set_callbacks(self, on_progress=None, on_log=None, on_complete=None, on_error=None):
        self._on_progress = on_progress
        self._on_log = on_log
        self._on_complete = on_complete
        self._on_error = on_error

    def start_import(self, source_path: Path) -> None:
        """Start an import in a dedicated background thread."""
        if self._thread and self._thread.is_alive():
            self._emit_log("Ein Import läuft bereits.")
            return
        self._thread = threading.Thread(target=self._run_import, args=(source_path,), daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._dispatch_to_orchestrator("pause")

    def resume(self) -> None:
        self._dispatch_to_orchestrator("resume")

    def stop(self) -> None:
        self._dispatch_to_orchestrator("stop")

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

    def _run_import(self, source_path: Path) -> None:
        """Import worker executed on a background thread."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            from icloudphotonator.orchestrator import ImportOrchestrator

            orchestrator = ImportOrchestrator(self._db_path, self._staging_dir)
            self._orchestrator = orchestrator
            self._register_callback(orchestrator, "on_progress", self._on_progress)
            self._register_callback(orchestrator, "on_log", self._on_log)

            start_import = getattr(orchestrator, "start_import", None)
            if not callable(start_import):
                raise AttributeError("ImportOrchestrator.start_import() ist nicht verfügbar.")

            self._emit_log(f"Starte Import für: {source_path}")
            result = start_import(source_path)
            if asyncio.iscoroutine(result):
                self._loop.run_until_complete(result)
            if self._on_complete:
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
