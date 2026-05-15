"""Tests for icloudphotonator.importer (subprocess-based osxphotos invocation)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from icloudphotonator.i18n import t
from icloudphotonator.importer import (
    PhotoImporter,
    _SubprocessImportError,
    find_photo_libraries,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CSV_HEADER = "filepath,imported,error,error_message,uuid\n"


def _make_importer(monkeypatch) -> PhotoImporter:
    """Construct a PhotoImporter without verifying the real osxphotos package."""
    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)
    return PhotoImporter()


def _patch_subprocess(
    monkeypatch,
    importer: PhotoImporter,
    *,
    returncode: int = 0,
    output: str = "",
    side_effect=None,
) -> dict:
    """Replace ``_run_subprocess`` with a recording stub. Returns a dict with calls."""
    calls: dict = {"count": 0, "cmd": None, "timeout": None, "cwd": None, "env": None}

    def fake_run_subprocess(cmd, timeout, cwd=None, env=None):
        calls["count"] += 1
        calls["cmd"] = cmd
        calls["timeout"] = timeout
        calls["cwd"] = cwd
        calls["env"] = env
        if side_effect is not None:
            return side_effect(cmd, timeout, cwd, env)
        return returncode, output

    monkeypatch.setattr(importer, "_run_subprocess", fake_run_subprocess)
    return calls


# ---------------------------------------------------------------------------
# Library discovery
# ---------------------------------------------------------------------------


def test_find_photo_libraries_searches_common_directories(tmp_path: Path, monkeypatch) -> None:
    pictures_dir = tmp_path / "Pictures"
    shared_dir = tmp_path / "Shared"
    pictures_dir.mkdir()
    shared_dir.mkdir()
    private_library = pictures_dir / "Private.photoslibrary"
    shared_library = shared_dir / "Family.photoslibrary"
    private_library.mkdir()
    shared_library.mkdir()
    (pictures_dir / "ignore.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr("icloudphotonator.importer.PICTURES_LIBRARY_DIR", pictures_dir)
    monkeypatch.setattr("icloudphotonator.importer.SHARED_LIBRARY_DIR", shared_dir)

    assert find_photo_libraries() == [private_library, shared_library]


# ---------------------------------------------------------------------------
# Successful import (with mock report)
# ---------------------------------------------------------------------------


def test_import_batch_returns_success_when_report_has_data(tmp_path: Path, monkeypatch) -> None:
    """Successful subprocess + non-empty report → ImportResult(success=True)."""
    importer = _make_importer(monkeypatch)
    file_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    library = tmp_path / "Shared.photoslibrary"
    library.mkdir()

    def write_report(cmd, timeout, cwd, env):
        report_idx = cmd.index("--report") + 1
        Path(cmd[report_idx]).write_text(
            CSV_HEADER
            + f"{file_paths[0]},true,false,,uuid-1\n"
            + f"{file_paths[1]},false,false,,\n",
            encoding="utf-8",
        )
        return 0, ""

    calls = _patch_subprocess(monkeypatch, importer, side_effect=write_report)
    result = importer.import_batch(
        file_paths, report_dir=tmp_path, album="Album", library=library, timeout=30,
    )

    assert calls["count"] == 1
    cmd = calls["cmd"]
    assert "-m" in cmd and "osxphotos" in cmd and "import" in cmd
    assert "--skip-dups" in cmd and "--auto-live" in cmd and "--exiftool" in cmd
    assert "--no-progress" in cmd
    assert ["--album", "Album"] == [cmd[cmd.index("--album")], cmd[cmd.index("--album") + 1]]
    assert ["--library", str(library)] == [
        cmd[cmd.index("--library")], cmd[cmd.index("--library") + 1],
    ]
    assert calls["timeout"] == 30
    assert result.success is True
    assert result.imported_count == 1
    assert result.skipped_count == 1
    assert result.error_count == 0
    assert result.errors == []
    assert result.report_path is not None and result.report_path.exists()


# ---------------------------------------------------------------------------
# Strict success semantics: no report ⇒ failure
# ---------------------------------------------------------------------------


def test_import_batch_returns_failure_when_report_is_missing(tmp_path: Path, monkeypatch) -> None:
    """Subprocess exits 0 but writes no report → silent failure (success=False)."""
    importer = _make_importer(monkeypatch)
    file_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    _patch_subprocess(monkeypatch, importer, returncode=0, output="")

    result = importer.import_batch(file_paths, report_dir=tmp_path, timeout=30)

    assert result.success is False
    assert result.imported_count == 0
    assert result.skipped_count == 0
    assert result.error_count == len(file_paths)
    assert result.errors == [{"file": "", "error": t("error.silent_failure_no_report")}]
    assert result.report_path is None


def test_import_batch_returns_failure_when_report_is_empty(tmp_path: Path, monkeypatch) -> None:
    """Subprocess exits 0 but writes 0-byte report → silent failure (success=False)."""
    importer = _make_importer(monkeypatch)
    file_paths = [tmp_path / "a.jpg"]

    def touch_empty_report(cmd, timeout, cwd, env):
        report_idx = cmd.index("--report") + 1
        Path(cmd[report_idx]).touch()  # 0-byte file
        return 0, ""

    _patch_subprocess(monkeypatch, importer, side_effect=touch_empty_report)

    result = importer.import_batch(file_paths, report_dir=tmp_path, timeout=30)

    assert result.success is False
    assert result.error_count == 1
    assert result.errors == [{"file": "", "error": t("error.silent_failure_no_report")}]
    # Empty report file still exists, so the path is reported for diagnostics.
    assert result.report_path is not None and result.report_path.exists()


# ---------------------------------------------------------------------------
# Subprocess failure classification
# ---------------------------------------------------------------------------


def test_import_batch_surfaces_subprocess_nonzero_exit(tmp_path: Path, monkeypatch) -> None:
    importer = _make_importer(monkeypatch)
    file_paths = [tmp_path / "a.jpg"]
    _patch_subprocess(monkeypatch, importer, returncode=1, output="some error from osxphotos")

    result = importer.import_batch(file_paths, report_dir=tmp_path, timeout=30)

    assert result.success is False
    assert result.error_count == 1
    assert "some error from osxphotos" in result.errors[0]["error"]


def test_import_batch_maps_aborted_output_to_descriptive_error(tmp_path: Path, monkeypatch) -> None:
    importer = _make_importer(monkeypatch)
    file_paths = [tmp_path / "a.jpg"]
    _patch_subprocess(monkeypatch, importer, returncode=1, output="Aborted!")

    result = importer.import_batch(file_paths, report_dir=tmp_path, timeout=30)

    assert result.success is False
    assert result.errors == [
        {
            "file": "",
            "error": "osxphotos aborted — exiftool may be missing (https://exiftool.org/)",
        }
    ]


def test_import_batch_maps_sqlite_open_error_to_full_disk_access_message(
    tmp_path: Path, monkeypatch
) -> None:
    importer = _make_importer(monkeypatch)
    file_paths = [tmp_path / "a.jpg"]
    library = tmp_path / "Personal.photoslibrary"
    library.mkdir()
    output = (
        "Traceback (most recent call last):\n"
        "  ...\n"
        "sqlite3.OperationalError: unable to open database file\n"
    )
    _patch_subprocess(monkeypatch, importer, returncode=1, output=output)

    result = importer.import_batch(
        file_paths, report_dir=tmp_path, library=library, timeout=30,
    )

    assert result.success is False
    assert result.error_count == 1
    assert result.errors == [
        {
            "file": "",
            "error": t("error.full_disk_access_missing"),
            "full_disk_access_missing": True,
        }
    ]


# ---------------------------------------------------------------------------
# Timeout behaviour: real subprocess via _run_subprocess
# ---------------------------------------------------------------------------


def test_run_subprocess_kills_hanging_process_and_raises_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    """A hanging child must be terminated within ~timeout seconds, not minutes."""
    import subprocess
    import sys as _sys

    importer = _make_importer(monkeypatch)
    # Spawn a real child that ignores SIGTERM-via-communicate and sleeps long.
    cmd = [_sys.executable, "-c", "import time; time.sleep(60)"]

    start = time.monotonic()
    try:
        importer._run_subprocess(cmd, timeout=1)
    except TimeoutError as exc:
        elapsed = time.monotonic() - start
        assert "timed out" in str(exc)
        # 1s timeout + up to 5s SIGTERM grace + up to 5s SIGKILL grace = 11s.
        # We assert well under that to prove we don't wait minutes.
        assert elapsed < 10.0, f"timeout took {elapsed:.1f}s, expected < 10s"
    else:  # pragma: no cover - defensive
        raise AssertionError("expected TimeoutError to be raised")

    # The spawned process must be reaped — poll() returns the exit code.
    proc: subprocess.Popen = importer._last_process
    assert proc.poll() is not None, "subprocess was not killed/reaped"


def test_run_subprocess_sigterm_then_sigkill_when_terminate_ignored(
    monkeypatch, tmp_path: Path
) -> None:
    """Verify the two-stage kill: SIGTERM first, then SIGKILL after grace."""
    importer = _make_importer(monkeypatch)

    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 99999
            self.returncode = -9
            self.terminated = False
            self.killed = False
            self._communicate_calls = 0

        def communicate(self, timeout=None):
            self._communicate_calls += 1
            # 1) initial wait → raise TimeoutExpired (still hanging)
            # 2) after terminate() → also TimeoutExpired (ignored SIGTERM)
            # 3) after kill() → returns
            import subprocess as _sp
            if self._communicate_calls < 3:
                raise _sp.TimeoutExpired(cmd=["x"], timeout=timeout or 1)
            return ("partial output\n", None)

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

    fake = FakeProcess()

    def fake_popen(*args, **kwargs):
        return fake

    monkeypatch.setattr("icloudphotonator.importer.subprocess.Popen", fake_popen)

    raised = False
    try:
        importer._run_subprocess(["nope"], timeout=1)
    except TimeoutError:
        raised = True

    assert raised, "TimeoutError must be raised after kill sequence"
    assert fake.terminated, "process.terminate() must be called on first timeout"
    assert fake.killed, "process.kill() must be called when SIGTERM is ignored"
    assert fake._communicate_calls == 3



# ---------------------------------------------------------------------------
# _build_command: dev vs. frozen (PyInstaller) dispatch
# ---------------------------------------------------------------------------


def _build_command_args(tmp_path: Path) -> dict:
    """Common kwargs for ``PhotoImporter._build_command``."""
    return {
        "file_paths": [tmp_path / "a.jpg"],
        "skip_dups": True,
        "auto_live": True,
        "use_exiftool": True,
        "album": "Album",
        "report_path": tmp_path / "report.csv",
        "library": None,
    }


def test_build_command_uses_python_module_in_dev(tmp_path: Path, monkeypatch) -> None:
    """In dev mode (sys.frozen unset) we invoke ``python -m osxphotos import``."""
    importer = _make_importer(monkeypatch)
    # Ensure no leftover sys.frozen from another test.
    monkeypatch.delattr(sys, "frozen", raising=False)

    cmd = importer._build_command(**_build_command_args(tmp_path))

    assert cmd[:4] == [sys.executable, "-m", "osxphotos", "import"]
    assert "--run-osxphotos" not in cmd


def test_build_command_uses_argv_marker_in_frozen(tmp_path: Path, monkeypatch) -> None:
    """In a frozen PyInstaller bundle we re-invoke ourselves via ``--run-osxphotos``."""
    importer = _make_importer(monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/fake/app")

    cmd = importer._build_command(**_build_command_args(tmp_path))

    assert cmd[:3] == ["/fake/app", "--run-osxphotos", "import"]
    assert "-m" not in cmd
