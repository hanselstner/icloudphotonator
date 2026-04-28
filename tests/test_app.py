import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import icloudphotonator.ui.app as app
from icloudphotonator.i18n import load_locale


def test_prompt_for_automation_permission_uses_german_dialog(monkeypatch) -> None:
    load_locale("de")
    captured: dict[str, object] = {}

    class FakeMessageBox:
        @staticmethod
        def askyesno(title, message, icon=None):
            captured["title"] = title
            captured["message"] = message
            captured["icon"] = icon
            return True

    monkeypatch.setattr(app, "messagebox", FakeMessageBox)

    assert app._prompt_for_automation_permission() is True
    assert captured["title"] == "Berechtigung erforderlich"
    assert "Automation-Berechtigung" in captured["message"]
    assert "Fotos.app" in captured["message"]
    assert captured["icon"] == "warning"


def test_open_automation_settings_uses_system_preferences_deeplink(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, check=False):
        captured["command"] = command
        captured["check"] = check

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    app._open_automation_settings()

    assert captured["command"] == [
        "open",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
    ]
    assert captured["check"] is False


def test_check_automation_permission_runs_minimal_photos_applescript(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_applescript(script: str):
        captured["script"] = script
        return (True, "Photos")

    monkeypatch.setattr("icloudphotonator.photos_preflight.run_applescript", fake_run_applescript)

    assert app._check_automation_permission() is True
    assert captured["script"] == 'tell application "Photos" to get name'


def test_check_automation_permission_returns_false_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "icloudphotonator.photos_preflight.run_applescript",
        lambda script: (False, "Error -1743: Not authorized"),
    )

    assert app._check_automation_permission() is False


def test_onboarding_done_round_trip_uses_config_file(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: True)
    monkeypatch.setattr(app, "_check_library_readable", lambda: True)

    assert app._check_onboarding_done() is False

    app._mark_onboarding_done()

    assert app._check_onboarding_done() is True
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"onboarding_done": True}


def test_mark_onboarding_done_does_not_persist_when_full_disk_access_missing(
    tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: True)
    monkeypatch.setattr(app, "_check_library_readable", lambda: False)

    persisted = app._mark_onboarding_done()

    assert persisted is False
    assert app._check_onboarding_done() is False
    assert not config_path.exists()


def test_mark_onboarding_done_force_persists_even_without_full_disk_access(
    tmp_path, monkeypatch
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: False)
    monkeypatch.setattr(app, "_check_library_readable", lambda: False)

    persisted = app._mark_onboarding_done(force=True)

    assert persisted is True
    assert app._check_onboarding_done() is True


def test_full_disk_access_settings_url_points_to_correct_pane() -> None:
    assert (
        app.FULL_DISK_ACCESS_SETTINGS_URL
        == "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
    )


def test_open_full_disk_access_settings_uses_deeplink(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, check=False):
        captured["command"] = command
        captured["check"] = check

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    app._open_full_disk_access_settings()

    assert captured["command"] == [
        "open",
        "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    ]
    assert captured["check"] is False


def test_locale_files_contain_full_disk_access_keys() -> None:
    locales_dir = app.Path(__file__).resolve().parent.parent / "icloudphotonator" / "locales"
    required_keys = [
        "onboarding.full_disk_title",
        "onboarding.full_disk_desc",
        "onboarding.full_disk_granted",
        "onboarding.full_disk_not_granted",
        "onboarding.open_full_disk_settings",
        "onboarding.skip_for_now",
        "onboarding.full_disk_previous_skip",
        "dialog.full_disk_title",
        "dialog.full_disk_message",
        "dialog.restart_app",
    ]
    for locale in ("en", "de"):
        data = json.loads((locales_dir / f"{locale}.json").read_text(encoding="utf-8"))
        for key in required_keys:
            assert key in data, f"Missing key {key!r} in {locale}.json"
            assert data[key], f"Empty value for {key!r} in {locale}.json"


def test_full_disk_skip_persists_to_config(tmp_path, monkeypatch) -> None:
    from datetime import datetime

    config_path = tmp_path / "config.json"
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)

    app._persist_full_disk_skip()

    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "onboarding_full_disk_skipped_at" in data
    # Must be a parseable ISO 8601 timestamp.
    datetime.fromisoformat(data["onboarding_full_disk_skipped_at"])
    assert app._check_full_disk_skip_persisted() is True


