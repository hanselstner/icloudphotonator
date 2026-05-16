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
        def _check_launch_environment_warning(self) -> None:
            calls.append("launch_env")

        def _show_onboarding(self) -> None:
            calls.append("onboarding")

        def _ensure_source_access_if_needed(self) -> None:
            calls.append("source_access")

        def _check_for_incomplete_jobs(self) -> None:
            calls.append("resume")

    app.ICloudPhotonatorApp._run_startup_sequence(DummyApp())

    assert calls == ["launch_env", "onboarding", "source_access", "resume"]


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



# --- launch_environment detection ---


def test_launch_environment_detects_dmg_volume_path() -> None:
    from icloudphotonator.launch_environment import detect_launch_environment

    env = detect_launch_environment("/Volumes/iCloudPhotonator/iCloudPhotonator.app/Contents/MacOS/iCloudPhotonator")

    assert env.kind == "dmg"
    assert env.is_risky is True


def test_launch_environment_detects_app_translocation_path() -> None:
    from icloudphotonator.launch_environment import detect_launch_environment

    env = detect_launch_environment(
        "/private/var/folders/xx/yy/T/AppTranslocation/ABC-123/d/iCloudPhotonator.app/Contents/MacOS/iCloudPhotonator"
    )

    assert env.kind == "translocation"
    assert env.is_risky is True


def test_launch_environment_returns_ok_for_applications_path() -> None:
    from icloudphotonator.launch_environment import detect_launch_environment

    env = detect_launch_environment("/Applications/iCloudPhotonator.app/Contents/MacOS/iCloudPhotonator")

    assert env.kind == "ok"
    assert env.is_risky is False


def test_launch_environment_returns_ok_for_development_path() -> None:
    from icloudphotonator.launch_environment import detect_launch_environment

    env = detect_launch_environment("/Users/dev/code/icloudphotonator/.venv/bin/python")

    assert env.kind == "ok"
    assert env.is_risky is False


def test_launch_environment_uses_meipass_when_no_path_given(monkeypatch) -> None:
    import sys as _sys

    from icloudphotonator.launch_environment import detect_launch_environment

    monkeypatch.setattr(_sys, "_MEIPASS", "/Volumes/iCloudPhotonator 1/iCloudPhotonator.app/Contents/MacOS", raising=False)
    try:
        env = detect_launch_environment()
    finally:
        # monkeypatch removes attributes it added, but be defensive in case real attr existed
        pass

    assert env.kind == "dmg"
    assert env.path.startswith("/Volumes/")


# --- _check_launch_environment_warning dispatch ---


def test_check_launch_environment_warning_skips_when_path_ok(monkeypatch) -> None:
    """When the launch path is safe, no dialog is shown and no log entry is written."""
    from icloudphotonator.launch_environment import LaunchEnvironment

    monkeypatch.setattr(app, "_launch_warning_dismissed", False)
    monkeypatch.setattr(
        app, "detect_launch_environment", lambda: LaunchEnvironment(kind="ok", path="/Applications/iCloudPhotonator.app")
    )
    dialog_recorder = MagicMock()
    monkeypatch.setattr(app, "DmgLaunchDialog", dialog_recorder)

    class DummyApp:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def add_log(self, message: str) -> None:
            self.logs.append(message)

        def wait_window(self, dialog) -> None:  # pragma: no cover - shouldn't run
            self.logs.append("waited")

    dummy = DummyApp()
    app.ICloudPhotonatorApp._check_launch_environment_warning(dummy)

    dialog_recorder.assert_not_called()
    assert dummy.logs == []


