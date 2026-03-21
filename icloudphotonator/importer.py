from __future__ import annotations

import csv
import json
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ImportResult:
    success: bool
    imported_count: int
    skipped_count: int
    error_count: int
    errors: list[dict]
    report_path: Path | None


class PhotoImporter:
    """Wraps osxphotos import CLI for importing photos into Apple Photos."""

    def __init__(self, osxphotos_path: str = "osxphotos"):
        self.osxphotos_path = osxphotos_path
        self._command_prefix = self._resolve_command_prefix(osxphotos_path)
        self._verify_osxphotos()

    def _verify_osxphotos(self):
        """Check that osxphotos is available."""
        result = self._run_command([*self._command_prefix, "--version"], timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"osxphotos is not available: {(result.stderr or result.stdout).strip()}")

    def import_batch(
        self,
        file_paths: list[Path],
        skip_dups: bool = True,
        auto_live: bool = True,
        use_exiftool: bool = True,
        report_dir: Path | None = None,
        timeout: int = 600,
    ) -> ImportResult:
        """Import a batch of files using osxphotos import CLI."""
        if not file_paths:
            return ImportResult(True, 0, 0, 0, [], None)

        target_report_dir = Path(report_dir) if report_dir else Path(tempfile.mkdtemp(prefix="icloudphotonator-report-"))
        target_report_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_report_dir / f"import-report-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.csv"

        cmd = self._build_command(file_paths, skip_dups, auto_live, use_exiftool, report_path)
        completed = self._run_command(cmd, timeout)
        parsed = self._parse_report(report_path) if report_path.exists() else ImportResult(
            success=completed.returncode == 0,
            imported_count=0,
            skipped_count=0,
            error_count=0,
            errors=[],
            report_path=None,
        )

        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "osxphotos import failed").strip()
            parsed.success = False
            if parsed.error_count == 0:
                parsed.error_count = len(file_paths)
            if not parsed.errors:
                parsed.errors.append({"file": "", "error": stderr})
        else:
            parsed.success = parsed.error_count == 0

        if parsed.report_path is None and report_path.exists():
            parsed.report_path = report_path
        return parsed

    def _build_command(self, file_paths, skip_dups, auto_live, use_exiftool, report_path) -> list[str]:
        """Build the osxphotos import command."""
        cmd = [*self._command_prefix, "import", *[str(path) for path in file_paths]]
        if skip_dups:
            cmd.append("--skip-dups")
        if auto_live:
            cmd.append("--auto-live")
        if use_exiftool:
            cmd.append("--exiftool")
        cmd.extend(["--verbose", "--report", str(report_path)])
        return cmd

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
                errors.append(
                    {
                        "file": row.get("filepath") or row.get("file") or "",
                        "error": row.get("error_message") or "osxphotos reported an error",
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

    def _run_command(self, cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
        """Run command with timeout and error handling."""
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Unable to execute osxphotos command: {cmd[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"osxphotos import timed out after {timeout} seconds") from exc

    def _resolve_command_prefix(self, osxphotos_path: str) -> list[str]:
        if " " in osxphotos_path.strip():
            return shlex.split(osxphotos_path)
        if resolved := shutil.which(osxphotos_path):
            return [resolved]
        if osxphotos_path == "osxphotos" and shutil.which("uv"):
            return ["uv", "run", "osxphotos"]
        raise RuntimeError("osxphotos executable was not found in PATH and uv fallback is unavailable.")

    def _load_report_rows(self, report_path: Path) -> list[dict]:
        if report_path.suffix.lower() == ".json":
            return json.loads(report_path.read_text())
        with report_path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _as_bool(value: object) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes"}