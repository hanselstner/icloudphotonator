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