def test_check_launch_environment_warning_shows_dialog_on_dmg(monkeypatch) -> None:
    """When the launch path is risky, the dialog is constructed and shown."""
    load_locale("de")
    from icloudphotonator.launch_environment import LaunchEnvironment

    monkeypatch.setattr(app, "_launch_warning_dismissed", False)
    env = LaunchEnvironment(kind="dmg", path="/Volumes/iCloudPhotonator/x.app")
    monkeypatch.setattr(app, "detect_launch_environment", lambda: env)

    constructed: dict[str, object] = {}

    class FakeDialog:
        def __init__(self, master, environment, on_continue=None):
            constructed["master"] = master
            constructed["environment"] = environment
            constructed["on_continue"] = on_continue
            self.chosen_action = "continue"

    monkeypatch.setattr(app, "DmgLaunchDialog", FakeDialog)

    class DummyApp:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def add_log(self, message: str) -> None:
            self.logs.append(message)

        def wait_window(self, dialog) -> None:
            self.logs.append("waited")

    dummy = DummyApp()
    app.ICloudPhotonatorApp._check_launch_environment_warning(dummy)

    assert constructed["master"] is dummy
    assert constructed["environment"] is env
    assert dummy.logs[0].startswith("⚠️")
    assert dummy.logs[-1] == "waited"
    # "continue" must mark the session flag so the dialog isn't shown again
    assert app._launch_warning_dismissed is True


def test_check_launch_environment_warning_respects_session_flag(monkeypatch) -> None:
    """Once the user picked Continue, the dialog is not shown again this session."""
    monkeypatch.setattr(app, "_launch_warning_dismissed", True)
    dialog_recorder = MagicMock()
    monkeypatch.setattr(app, "DmgLaunchDialog", dialog_recorder)
    monkeypatch.setattr(app, "detect_launch_environment", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    class DummyApp:
        def add_log(self, message: str) -> None:  # pragma: no cover - shouldn't run
            pass

    app.ICloudPhotonatorApp._check_launch_environment_warning(DummyApp())

    dialog_recorder.assert_not_called()


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")


def test_has_media_files_empty_folder(tmp_path) -> None:
    assert app._has_media_files(tmp_path) is False


def test_has_media_files_top_level_match(tmp_path) -> None:
    _touch(tmp_path / "a.jpg")
    assert app._has_media_files(tmp_path) is True


def test_has_media_files_one_level_deep(tmp_path) -> None:
    _touch(tmp_path / "Sub" / "a.jpg")
    assert app._has_media_files(tmp_path) is True


def test_has_media_files_five_levels_deep(tmp_path) -> None:
    _touch(tmp_path / "A" / "B" / "C" / "D" / "E" / "a.jpg")
    assert app._has_media_files(tmp_path) is True


def test_has_media_files_skips_hidden_directories(tmp_path) -> None:
    _touch(tmp_path / ".hidden" / "a.jpg")
    assert app._has_media_files(tmp_path) is False


def test_has_media_files_skips_synology_workdir(tmp_path) -> None:
    _touch(tmp_path / "@eaDir" / "a.jpg")
    assert app._has_media_files(tmp_path) is False


def test_has_media_files_ignores_sidecar_and_text_files(tmp_path) -> None:
    _touch(tmp_path / "a.aae")
    _touch(tmp_path / "Sub" / "notes.txt")
    _touch(tmp_path / "Sub" / "More" / "extra.AAE")
    assert app._has_media_files(tmp_path) is False


def test_has_media_files_detects_canon_raw(tmp_path) -> None:
    _touch(tmp_path / "DCIM" / "IMG_0001.cr2")
    assert app._has_media_files(tmp_path) is True


def test_has_media_files_mixed_case_extensions(tmp_path) -> None:
    _touch(tmp_path / "A.JPG")
    assert app._has_media_files(tmp_path) is True
    other = tmp_path / "other"
    _touch(other / "b.HEIC")
    assert app._has_media_files(other) is True


def test_has_media_files_skips_dotfiles(tmp_path) -> None:
    _touch(tmp_path / ".a.jpg")
    _touch(tmp_path / "Sub" / ".b.png")
    assert app._has_media_files(tmp_path) is False
