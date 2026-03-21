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


def test_ui_module_imports() -> None:
    from icloudphotonator.ui.app import ICloudPhotonatorApp

    assert ICloudPhotonatorApp.__name__ == "ICloudPhotonatorApp"