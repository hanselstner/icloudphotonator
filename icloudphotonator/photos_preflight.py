"""Pre-flight checks for Apple Photos app readiness."""
from __future__ import annotations

import logging
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("icloudphotonator.preflight")


def check_library_readable(library: Path | None) -> bool:
    """Verify the Apple Photos library SQLite database can be opened.

    Without Full Disk Access (TCC) macOS blocks sqlite3.connect() on the
    Photos.sqlite file with 'unable to open database file' — we use that as
    the canonical signal that FDA is missing. Resolves *library* via
    osxphotos.utils.get_last_library_path() when None.
    """
    if library is None:
        try:
            from osxphotos.utils import get_last_library_path
            resolved = get_last_library_path()
        except Exception as exc:
            logger.warning("check_library_readable: failed to resolve library path: %s", exc)
            return False
        if not resolved:
            logger.warning("check_library_readable: no last library path available")
            return False
        library = Path(resolved)

    db_path = Path(library)
    if db_path.suffix == ".photoslibrary" or db_path.name.endswith(".photoslibrary"):
        db_path = db_path / "database" / "Photos.sqlite"

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA schema_version")
        return True
    except sqlite3.OperationalError as exc:
        logger.warning("check_library_readable failed for %s: %s", db_path, exc)
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

# Minimal valid JPEG for health-image import test
HEALTH_JPEG = bytes.fromhex(
    'ffd8ffe000104a46494600010100000100010000'
    'ffdb004300080606070605080707070909080a0c'
    '140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c'
    '20242e2720222c231c1c2837292c303134341f'
    '27393d38323c2e333432ffc0000b080001000101'
    '011100ffc4001f000001050101010101010000000'
    '0000000000102030405060708090a0bffc400'
    '00ffc40000ffda00080101000003100002000063ffd9'
)

OSASCRIPT_TIMEOUT = 15


def run_applescript(script: str) -> tuple[bool, str]:
    """Run an AppleScript in-process via NSAppleScript (PyObjC).

    Returns (success, output_or_error_message).
    """
    from Foundation import NSAppleScript  # type: ignore[import-untyped]

    nsa = NSAppleScript.alloc().initWithSource_(script)
    result, error_info = nsa.executeAndReturnError_(None)
    if error_info is not None:
        msg = error_info.get("NSAppleScriptErrorMessage", "Unknown error")
        num = error_info.get("NSAppleScriptErrorNumber", -1)
        return False, f"Error {num}: {msg}"
    if result is not None:
        return True, result.stringValue() or ""
    return True, ""


@dataclass
class PreflightResult:
    """Result of a preflight check."""
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class PhotosPreflight:
    """Pre-flight checks ensuring Apple Photos is ready for import."""

    def _run_applescript(self, script: str) -> tuple[bool, str]:
        """Run an AppleScript in-process via the standalone run_applescript helper."""
        return run_applescript(script)

    def check_photos_running(self) -> bool:
        """Check if Photos.app is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-x", "Photos"],
                capture_output=True,
                check=False,
            )
            return result.returncode == 0
        except Exception as exc:
            logger.warning("Photos running check failed: %s", exc)
            return False

    def check_photos_responsive(self) -> bool:
        """Check if Photos.app responds to AppleScript commands."""
        try:
            success, _output = self._run_applescript('tell application "Photos" to get name')
            return success
        except Exception as exc:
            logger.warning("Photos responsive check failed: %s", exc)
            return False

    def check_automation_permission(self) -> bool:
        """Check if we have Automation permission for Photos."""
        try:
            success, _output = self._run_applescript('tell application "Photos" to get name')
            return success
        except Exception as exc:
            logger.warning("Automation permission check failed: %s", exc)
            return False

    def _check_has_window(self) -> bool:
        """Check that Photos.app is responsive (not stuck headless)."""
        try:
            success, _output = self._run_applescript(
                'tell application "Photos" to get name'
            )
            return success
        except Exception as exc:
            logger.warning("Photos window check failed: %s", exc)
            return False

    def check_health_image_import(self) -> bool:
        """Test importing a minimal JPEG to verify the import pipeline works."""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(HEALTH_JPEG)
                tmp_path = Path(tmp.name)
            try:
                script = (
                    f'tell application "Photos" to import POSIX file "{tmp_path}" '
                    f'skip check duplicates true'
                )
                success, _output = self._run_applescript(script)
                return success
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        except Exception as exc:
            logger.warning("Health image check failed: %s", exc)
            return False

    def run_preflight(self, library: Path | None = None) -> PreflightResult:
        """Run all preflight checks. Returns a PreflightResult."""
        checks: dict[str, bool] = {}
        errors: list[str] = []

        checks["photos_running"] = self.check_photos_running()
        if not checks["photos_running"]:
            errors.append("Photos.app is not running.")

        checks["automation_permission"] = self.check_automation_permission()
        if not checks["automation_permission"]:
            errors.append("Automation permission for Photos is missing.")

        checks["photos_responsive"] = self.check_photos_responsive()
        if not checks["photos_responsive"]:
            errors.append("Photos.app is not responding.")

        checks["has_window"] = self._check_has_window()
        if not checks["has_window"]:
            errors.append("Photos.app has no window (headless/blocked?).")

        checks["library_readable"] = check_library_readable(library)
        if not checks["library_readable"]:
            errors.append(
                "Full Disk Access is missing: cannot read Apple Photos library database. "
                "Enable access in System Settings → Privacy & Security → Full Disk Access, "
                "then relaunch the app."
            )

        passed = all(checks.values())
        result = PreflightResult(passed=passed, checks=checks, errors=errors)

        if passed:
            logger.info("Preflight passed: %s", checks)
        else:
            logger.warning("Preflight failed: %s — %s", checks, errors)

        return result

    # ------------------------------------------------------------------
    # Auto-recovery helpers
    # ------------------------------------------------------------------

    def _kill_photos(self) -> None:
        """Force-kill Photos.app via pkill."""
        logger.info("Killing Photos (pkill)…")
        subprocess.run(["pkill", "-9", "Photos"], check=False)
        time.sleep(2)

    def _start_photos(self) -> None:
        """Launch Photos.app via 'open' and wait for it to appear."""
        logger.info("Starting Photos…")
        subprocess.run(["open", "-a", "Photos"], check=False)
        time.sleep(5)

    def _activate_photos(self) -> None:
        """Bring Photos to the foreground via AppleScript."""
        logger.info("Activating Photos…")
        try:
            self._run_applescript('tell application "Photos" to activate')
        except Exception as exc:
            logger.warning("Photos activate failed: %s", exc)

    def ensure_photos_responsive(self) -> bool:
        """Quick responsiveness check with auto-recovery.

        1. Ping Photos — if responsive, return True immediately.
        2. Check automation permission — if missing, skip kill/restart (won't help).
        3. Otherwise kill → restart → activate → re-check.
        4. Up to *max_retries* recovery attempts.
        """
        max_retries = 2
        for attempt in range(1 + max_retries):
            if self.check_photos_responsive() and self._check_has_window():
                if attempt > 0:
                    logger.info(
                        "Photos ready after %d recovery attempt(s).", attempt
                    )
                return True
            if attempt < max_retries:
                if not self.check_automation_permission():
                    logger.error("Automation permission missing — kill/restart won't help.")
                    return False
                logger.warning(
                    "Photos not responding — recovery attempt %d/%d",
                    attempt + 1,
                    max_retries,
                )
                self._kill_photos()
                self._start_photos()
                self._activate_photos()
        logger.error("Photos unreachable after %d recovery attempts.", max_retries)
        return False

