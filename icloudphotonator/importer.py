from __future__ import annotations

import csv
import json
import logging
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path

from .i18n import t


logger = logging.getLogger("icloudphotonator")


class _SubprocessImportError(RuntimeError):
    """Raised when the osxphotos subprocess exits with a non-zero status.

    Carries the captured combined stdout/stderr so callers can classify
    the failure (Full Disk Access missing, click.Abort, etc.).
    """

    def __init__(self, message: str, returncode: int, output: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.output = output


PICTURES_LIBRARY_DIR = Path.home() / "Pictures"
SHARED_LIBRARY_DIR = Path("/Users/Shared")


def find_photo_libraries() -> list[Path]:
    """Find all Apple Photos libraries in common local locations."""
    libraries: list[Path] = []
    for directory in (PICTURES_LIBRARY_DIR, SHARED_LIBRARY_DIR):
        if directory.exists():
            libraries.extend(directory.glob("*.photoslibrary"))
    return sorted({path for path in libraries})


@dataclass
class ImportResult:
    success: bool
    imported_count: int
    skipped_count: int
    error_count: int
    errors: list[dict]
    report_path: Path | None


class PhotoImporter:
    """Wraps osxphotos' Python import API for importing photos into Apple Photos."""

    def __init__(self, osxphotos_path: str = "osxphotos"):
        # Retained for backwards-compatible constructor usage.
        self.osxphotos_path = osxphotos_path
        self._verify_osxphotos()

    def _verify_osxphotos(self) -> None:
        """Check that osxphotos' import API is available."""
        self._get_import_cli()

    def import_batch(
        self,
        file_paths: list[Path],
        skip_dups: bool = True,
        auto_live: bool = True,
        use_exiftool: bool = True,
        album: str | None = None,
        report_dir: Path | None = None,
        timeout: int = 600,
        library: Path | None = None,
    ) -> ImportResult:
        """Import a batch of files using osxphotos' in-process import API."""
        if not file_paths:
            return ImportResult(True, 0, 0, 0, [], None)

        logger.info(
            "import_batch called: %d files, skip_dups=%s, auto_live=%s, exiftool=%s, album=%r, library=%s, timeout=%ds",
            len(file_paths), skip_dups, auto_live, use_exiftool, album, library, timeout,
        )
        logger.debug("Files: %s", [str(p) for p in file_paths[:5]] + (["..."] if len(file_paths) > 5 else []))
        logger.debug(
            "Runtime: python=%s, frozen=%s, MEIPASS=%s, cwd=%s, HOME=%s",
            sys.executable, getattr(sys, "frozen", False),
            getattr(sys, "_MEIPASS", "not bundled"), os.getcwd(), Path.home(),
        )

        target_report_dir = Path(report_dir) if report_dir else Path(tempfile.mkdtemp(prefix="icloudphotonator-report-"))
        target_report_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_report_dir / f"import-report-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.csv"

        try:
            self._run_import(file_paths, skip_dups, auto_live, use_exiftool, album, report_path, timeout, library)
        except _SubprocessImportError as exc:
            logger.error("osxphotos subprocess failed: rc=%s", exc.returncode)
            error_msg, fda_match = self._classify_subprocess_failure(exc.output, library)
            if not error_msg:
                error_msg = str(exc)
            logger.error("Resolved error message for report: %s", error_msg)
            return self._result_from_report(
                report_path=report_path,
                fallback_success=False,
                fallback_error=error_msg,
                file_count=len(file_paths),
                full_disk_access_missing=fda_match,
            )
        except TimeoutError as exc:
            logger.error("osxphotos subprocess timed out: %s", exc)
            return self._result_from_report(
                report_path=report_path,
                fallback_success=False,
                fallback_error=str(exc),
                file_count=len(file_paths),
            )
        except Exception as exc:
            import traceback
            logger.error("Import failed with exception: %s: %s", type(exc).__name__, exc)
            logger.error("Full traceback:\n%s", traceback.format_exc())
            error_msg = str(exc).strip() or f"{type(exc).__module__}.{type(exc).__name__}"
            return self._result_from_report(
                report_path=report_path,
                fallback_success=False,
                fallback_error=error_msg,
                file_count=len(file_paths),
            )

        return self._result_from_report(
            report_path=report_path,
            fallback_success=True,
            file_count=len(file_paths),
        )

    def _run_import(
        self,
        file_paths: list[Path],
        skip_dups: bool,
        auto_live: bool,
        use_exiftool: bool,
        album: str | None,
        report_path: Path,
        timeout: int,
        library: Path | None = None,
    ) -> None:
        # Run osxphotos as a subprocess so we can hard-kill it on timeout.
        # The previous in-process ThreadPoolExecutor + Future.result(timeout)
        # pattern could not interrupt a hung osxphotos call: the worker thread
        # kept running and the surrounding `with` block waited on
        # shutdown(wait=True), delaying the TimeoutError by minutes.
        osxphotos_data_dir = self._ensure_osxphotos_data_dir()

        env = os.environ.copy()
        # Point osxphotos' SQLiteKVStore at our verified-writable data dir.
        env["XDG_DATA_HOME"] = str(osxphotos_data_dir.parent)

        cmd = self._build_command(
            file_paths=file_paths,
            skip_dups=skip_dups,
            auto_live=auto_live,
            use_exiftool=use_exiftool,
            album=album,
            report_path=report_path,
            library=library,
        )
        logger.info(
            "Starting osxphotos subprocess (timeout=%ds, cwd=%s): %s",
            timeout,
            osxphotos_data_dir,
            " ".join(shlex.quote(arg) for arg in cmd),
        )

        returncode, output = self._run_subprocess(
            cmd,
            timeout=timeout,
            cwd=str(osxphotos_data_dir),
            env=env,
        )

        if returncode != 0:
            snippet = (output or "").strip()
            snippet = snippet[-1000:] if snippet else "(no output captured)"
            raise _SubprocessImportError(
                f"osxphotos subprocess exited with code {returncode}: {snippet}",
                returncode=returncode,
                output=output or "",
            )
        logger.info("osxphotos subprocess completed successfully (rc=0)")

    def _build_command(
        self,
        file_paths: list[Path],
        skip_dups: bool,
        auto_live: bool,
        use_exiftool: bool,
        album: str | None,
        report_path: Path,
        library: Path | None,
    ) -> list[str]:
        # Invoke osxphotos via `python -m osxphotos import ...` in dev mode.
        # Using sys.executable ensures we run in the same interpreter (and
        # venv) as the parent process. In a frozen PyInstaller bundle
        # sys.executable points at the bundle bootloader, which does not
        # honour `-m`; instead we re-invoke ourselves with the
        # `--run-osxphotos` argv marker (see icloudphotonator/__main__.py).
        if getattr(sys, "frozen", False):
            cmd: list[str] = [sys.executable, "--run-osxphotos", "import"]
        else:
            cmd = [sys.executable, "-m", "osxphotos", "import"]
        cmd.extend(str(path) for path in file_paths)
        cmd.extend(["--report", str(report_path), "--no-progress"])
        if skip_dups:
            cmd.append("--skip-dups")
        if auto_live:
            cmd.append("--auto-live")
        if use_exiftool:
            cmd.append("--exiftool")
        if album:
            cmd.extend(["--album", album])
        if library is not None:
            cmd.extend(["--library", str(library)])
        return cmd

    def _run_subprocess(
        self,
        cmd: list[str],
        timeout: int,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        """Run osxphotos as a subprocess with hard-kill on timeout.

        On timeout: terminate(), wait up to 5s, then kill() and wait again.
        Always raises TimeoutError after the kill sequence so the caller
        sees a fast, deterministic timeout — not a 14-minute hang.

        Returns (returncode, combined_stdout_stderr).
        """
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=env,
        )
        # Exposed for tests / debugging — last spawned process.
        self._last_process = process
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning(
                "osxphotos subprocess hit %ds timeout — sending SIGTERM (pid=%s)",
                timeout, process.pid,
            )
            process.terminate()
            stdout = ""
            try:
                stdout, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "osxphotos subprocess did not exit after SIGTERM — sending SIGKILL (pid=%s)",
                    process.pid,
                )
                process.kill()
                try:
                    stdout, _ = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.error(
                        "osxphotos subprocess did not exit even after SIGKILL (pid=%s)",
                        process.pid,
                    )
                    stdout = ""
            if stdout:
                logger.info("osxphotos partial output before kill:\n%s", stdout)
            raise TimeoutError(f"osxphotos import timed out after {timeout}s")

        if stdout:
            logger.info("osxphotos subprocess output:\n%s", stdout)
        return process.returncode, stdout or ""

    def _classify_subprocess_failure(
        self,
        output: str,
        library: Path | None,
    ) -> tuple[str, bool]:
        """Map subprocess output to a user-facing error message + FDA flag."""
        text = output or ""
        lower = text.lower()
        # Full Disk Access missing: sqlite3 cannot open the .photoslibrary db.
        library_str = str(library).lower() if library is not None else ""
        if "unable to open database file" in lower and (
            ".photoslibrary" in lower or ".photoslibrary" in library_str
        ):
            return t("error.full_disk_access_missing"), True
        # Click prints "Aborted!" when the CLI raises click.Abort. Historically
        # this was triggered by a missing exiftool binary in our environment.
        stripped = text.strip()
        if not stripped or stripped.lower().endswith("aborted!"):
            return "osxphotos aborted — exiftool may be missing (https://exiftool.org/)", False
        # Otherwise surface the tail of the captured output.
        snippet = stripped[-500:]
        return snippet, False

    def _ensure_osxphotos_data_dir(self) -> Path:
        """Locate (and verify writable) the osxphotos SQLiteKVStore dir.

        osxphotos uses xdg_data_home() / "osxphotos" for its internal
        SQLiteKVStore. If this directory doesn't exist or can't be created,
        every import fails with "unable to open database file".
        """
        try:
            from xdg_base_dirs import xdg_data_home
            osxphotos_data_dir = xdg_data_home() / "osxphotos"
        except ImportError:
            osxphotos_data_dir = Path.home() / ".local" / "share" / "osxphotos"

        try:
            osxphotos_data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "osxphotos data dir: %s (exists=%s, writable=%s)",
                osxphotos_data_dir,
                osxphotos_data_dir.exists(),
                os.access(str(osxphotos_data_dir), os.W_OK),
            )
        except OSError as e:
            logger.error("Cannot create osxphotos data dir %s: %s", osxphotos_data_dir, e)
            osxphotos_data_dir = Path.home() / ".icloudphotonator" / "osxphotos_data"
            osxphotos_data_dir.mkdir(parents=True, exist_ok=True)
            logger.warning("Using fallback data dir: %s", osxphotos_data_dir)

        # Verify sqlite3 can actually create a database in this directory.
        test_db_path = osxphotos_data_dir / "_test_write.db"
        try:
            conn = sqlite3.connect(str(test_db_path))
            conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
            conn.close()
            test_db_path.unlink(missing_ok=True)
            logger.info("SQLite write test passed in %s", osxphotos_data_dir)
        except Exception as e:
            logger.error("SQLite write test FAILED in %s: %s", osxphotos_data_dir, e)
            fallback_dir = Path.home() / ".icloudphotonator" / "osxphotos_data"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            try:
                test_db2 = fallback_dir / "_test_write.db"
                conn = sqlite3.connect(str(test_db2))
                conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
                conn.close()
                test_db2.unlink(missing_ok=True)
                logger.info("Fallback SQLite write test passed in %s", fallback_dir)
                osxphotos_data_dir = fallback_dir
            except Exception as e2:
                logger.error("Fallback SQLite write test ALSO FAILED: %s", e2)
        return osxphotos_data_dir

    def _get_import_cli(self):
        try:
            module = import_module("osxphotos.cli.import_cli")
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"osxphotos import API is unavailable: {exc}") from exc

        try:
            return module.import_cli
        except AttributeError as exc:
            raise RuntimeError("osxphotos import API is unavailable: missing import_cli()") from exc

    def _result_from_report(
        self,
        report_path: Path,
        fallback_success: bool,
        fallback_error: str | None = None,
        file_count: int = 0,
        full_disk_access_missing: bool = False,
    ) -> ImportResult:
        # STRICT SUCCESS SEMANTICS: never report success when the report file
        # is missing or empty while files were submitted. The previous
        # behaviour (default success=True if no report) silently masked
        # Photos.app hangs and produced false-positive "imported" counts.
        report_exists = report_path.exists()
        report_has_data = report_exists and report_path.stat().st_size > 0

        if fallback_success and file_count > 0 and not report_has_data:
            silent_msg = t("error.silent_failure_no_report")
            logger.error(
                "osxphotos subprocess exited 0 but report is %s (path=%s) — treating as silent failure",
                "missing" if not report_exists else "empty",
                report_path,
            )
            return ImportResult(
                success=False,
                imported_count=0,
                skipped_count=0,
                error_count=file_count,
                errors=[{"file": "", "error": silent_msg}],
                report_path=report_path if report_exists else None,
            )

        parsed = self._parse_report(report_path) if report_has_data else ImportResult(
            success=fallback_success,
            imported_count=0,
            skipped_count=0,
            error_count=0,
            errors=[],
            report_path=None,
        )

        parsed.success = fallback_success and parsed.error_count == 0
        if not fallback_success:
            parsed.success = False
            if parsed.error_count == 0:
                parsed.error_count = file_count
            if fallback_error and not parsed.errors:
                entry: dict = {"file": "", "error": fallback_error}
                if full_disk_access_missing:
                    entry["full_disk_access_missing"] = True
                parsed.errors.append(entry)

        if parsed.report_path is None and report_exists:
            parsed.report_path = report_path
        return parsed

    def _parse_report(self, report_path: Path) -> ImportResult:
        """Parse osxphotos CSV report to extract results."""
        rows = self._load_report_rows(report_path)
        imported_count = 0
        error_count = 0
        errors: list[dict] = []

        for row in rows:
            imported = self._as_bool(row.get("imported"))
            error = self._as_bool(row.get("error"))
            imported_count += int(imported)
            error_count += int(error)
            if error:
                error_text = row.get("error_message") or ""
                if not error_text:
                    # The 'error' column itself may contain descriptive text
                    # rather than just a boolean flag.
                    raw_error = str(row.get("error") or "").strip()
                    if raw_error.lower() not in {"1", "true", "yes", ""}:
                        error_text = raw_error
                if not error_text:
                    filepath = row.get("filepath") or row.get("file") or ""
                    error_text = f"Photos.app error for {Path(filepath).name}" if filepath else "osxphotos reported an error"
                errors.append(
                    {
                        "file": row.get("filepath") or row.get("file") or "",
                        "error": error_text,
                    }
                )

        skipped_count = max(0, len(rows) - imported_count - error_count)
        return ImportResult(
            success=error_count == 0,
            imported_count=imported_count,
            skipped_count=skipped_count,
            error_count=error_count,
            errors=errors,
            report_path=report_path,
        )

    def _load_report_rows(self, report_path: Path) -> list[dict]:
        if report_path.suffix.lower() == ".json":
            return json.loads(report_path.read_text())
        with report_path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _as_bool(value: object) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes"}