from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class ScanCancelledError(RuntimeError):
    """Raised when a scan is cancelled."""


class MediaType(Enum):
    PHOTO = "photo"
    VIDEO = "video"
    AAE = "aae"
    UNKNOWN = "unknown"


SUPPORTED_FORMATS: dict[MediaType, set[str]] = {
    MediaType.PHOTO: {
        ".heic",
        ".jpg",
        ".jpeg",
        ".png",
        ".heif",
        ".tiff",
        ".tif",
        ".bmp",
        ".gif",
        ".webp",
        ".raw",
        ".cr2",
        ".nef",
        ".arw",
        ".dng",
    },
    MediaType.VIDEO: {".mov", ".mp4", ".m4v", ".avi"},
    MediaType.AAE: {".aae"},
}


@dataclass
class FileInfo:
    path: Path
    size: int
    hash: str | None
    created: datetime
    modified: datetime
    media_type: MediaType
    format: str


@dataclass
class ScanManifest:
    files: list[FileInfo]
    live_photo_pairs: list[tuple[FileInfo, FileInfo]]
    total_size: int
    source_path: Path
    is_network_source: bool
    scan_timestamp: datetime


class Scanner:
    def __init__(self, source_path: Path, compute_hashes: bool = True) -> None:
        self.source_path = Path(source_path)
        self.compute_hashes = compute_hashes

    def scan(
        self,
        progress_callback: Callable[[FileInfo], None] | None = None,
        pause_check: Callable[[], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ScanManifest:
        files: list[FileInfo] = []
        total_size = 0
        is_network_source = self._is_network_path(self.source_path)

        def _walk_error(error: OSError) -> None:
            logger.warning("Unable to access %s: %s", error.filename, error)

        for root, dirs, filenames in os.walk(self.source_path, onerror=_walk_error):
            dirs[:] = [directory for directory in dirs if not directory.startswith(".")]

            for filename in filenames:
                if filename.startswith("."):
                    continue

                path = Path(root) / filename
                media_type = self._classify_file(path)
                if media_type is MediaType.UNKNOWN:
                    continue

                try:
                    stat_result = path.stat()
                except (OSError, PermissionError) as exc:
                    logger.warning("Skipping unreadable file %s: %s", path, exc)
                    continue

                if stat_result.st_size < 100:
                    logger.info("Skipping suspiciously small file %s", path)
                    continue

                file_hash: str | None = None
                if self.compute_hashes:
                    try:
                        if is_network_source:
                            file_hash = self._compute_hash_with_timeout(path, timeout_seconds=60)
                        else:
                            file_hash = self._compute_hash(path)
                    except TimeoutError:
                        logger.warning("Hash computation timed out for %s", path)
                    except (OSError, PermissionError) as exc:
                        logger.warning("Failed to hash %s: %s", path, exc)

                file_info = FileInfo(
                    path=path,
                    size=stat_result.st_size,
                    hash=file_hash,
                    created=datetime.fromtimestamp(stat_result.st_ctime),
                    modified=datetime.fromtimestamp(stat_result.st_mtime),
                    media_type=media_type,
                    format=path.suffix.lstrip(".").upper(),
                )
                files.append(file_info)
                total_size += stat_result.st_size

                if progress_callback is not None:
                    progress_callback(file_info)

                if pause_check is not None:
                    pause_check()

                if cancel_check is not None and cancel_check():
                    raise ScanCancelledError(f"Scan cancelled while processing {path}")

        return ScanManifest(
            files=files,
            live_photo_pairs=self._detect_live_pairs(files),
            total_size=total_size,
            source_path=self.source_path,
            is_network_source=is_network_source,
            scan_timestamp=datetime.now(),
        )

    def _classify_file(self, path: Path) -> MediaType:
        extension = path.suffix.lower()
        for media_type, extensions in SUPPORTED_FORMATS.items():
            if extension in extensions:
                return media_type
        return MediaType.UNKNOWN

    def _compute_hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(8192):
                digest.update(chunk)
        return digest.hexdigest()

    def _compute_hash_with_timeout(self, path: Path, timeout_seconds: int) -> str:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._compute_hash, path)
            try:
                return future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Timed out hashing {path}")

    def _detect_live_pairs(self, files: list[FileInfo]) -> list[tuple[FileInfo, FileInfo]]:
        photos: dict[tuple[Path, str], list[FileInfo]] = {}
        videos: dict[tuple[Path, str], list[FileInfo]] = {}

        for file_info in files:
            key = (file_info.path.parent, file_info.path.stem)
            if file_info.media_type is MediaType.PHOTO:
                photos.setdefault(key, []).append(file_info)
            elif file_info.media_type is MediaType.VIDEO:
                videos.setdefault(key, []).append(file_info)

        live_pairs: list[tuple[FileInfo, FileInfo]] = []
        for key in photos.keys() & videos.keys():
            for photo, video in zip(photos[key], videos[key]):
                live_pairs.append((photo, video))
        return live_pairs

    def _is_network_path(self, path: Path) -> bool:
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
            logger.debug("Falling back to /Volumes heuristic for %s", resolved)
            return True

        network_filesystems = {"smbfs", "nfs", "afpfs"}
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

        return best_match is not None and best_match[1] in network_filesystems
