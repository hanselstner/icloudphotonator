from click.testing import CliRunner

from icloudphotonator.__main__ import main


def test_help_works() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "gui" in result.output
    assert "import-photos" in result.output


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
    assert "--library" in result.output
    assert "--mediathek" in result.output


def test_import_photos_passes_library_to_orchestrator(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "source"
    source_path.mkdir()
    library_path = tmp_path / "Family.photoslibrary"
    library_path.mkdir()
    captured: dict[str, object] = {}

    class DummyOrchestrator:
        def __init__(self, db_path, staging_dir, library=None) -> None:
            captured["db_path"] = db_path
            captured["staging_dir"] = staging_dir
            captured["library"] = library

        def on_progress(self, callback) -> None:
            captured["progress_callback"] = callback

        async def start_import(self, source_path) -> None:
            captured["source_path"] = source_path

    monkeypatch.setattr("icloudphotonator.logging_config.setup_logging", lambda: None)
    monkeypatch.setattr("icloudphotonator.orchestrator.ImportOrchestrator", DummyOrchestrator)

    result = CliRunner().invoke(
        main,
        ["import-photos", str(source_path), "--library", str(library_path)],
    )

    assert result.exit_code == 0
    assert captured["source_path"] == source_path
    assert captured["library"] == library_path
    assert str(library_path) in result.output


def test_ui_module_imports() -> None:
    from icloudphotonator.ui.app import ICloudPhotonatorApp

    assert ICloudPhotonatorApp.__name__ == "ICloudPhotonatorApp"