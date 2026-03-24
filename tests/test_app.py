import json
from types import SimpleNamespace

import icloudphotonator.ui.app as app


def test_prompt_for_automation_permission_uses_german_dialog(monkeypatch) -> None:
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

    def fake_run(command, capture_output=False, timeout=None, check=False):
        captured["command"] = command
        captured["capture_output"] = capture_output
        captured["timeout"] = timeout
        captured["check"] = check
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(app.subprocess, "run", fake_run)

    assert app._check_automation_permission() is True
    assert captured["command"] == ["osascript", "-e", 'tell application "Photos" to get name']
    assert captured["capture_output"] is True
    assert captured["timeout"] == 10
    assert captured["check"] is False


def test_check_automation_permission_returns_false_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(app.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))

    assert app._check_automation_permission() is False


def test_onboarding_done_round_trip_uses_config_file(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(app, "ONBOARDING_CONFIG_PATH", config_path)

    assert app._check_onboarding_done() is False

    app._mark_onboarding_done()

    assert app._check_onboarding_done() is True
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"onboarding_done": True}


def test_show_onboarding_uses_german_dialog_and_marks_completion(monkeypatch) -> None:
    captured: dict[str, object] = {}
    logs: list[str] = []
    marks: list[str] = []

    class FakeMessageBox:
        @staticmethod
        def showinfo(title, message):
            captured["title"] = title
            captured["message"] = message
            return "ok"

    class DummyApp:
        def add_log(self, message: str) -> None:
            logs.append(message)

    monkeypatch.setattr(app, "messagebox", FakeMessageBox)
    monkeypatch.setattr(app, "_check_onboarding_done", lambda: False)
    monkeypatch.setattr(app, "_check_automation_permission", lambda: True)
    monkeypatch.setattr(app, "_mark_onboarding_done", lambda: marks.append("done"))

    app.ICloudPhotonatorApp._show_onboarding(DummyApp())

    assert captured["title"] == "Willkommen bei iCloudPhotonator"
    assert "Automation (Fotos-App)" in captured["message"]
    assert "Fotomediathek" in captured["message"]
    assert "Bitte bestätigen Sie jeweils mit „OK“." in captured["message"]
    assert logs == ["Prüfe Automation-Berechtigung...", "✅ Automation-Berechtigung erteilt."]
    assert marks == ["done"]


def test_run_startup_sequence_runs_onboarding_before_resume_check() -> None:
    calls: list[str] = []

    class DummyApp:
        def _show_onboarding(self) -> None:
            calls.append("onboarding")

        def _check_for_incomplete_jobs(self) -> None:
            calls.append("resume")

    app.ICloudPhotonatorApp._run_startup_sequence(DummyApp())

    assert calls == ["onboarding", "resume"]