def test_full_disk_skip_cleared_when_fda_granted(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"onboarding_full_disk_skipped_at": "2026-04-28T12:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: True)
    monkeypatch.setattr(app, "_check_library_readable", lambda: True)

    persisted = app._mark_onboarding_done(force=True)

    assert persisted is True
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data.get("onboarding_done") is True
    assert "onboarding_full_disk_skipped_at" not in data
    assert app._check_full_disk_skip_persisted() is False


def test_full_disk_skip_persists_when_fda_still_missing(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"onboarding_full_disk_skipped_at": "2026-04-28T12:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: True)
    monkeypatch.setattr(app, "_check_library_readable", lambda: False)

    persisted = app._mark_onboarding_done(force=True)

    assert persisted is True
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data.get("onboarding_done") is True
    assert data.get("onboarding_full_disk_skipped_at") == "2026-04-28T12:00:00+00:00"
    assert app._check_full_disk_skip_persisted() is True


def test_show_onboarding_first_run_opens_dialog(monkeypatch) -> None:
    """On first run, _show_onboarding creates an OnboardingDialog and waits for it."""
    load_locale("de")
    dialog_instances: list[object] = []

    class FakeOnboardingDialog:
        def __init__(self, master, on_complete=None):
            dialog_instances.append(self)

    class DummyApp:
        def add_log(self, message: str) -> None:
            pass

        def wait_window(self, dialog) -> None:
            pass

    monkeypatch.setattr(app, "_check_onboarding_done", lambda: False)
    monkeypatch.setattr(app, "OnboardingDialog", FakeOnboardingDialog)

    app.ICloudPhotonatorApp._show_onboarding(DummyApp())

    assert len(dialog_instances) == 1


def test_show_onboarding_subsequent_run_checks_permission(monkeypatch) -> None:
    """On subsequent runs, _show_onboarding checks automation permission directly."""
    load_locale("de")
    logs: list[str] = []

    class DummyApp:
        def add_log(self, message: str) -> None:
            logs.append(message)

    monkeypatch.setattr(app, "_check_onboarding_done", lambda: True)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: True)

    app.ICloudPhotonatorApp._show_onboarding(DummyApp())

    assert logs == ["Prüfe Automation-Berechtigung...", "✅ Automation-Berechtigung erteilt."]



def test_run_startup_sequence_runs_onboarding_before_resume_check() -> None:
    calls: list[str] = []

    class DummyApp:
        def _show_onboarding(self) -> None:
            calls.append("onboarding")

        def _ensure_source_access_if_needed(self) -> None:
            calls.append("source_access")

        def _check_for_incomplete_jobs(self) -> None:
            calls.append("resume")

    app.ICloudPhotonatorApp._run_startup_sequence(DummyApp())

    assert calls == ["onboarding", "source_access", "resume"]


def test_handle_full_disk_access_error_constructs_dialog(monkeypatch) -> None:
    """The FDA error handler stops the bridge, finishes the run, and shows the dialog."""
    load_locale("de")

    dialog_recorder = MagicMock()
    monkeypatch.setattr(app, "FullDiskAccessDialog", dialog_recorder)

    class DummyApp:
        def __init__(self) -> None:
            self._is_running = True
            self._bridge = MagicMock()
            self._finish_run = MagicMock()

        def after(self, delay, callback):
            callback()

    dummy = DummyApp()

    app.ICloudPhotonatorApp._handle_full_disk_access_error(dummy)

    dialog_recorder.assert_called_once_with(dummy)
    dummy._bridge.stop.assert_called_once_with()
    dummy._finish_run.assert_called_once()
    finish_args = dummy._finish_run.call_args.args
    assert finish_args[0] == app.t("progress.error")
    assert finish_args[1] == app.t("error.full_disk_access_missing")


def test_handle_full_disk_access_error_skips_bridge_stop_when_idle(monkeypatch) -> None:
    """When no import is running, _bridge.stop() is not invoked but the dialog still appears."""
    load_locale("de")

    dialog_recorder = MagicMock()
    monkeypatch.setattr(app, "FullDiskAccessDialog", dialog_recorder)

    class DummyApp:
        def __init__(self) -> None:
            self._is_running = False
            self._bridge = MagicMock()
            self._finish_run = MagicMock()

        def after(self, delay, callback):
            callback()

    dummy = DummyApp()

    app.ICloudPhotonatorApp._handle_full_disk_access_error(dummy)

    dialog_recorder.assert_called_once_with(dummy)
    dummy._bridge.stop.assert_not_called()
    dummy._finish_run.assert_called_once()
