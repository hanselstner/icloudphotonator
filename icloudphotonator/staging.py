from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from .scanner import FileInfo


class StagingManager:
    """Stages files from network sources to local temp directory."""

    def __init__(self, staging_dir: Path | None = None, max_staging_size_gb: float = 10.0):
        self._staging_dir = Path(staging_dir) if staging_dir else Path(tempfile.gettempdir()) / "icloudphotonator-staging"
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._max_staging_size_bytes = int(max(0.0, max_staging_size_gb) * 1024**3)

    def stage_files(self, files: list[FileInfo], progress_callback=None) -> list[tuple[FileInfo, Path]]:
        """Copy files to local staging. Returns list of (original_info, staged_path).

        For local files, returns the original path (no copy needed).
        For network files, copies to staging_dir.
        """
        staged_files: list[tuple[FileInfo, Path]] = []
        used_bytes, max_bytes = self.get_staging_usage()
        projected_usage = used_bytes

        for file_info in files:
            if not self._requires_staging(file_info.path):
                staged_files.append((file_info, file_info.path))
                if progress_callback is not None:
                    progress_callback(file_info, file_info.path)
                continue

            projected_usage += file_info.size
            if max_bytes and projected_usage > max_bytes:
                raise RuntimeError("Staging area is full; increase max_staging_size_gb or clean up staged files.")

            staged_path = self._staging_dir / f"{uuid4().hex}_{file_info.path.name}"
            shutil.copy2(file_info.path, staged_path)
            staged_files.append((file_info, staged_path))
            if progress_callback is not None:
                progress_callback(file_info, staged_path)

        return staged_files

    def cleanup_staged(self, staged_paths: list[Path]):
        """Remove staged files after successful import."""
        for staged_path in staged_paths:
            path = Path(staged_path)
            try:
                path.relative_to(self._staging_dir)
            except ValueError:
                continue
            if path.exists() and path.is_file():
                path.unlink()

    def get_staging_usage(self) -> tuple[int, int]:
        """Returns (used_bytes, max_bytes)."""
        used_bytes = sum(path.stat().st_size for path in self._staging_dir.rglob("*") if path.is_file())
        return used_bytes, self._max_staging_size_bytes

    @property
    def staging_dir(self) -> Path:
        return self._staging_dir

    def _requires_staging(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path

        resolved_str = str(resolved)
        if not resolved_str.startswith("/Volumes/"):
            return False

        try:
            mount_output = subprocess.run(
                ["mount"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return True

        best_match: tuple[int, str] | None = None
        for line in mount_output.splitlines():
            match = re.search(r" on (.+?) \((.+?)\)$", line)
            if not match:
                continue
            mount_point = match.group(1)
            fs_type = match.group(2).split(",", 1)[0].strip().lower()
            if resolved_str == mount_point or resolved_str.startswith(f"{mount_point.rstrip('/')}/"):
                if best_match is None or len(mount_point) > best_match[0]:
                    best_match = (len(mount_point), fs_type)

        return best_match is not None and best_match[1] in {"smbfs", "nfs", "afpfs"}