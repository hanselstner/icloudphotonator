from click.testing import CliRunner

from icloudphotonator.__main__ import main


def test_help_works() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "gui" in result.output
    assert "import-photos" in result.output
    assert "retry-errors" in result.output


def test_version_works() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_import_photos_help_shows_expected_options() -> None:
    result = CliRunner().invoke(main, ["import-photos", "--help"])

    assert result.exit_code == 0
    assert "SOURCE" in result.output
    assert "--staging-dir" in result.output
    assert "--db-path" in result.output
    assert "--album" in result.output
    assert "--library" in result.output
    assert "--mediathek" in result.output


def test_import_photos_passes_library_and_album_to_orchestrator(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "source"
    source_path.mkdir()
    album = "Custom Album"
    library_path = tmp_path / "Family.photoslibrary"
    library_path.mkdir()
    captured: dict[str, object] = {}

    class DummyOrchestrator:
        def __init__(self, db_path, staging_dir, library=None, album=None) -> None:
            captured["db_path"] = db_path
            captured["staging_dir"] = staging_dir
            captured["library"] = library
            captured["album"] = album

        def on_progress(self, callback) -> None:
            captured["progress_callback"] = callback

        async def start_import(self, source_path) -> None:
            captured["source_path"] = source_path

    monkeypatch.setattr("icloudphotonator.logging_config.setup_logging", lambda: None)
    monkeypatch.setattr("icloudphotonator.orchestrator.ImportOrchestrator", DummyOrchestrator)

    result = CliRunner().invoke(
        main,
        ["import-photos", str(source_path), "--album", album, "--library", str(library_path)],
    )

    assert result.exit_code == 0
    assert captured["source_path"] == source_path
    assert captured["album"] == album
    assert captured["library"] == library_path
    assert album in result.output
    assert str(library_path) in result.output


def test_import_photos_defaults_album_to_source_folder_name(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "Kristins iPhone"
    source_path.mkdir()
    captured: dict[str, object] = {}

    class DummyOrchestrator:
        def __init__(self, db_path, staging_dir, library=None, album=None) -> None:
            captured["album"] = album

        def on_progress(self, callback) -> None:
            captured["progress_callback"] = callback

        async def start_import(self, source_path) -> None:
            captured["source_path"] = source_path

    monkeypatch.setattr("icloudphotonator.logging_config.setup_logging", lambda: None)
    monkeypatch.setattr("icloudphotonator.orchestrator.ImportOrchestrator", DummyOrchestrator)

    result = CliRunner().invoke(main, ["import-photos", str(source_path)])

    assert result.exit_code == 0
    assert captured["source_path"] == source_path
    assert captured["album"] == source_path.name
    assert source_path.name in result.output


def test_ui_module_imports() -> None:
    from icloudphotonator.ui.app import ICloudPhotonatorApp

    assert ICloudPhotonatorApp.__name__ == "ICloudPhotonatorApp"


def test_retry_errors_resets_latest_job_error_files(tmp_path) -> None:
    from icloudphotonator.db import Database
    from icloudphotonator.state import FileStatus

    db_path = tmp_path / "jobs.db"
    db = Database(db_path)
    job_id = db.create_job("/photos", {})
    error_id = db.add_file(job_id, "/photos/a.jpg", 1, "hash-a", "image")
    db.update_file_status(error_id, FileStatus.ERROR, error_message="failed")

    result = CliRunner().invoke(main, ["retry-errors", "--db-path", str(db_path)])

    assert result.exit_code == 0
    assert job_id in result.output
    assert "1 Fehlerdateien" in result.output
    pending_rows = db.get_pending_files(job_id, limit=10)
    assert [row["path"] for row in pending_rows] == ["/photos/a.jpg"]