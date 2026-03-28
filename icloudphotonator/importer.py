from __future__ import annotations

import csv
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path


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

    def _verify_osxphotos(self):
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

        target_report_dir = Path(report_dir) if report_dir else Path(tempfile.mkdtemp(prefix="icloudphotonator-report-"))
        target_report_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_report_dir / f"import-report-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.csv"

        try:
            self._run_import(file_paths, skip_dups, auto_live, use_exiftool, album, report_path, timeout, library)
        except Exception as exc:
            # Walk the full exception chain to capture root causes
            parts: list[str] = []
            current: BaseException | None = exc
            seen: set[int] = set()
            while current is not None and id(current) not in seen:
                seen.add(id(current))
                msg = str(current).strip()
                if msg:
                    parts.append(msg)
                current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)
            error_msg = " → ".join(parts) if parts else ""
            if not error_msg:
                error_msg = f"{type(exc).__module__}.{type(exc).__name__}"
            if "Abort" in type(exc).__name__ and not parts:
                error_msg = "osxphotos aborted — möglicherweise fehlt exiftool (https://exiftool.org/)"
            return self._result_from_report(
                report_path=report_path,
                fallback_success=False,
                fallback_error=error_msg,
                file_count=len(file_paths),
            )

        return self._result_from_report(report_path=report_path, fallback_success=True)

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
        import concurrent.futures

        import_cli = self._get_import_cli()
        self._verbose_log: list[str] = []

        def _verbose_callback(msg: object) -> None:
            self._verbose_log.append(str(msg))

        import_kwargs = dict(
            files_or_dirs=tuple(str(path) for path in file_paths),
            skip_dups=skip_dups,
            auto_live=auto_live,
            exiftool=use_exiftool,
            no_progress=True,
            report=str(report_path),
            verbose=_verbose_callback,
        )
        if album:
            import_kwargs["album"] = (album,)
        if library is not None:
            import_kwargs["library"] = str(library)

        def _do_import() -> None:
            try:
                import_cli(**import_kwargs)
            except TypeError:
                # verbose kwarg not supported by this version of osxphotos
                import_kwargs.pop("verbose", None)
                self._verbose_log.clear()
                import_cli(**import_kwargs)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_import)
            try:
                future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"osxphotos Import-Timeout nach {timeout}s")

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
    ) -> ImportResult:
        parsed = self._parse_report(report_path) if report_path.exists() else ImportResult(
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
                parsed.errors.append({"file": "", "error": fallback_error})

        if parsed.report_path is None and report_path.exists():
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
                    error_text = f"Photos.app Fehler bei {Path(filepath).name}" if filepath else "osxphotos reported an error"
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