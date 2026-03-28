"""Pre-flight checks for Apple Photos app readiness."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("icloudphotonator.preflight")

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


@dataclass
class PreflightResult:
    """Result of a preflight check."""
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class PhotosPreflight:
    """Pre-flight checks ensuring Apple Photos is ready for import."""

    def _run_osascript(self, script: str, timeout: int = OSASCRIPT_TIMEOUT) -> subprocess.CompletedProcess:
        """Run an AppleScript via osascript with timeout."""
        return subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def check_photos_running(self) -> bool:
        """Check if Photos.app is running."""
        try:
            result = self._run_osascript(
                'tell application "System Events" to (name of processes) contains "Photos"'
            )
            return result.returncode == 0 and "true" in result.stdout.lower()
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Photos-Running-Check fehlgeschlagen: %s", exc)
            return False

    def check_photos_responsive(self) -> bool:
        """Check if Photos.app responds to AppleScript commands."""
        try:
            result = self._run_osascript('tell application "Photos" to get name')
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Photos-Responsive-Check fehlgeschlagen: %s", exc)
            return False

    def check_automation_permission(self) -> bool:
        """Check if we have Automation permission for Photos."""
        try:
            result = self._run_osascript('tell application "Photos" to get name')
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Automation-Permission-Check fehlgeschlagen: %s", exc)
            return False

    def check_photos_not_locked(self) -> bool:
        """Check that Photos is not showing a modal dialog / locked state."""
        try:
            result = self._run_osascript(
                'tell application "Photos" to get id of every media item whose id is "___nonexistent___"'
            )
            # If Photos is locked/modal, this will timeout or error differently
            # A clean "no results" or returncode 0 means Photos is responsive
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Photos-Lock-Check fehlgeschlagen: %s", exc)
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
                result = self._run_osascript(script, timeout=30)
                return result.returncode == 0
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("Health-Image-Check fehlgeschlagen: %s", exc)
            return False

    def run_preflight(self) -> PreflightResult:
        """Run all preflight checks. Returns a PreflightResult."""
        checks: dict[str, bool] = {}
        errors: list[str] = []

        checks["photos_running"] = self.check_photos_running()
        if not checks["photos_running"]:
            errors.append("Photos.app läuft nicht.")

        checks["automation_permission"] = self.check_automation_permission()
        if not checks["automation_permission"]:
            errors.append("Automation-Berechtigung für Photos fehlt.")

        checks["photos_responsive"] = self.check_photos_responsive()
        if not checks["photos_responsive"]:
            errors.append("Photos.app reagiert nicht.")

        checks["photos_not_locked"] = self.check_photos_not_locked()
        if not checks["photos_not_locked"]:
            errors.append("Photos.app scheint blockiert zu sein (modaler Dialog?).")

        passed = all(checks.values())
        result = PreflightResult(passed=passed, checks=checks, errors=errors)

        if passed:
            logger.info("Preflight bestanden: %s", checks)
        else:
            logger.warning("Preflight fehlgeschlagen: %s — %s", checks, errors)

        return result

    def ensure_photos_responsive(self) -> bool:
        """Quick check for use before each batch. Fast path — no full preflight."""
        return self.check_photos_responsive()

