from click.testing import CliRunner

from icloudphotonator.__main__ import main


def test_cli_help_lists_gui_and_import_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "gui" in result.output
    assert "import-photos" in result.output


def test_cli_version_option() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_ui_module_imports() -> None:
    from icloudphotonator.ui.app import ICloudPhotonatorApp

    assert ICloudPhotonatorApp.__name__ == "ICloudPhotonatorApp"