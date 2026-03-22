from pathlib import Path

import pytest

from icloudphotonator.scanner import MediaType, ScanCancelledError, Scanner


def _write_file(path: Path, size: int = 128) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


@pytest.mark.parametrize(
    ("filename", "expected_type"),
    [
        ("sample.heic", MediaType.PHOTO),
        ("sample.jpg", MediaType.PHOTO),
        ("sample.jpeg", MediaType.PHOTO),
        ("sample.png", MediaType.PHOTO),
        ("sample.heif", MediaType.PHOTO),
        ("sample.tiff", MediaType.PHOTO),
        ("sample.tif", MediaType.PHOTO),
        ("sample.bmp", MediaType.PHOTO),
        ("sample.gif", MediaType.PHOTO),
        ("sample.webp", MediaType.PHOTO),
        ("sample.raw", MediaType.PHOTO),
        ("sample.cr2", MediaType.PHOTO),
        ("sample.nef", MediaType.PHOTO),
        ("sample.arw", MediaType.PHOTO),
        ("sample.dng", MediaType.PHOTO),
        ("sample.mov", MediaType.VIDEO),
        ("sample.mp4", MediaType.VIDEO),
        ("sample.m4v", MediaType.VIDEO),
        ("sample.avi", MediaType.VIDEO),
        ("sample.aae", MediaType.AAE),
    ],
)
def test_classify_supported_formats(tmp_path: Path, filename: str, expected_type: MediaType) -> None:
    file_path = _write_file(tmp_path / filename)
    scanner = Scanner(tmp_path, compute_hashes=False)

    assert scanner._classify_file(file_path) is expected_type


def test_detects_live_photo_pairs(tmp_path: Path) -> None:
    _write_file(tmp_path / "IMG_0001.HEIC")
    _write_file(tmp_path / "IMG_0001.MOV")
    _write_file(tmp_path / "IMG_0001.AAE")
    _write_file(tmp_path / "IMG_0002.JPG")

    manifest = Scanner(tmp_path, compute_hashes=False).scan()

    assert len(manifest.live_photo_pairs) == 1
    photo, video = manifest.live_photo_pairs[0]
    assert photo.path.name == "IMG_0001.HEIC"
    assert video.path.name == "IMG_0001.MOV"


def test_hidden_files_are_skipped(tmp_path: Path) -> None:
    _write_file(tmp_path / ".hidden.jpg")
    _write_file(tmp_path / "visible.jpg")

    manifest = Scanner(tmp_path, compute_hashes=False).scan()

    assert [file.path.name for file in manifest.files] == ["visible.jpg"]


def test_small_files_are_skipped(tmp_path: Path) -> None:
    _write_file(tmp_path / "tiny.jpg", size=99)
    _write_file(tmp_path / "valid.jpg", size=100)

    manifest = Scanner(tmp_path, compute_hashes=False).scan()

    assert [file.path.name for file in manifest.files] == ["valid.jpg"]


def test_scan_calls_pause_check_for_each_discovered_file(tmp_path: Path) -> None:
    _write_file(tmp_path / "one.jpg")
    _write_file(tmp_path / "two.jpg")
    pause_calls: list[str] = []

    manifest = Scanner(tmp_path, compute_hashes=False).scan(
        pause_check=lambda: pause_calls.append("pause")
    )

    assert len(manifest.files) == 2
    assert pause_calls == ["pause", "pause"]


def test_scan_raises_when_cancelled(tmp_path: Path) -> None:
    _write_file(tmp_path / "one.jpg")
    _write_file(tmp_path / "two.jpg")
    pause_calls: list[str] = []
    cancel_checks = {"count": 0}

    def _cancel_check() -> bool:
        cancel_checks["count"] += 1
        return cancel_checks["count"] == 1

    with pytest.raises(ScanCancelledError):
        Scanner(tmp_path, compute_hashes=False).scan(
            pause_check=lambda: pause_calls.append("pause"),
            cancel_check=_cancel_check,
        )

    assert pause_calls == ["pause"]
    assert cancel_checks["count"] == 1