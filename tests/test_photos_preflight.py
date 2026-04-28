import sqlite3
from pathlib import Path

import pytest

from icloudphotonator import photos_preflight
from icloudphotonator.photos_preflight import (
    PhotosPreflight,
    check_library_readable,
)


def _make_photoslibrary(tmp_path: Path) -> Path:
    library = tmp_path / "Personal.photoslibrary"
    (library / "database").mkdir(parents=True)
    db = library / "database" / "Photos.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
    conn.close()
    return library


def test_check_library_readable_returns_true_for_real_sqlite_db(tmp_path: Path) -> None:
    library = _make_photoslibrary(tmp_path)
    assert check_library_readable(library) is True


def test_check_library_readable_returns_false_when_sqlite_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _make_photoslibrary(tmp_path)

    def fake_connect(_path: str):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(photos_preflight.sqlite3, "connect", fake_connect)
    assert check_library_readable(library) is False


def test_check_library_readable_resolves_via_osxphotos_when_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _make_photoslibrary(tmp_path)

    monkeypatch.setattr(
        "osxphotos.utils.get_last_library_path",
        lambda: str(library),
    )
    assert check_library_readable(None) is True


def test_run_preflight_records_library_readable_failure_and_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _make_photoslibrary(tmp_path)
    pre = PhotosPreflight()

    monkeypatch.setattr(pre, "check_photos_running", lambda: True)
    monkeypatch.setattr(pre, "check_automation_permission", lambda: True)
    monkeypatch.setattr(pre, "check_photos_responsive", lambda: True)
    monkeypatch.setattr(pre, "_check_has_window", lambda: True)

    def fake_connect(_path: str):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(photos_preflight.sqlite3, "connect", fake_connect)

    result = pre.run_preflight(library=library)

    assert result.checks["library_readable"] is False
    assert result.passed is False
    assert any("Full Disk Access" in err for err in result.errors)


def test_run_preflight_passes_when_library_readable_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = _make_photoslibrary(tmp_path)
    pre = PhotosPreflight()

    monkeypatch.setattr(pre, "check_photos_running", lambda: True)
    monkeypatch.setattr(pre, "check_automation_permission", lambda: True)
    monkeypatch.setattr(pre, "check_photos_responsive", lambda: True)
    monkeypatch.setattr(pre, "_check_has_window", lambda: True)

    result = pre.run_preflight(library=library)

    assert result.checks["library_readable"] is True
    assert result.passed is True
    assert result.errors == []

