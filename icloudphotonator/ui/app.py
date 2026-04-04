from __future__ import annotations

import json
import os
import subprocess
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog
    from tkinter import messagebox

    import customtkinter as ctk
except ModuleNotFoundError as exc:
    tk = None
    filedialog = None
    messagebox = None
    ctk = None
    _UI_IMPORT_ERROR = exc
else:
    _UI_IMPORT_ERROR = None

from icloudphotonator.i18n import t, load_locale, get_locale
from icloudphotonator.importer import find_photo_libraries
from icloudphotonator.persistence import APP_DIR
from icloudphotonator.settings import ImportSettings

from .bridge import BackendBridge

APP_TITLE = "iCloudPhotonator"
REPOSITORY_URL = "https://github.com/hanselstner/icloudphototnator"
ACCENT_BLUE = "#007AFF"

# --- Design System ---
BG_PRIMARY = ("#f5f5f7", "#1c1c1e")
BG_CARD = ("#ffffff", "#2c2c2e")
TEXT_PRIMARY = ("#1c1c1e", "#f5f5f7")
TEXT_SECONDARY = ("#8e8e93", "#8e8e93")
BORDER = ("#e5e5ea", "#38383a")
SUCCESS = "#34C759"
WARNING = "#FF9500"
ERROR = "#FF3B30"

AUTOMATION_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
ONBOARDING_CONFIG_PATH = APP_DIR / "config.json"
PERMISSION_DIALOG_TITLE = "dialog.permission_title"  # i18n key
PERMISSION_DIALOG_TEXT = "dialog.permission_message"  # i18n key
ONBOARDING_DIALOG_TITLE = "onboarding.title"  # i18n key
ONBOARDING_DIALOG_TEXT = "onboarding.message"  # i18n key


def build_library_options(libraries: list[Path]) -> dict[str, Path | None]:
    """Build display labels for selectable Photos libraries."""
    options: dict[str, Path | None] = {t("app.default_library"): None}
    for path in libraries:
        options[f"{path.stem} — {path}"] = path
    return options


def _raise_missing_ui_support() -> None:
    message = (
        "Tkinter support is not available in this Python environment. "
        "Install a Python build with Tk support to launch the GUI."
    )
    raise RuntimeError(message) from _UI_IMPORT_ERROR


def _open_automation_settings() -> None:
    subprocess.run(["open", AUTOMATION_SETTINGS_URL], check=False)


def _prompt_for_automation_permission() -> bool:
    if messagebox is None:
        return False
    return bool(messagebox.askyesno(t(PERMISSION_DIALOG_TITLE), t(PERMISSION_DIALOG_TEXT), icon="warning"))


def _check_automation_permission() -> bool:
    """Check whether the Photos Automation permission has already been granted."""
    try:
        from icloudphotonator.photos_preflight import run_applescript

        success, _ = run_applescript('tell application "Photos" to get name')
        return success
    except Exception:
        return False


def _check_source_access(path: Path | str) -> bool:
    """Return True if *path* exists and is readable (os.access check)."""
    p = Path(path)
    return p.exists() and os.access(p, os.R_OK)


def _check_onboarding_done() -> bool:
    """Check whether the first-launch permission onboarding is already complete."""
    if not ONBOARDING_CONFIG_PATH.exists():
        return False

    try:
        config = json.loads(ONBOARDING_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return False

    return isinstance(config, dict) and bool(config.get("onboarding_done", False))


def _mark_onboarding_done() -> None:
    """Persist completion of the first-launch permission onboarding."""
    ONBOARDING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config: dict[str, object] = {}
    if ONBOARDING_CONFIG_PATH.exists():
        try:
            payload = json.loads(ONBOARDING_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            config = payload

    config["onboarding_done"] = True
    ONBOARDING_CONFIG_PATH.write_text(json.dumps(config), encoding="utf-8")


if ctk is None or tk is None or filedialog is None or messagebox is None:

    class StatsCard:
        """Placeholder when Tk support is unavailable."""

        def __init__(self, *args, **kwargs) -> None:
            _raise_missing_ui_support()


    class LogView:
        """Placeholder when Tk support is unavailable."""

        def __init__(self, *args, **kwargs) -> None:
            _raise_missing_ui_support()


    class ICloudPhotonatorApp:
        """Placeholder app that fails with a helpful runtime error."""

        def __init__(self, *args, **kwargs) -> None:
            _raise_missing_ui_support()

        def _show_onboarding(self) -> None:
            if not _check_onboarding_done():
                messagebox.showinfo(t(ONBOARDING_DIALOG_TITLE), t(ONBOARDING_DIALOG_TEXT))
                _mark_onboarding_done()

            while True:
                self.add_log(t("log.checking_automation"))
                if _check_automation_permission():
                    self.add_log(t("log.automation_granted"))
                    break

                self.add_log(t("log.automation_not_granted"))
                open_prefs = messagebox.askyesno(
                    t("dialog.permission_missing_title"),
                    t("dialog.permission_missing_message"),
                    icon="warning",
                )
                if not open_prefs:
                    self.add_log(t("log.automation_declined"))
                    break

                subprocess.Popen(
                    ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"],
                )
                messagebox.showinfo(
                    t("dialog.grant_permission_title"),
                    t("dialog.grant_permission_message"),
                )

        def _ensure_source_access_if_needed(self) -> None:
            """If the last incomplete job's source folder is inaccessible, prompt the user."""
            incomplete_jobs = [job for job in self._bridge.get_incomplete_jobs() if job.get("source_path")]
            if not incomplete_jobs:
                return
            source_path = incomplete_jobs[0].get("source_path", "")
            if not source_path or _check_source_access(source_path):
                return
            self.add_log(t("log.source_not_reachable", path=source_path))
            messagebox.showwarning(
                t("dialog.source_not_reachable_title"),
                t("dialog.source_not_reachable_message", path=source_path),
            )
            chosen = filedialog.askdirectory(title=t("dialog.source_rechosen_title"))
            if chosen:
                self.add_log(t("log.source_rechosen", path=chosen))

        def _run_startup_sequence(self) -> None:
            self._show_onboarding()
            self._ensure_source_access_if_needed()
            self._check_for_incomplete_jobs()


    def main() -> None:
        _raise_missing_ui_support()

else:


    class SettingsDialog(ctk.CTkToplevel):
        """Settings dialog for configuring import parameters."""

        _LANG_MAP = {"English": "en", "Deutsch": "de"}
        _LANG_REVERSE = {v: k for k, v in _LANG_MAP.items()}

        def __init__(self, master, settings: ImportSettings, on_save: "Callable[[ImportSettings], None] | None" = None):
            super().__init__(master)
            self.title(t("settings.title"))
            self.geometry("480x600")
            self.resizable(False, False)
            self.grab_set()
            self.configure(fg_color=BG_PRIMARY)
            self._settings = settings
            self._on_save = on_save
            self._vars: dict[str, tk.Variable] = {}
            self._build_ui()

        def _build_ui(self) -> None:
            container = ctk.CTkScrollableFrame(self, fg_color="transparent")
            container.pack(fill="both", expand=True, padx=16, pady=(12, 0))

            # Intro text
            ctk.CTkLabel(
                container, text=t("settings.intro"),
                font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY,
                wraplength=430, justify="left",
            ).pack(fill="x", pady=(0, 12))

            # --- Import Performance ---
            self._section_label(container, t("settings.performance"))
            card1 = self._card(container)
            self._spinbox_row(card1, "min_batch_size", t("settings.min_batch"), 1, 50, 1)
            self._spinbox_row(card1, "max_batch_size", t("settings.max_batch"), 5, 100, 5)
            self._spinbox_row(card1, "cooldown_seconds", t("settings.cooldown"), 5, 300, 5, t("settings.seconds"))
            self._spinbox_row(card1, "extended_cooldown_seconds", t("settings.extended_cooldown"), 30, 600, 30, t("settings.seconds"))
            self._spinbox_row(card1, "extended_cooldown_every", t("settings.extended_every"), 10, 500, 10, t("settings.imports"))

            # --- Photos Management ---
            self._section_label(container, t("settings.photos"))
            card2 = self._card(container)
            self._spinbox_row(card2, "restart_photos_every", t("settings.restart_every"), 100, 2000, 100, t("settings.imports"))
            self._spinbox_row(card2, "restart_wait_seconds", t("settings.restart_wait"), 30, 300, 30, t("settings.seconds"))

            # --- Storage ---
            self._section_label(container, t("settings.storage"))
            card3 = self._card(container)
            self._spinbox_row(card3, "max_staging_size_gb", t("settings.max_staging"), 1, 50, 1, t("settings.gb"), is_float=True)

            # --- Language ---
            self._section_label(container, t("settings.language"))
            card4 = self._card(container)
            lang_row = ctk.CTkFrame(card4, fg_color="transparent")
            lang_row.pack(fill="x", pady=4)
            lang_var = tk.StringVar(value=self._LANG_REVERSE.get(self._settings.locale, "English"))
            self._vars["locale"] = lang_var
            ctk.CTkLabel(lang_row, text=t("settings.language"), font=ctk.CTkFont(size=12), width=180, anchor="w").pack(side="left")
            ctk.CTkComboBox(lang_row, variable=lang_var, values=list(self._LANG_MAP.keys()), state="readonly", width=140).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                card4, text=t("settings.language_restart_hint"),
                font=ctk.CTkFont(size=10), text_color=TEXT_SECONDARY,
            ).pack(anchor="w", pady=(0, 4))

            # --- Buttons ---
            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=16, pady=12)
            ctk.CTkButton(
                btn_frame, text=t("settings.reset"), width=120, height=32, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=BORDER,
                text_color=TEXT_PRIMARY, hover_color=("#e8e8ed", "#3a3a3c"),
                command=self._on_reset,
            ).pack(side="left")
            ctk.CTkButton(
                btn_frame, text=t("settings.save"), width=80, height=32, corner_radius=8,
                fg_color=ACCENT_BLUE, hover_color="#005EC4",
                command=self._on_save_click,
            ).pack(side="right")
            ctk.CTkButton(
                btn_frame, text=t("settings.cancel"), width=80, height=32, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=BORDER,
                text_color=TEXT_PRIMARY, hover_color=("#e8e8ed", "#3a3a3c"),
                command=self.destroy,
            ).pack(side="right", padx=(0, 8))

        def _section_label(self, parent, text: str) -> None:
            ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(8, 4))

        def _card(self, parent) -> ctk.CTkFrame:
            card = ctk.CTkFrame(parent, corner_radius=10, border_width=1, border_color=BORDER, fg_color=BG_CARD)
            card.pack(fill="x", pady=(0, 4))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=12, pady=8)
            return inner

        def _spinbox_row(self, parent, key: str, label: str, from_: int, to: int, step: int, unit: str = "", is_float: bool = False) -> None:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12), width=180, anchor="w").pack(side="left")
            current = getattr(self._settings, key)
            if is_float:
                var = tk.DoubleVar(value=float(current))
            else:
                var = tk.IntVar(value=int(current))
            self._vars[key] = var

            spin = tk.Spinbox(
                row, from_=from_, to=to, increment=step,
                textvariable=var, width=8, justify="center",
                relief="flat", bd=1,
            )
            spin.pack(side="left", padx=(0, 6))
            if unit:
                ctk.CTkLabel(row, text=unit, font=ctk.CTkFont(size=11), text_color=TEXT_SECONDARY).pack(side="left")

        def _on_reset(self) -> None:
            defaults = ImportSettings()
            for key, var in self._vars.items():
                if key == "locale":
                    var.set(self._LANG_REVERSE.get(defaults.locale, "English"))
                else:
                    var.set(getattr(defaults, key))

        def _on_save_click(self) -> None:
            for key, var in self._vars.items():
                if key == "locale":
                    self._settings.locale = self._LANG_MAP.get(var.get(), "en")
                else:
                    setattr(self._settings, key, var.get())
            self._settings.save()
            if self._on_save:
                self._on_save(self._settings)
            self.destroy()


    class StatsCard(ctk.CTkFrame):
        """A single stat display card with a prominent number and label."""

        def __init__(self, master, label: str, **kwargs):
            super().__init__(
                master, corner_radius=10, border_width=1,
                border_color=BORDER, fg_color=BG_CARD, **kwargs,
            )
            self.value_label = ctk.CTkLabel(
                self, text="0", font=ctk.CTkFont(size=24, weight="bold"),
            )
            self.value_label.pack(pady=(14, 2))
            self.name_label = ctk.CTkLabel(
                self, text=label, font=ctk.CTkFont(size=11),
                text_color=TEXT_SECONDARY,
            )
            self.name_label.pack(pady=(0, 14))

        def set_value(self, value: int | str, highlight_color: str | None = None) -> None:
            self.value_label.configure(text=str(value))
            if highlight_color:
                self.value_label.configure(text_color=highlight_color)
            else:
                self.value_label.configure(text_color=TEXT_PRIMARY)


    class LogView(ctk.CTkTextbox):
        """Scrollable log viewer with auto-scroll and a monospace font."""

        def __init__(self, master, **kwargs):
            super().__init__(
                master,
                font=ctk.CTkFont(family="Menlo", size=11),
                fg_color="#111827",
                text_color="#f3f4f6",
                wrap="word",
                state="disabled",
                **kwargs,
            )

        def append(self, text: str) -> None:
            self.configure(state="normal")
            self.insert("end", text + "\n")
            self.see("end")
            self.configure(state="disabled")


    class ICloudPhotonatorApp(ctk.CTk):
        """Main desktop application window."""

        def __init__(self) -> None:
            ctk.set_appearance_mode("system")
            ctk.set_default_color_theme("blue")
            super().__init__()

            self.title(APP_TITLE)
            self.geometry("720x880")
            self.minsize(640, 720)
            self.configure(fg_color=BG_PRIMARY)

            self._source_path: Path | None = None
            self._is_running = False
            self._is_paused = False
            self._last_stats: dict[str, int] = {}
            self._last_error_count: int = 0
            self._last_job_id: str | None = None
            self.path_var = tk.StringVar(value=t("app.no_folder"))
            self.album_var = tk.StringVar(value="")
            self.library_var = tk.StringVar(value=t("app.default_library"))
            self._library_options: dict[str, Path | None] = {}
            self._settings = ImportSettings.load()
            self._bridge = BackendBridge()
            self._bridge.set_callbacks(
                on_progress=self._handle_progress,
                on_log=self.add_log,
                on_complete=self._handle_complete,
                on_error=self._handle_error,
                on_permission_error=self._handle_permission_error,
            )

            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self._build_ui()
            self._set_status(t("app.ready"))
            self.add_log(t("app.application_ready"))
            self.after(0, self._run_startup_sequence)

        def _run_startup_sequence(self) -> None:
            """Run startup checks in order: onboarding first, source access, resume checks last."""
            self._show_onboarding()
            self._ensure_source_access_if_needed()
            self._check_for_incomplete_jobs()

        def _ensure_source_access_if_needed(self) -> None:
            """If the last incomplete job's source folder is inaccessible, prompt the user."""
            incomplete_jobs = [job for job in self._bridge.get_incomplete_jobs() if job.get("source_path")]
            if not incomplete_jobs:
                return
            source_path = incomplete_jobs[0].get("source_path", "")
            if not source_path or _check_source_access(source_path):
                return
            self.add_log(t("log.source_not_reachable", path=source_path))
            messagebox.showwarning(
                t("dialog.source_not_reachable_title"),
                t("dialog.source_not_reachable_message", path=source_path),
            )
            chosen = filedialog.askdirectory(title=t("dialog.source_rechosen_title"))
            if chosen:
                self.add_log(t("log.source_rechosen", path=chosen))

        def _show_onboarding(self) -> None:
            """Check Automation permission on every launch; show intro only on first run."""
            if not _check_onboarding_done():
                messagebox.showinfo(t(ONBOARDING_DIALOG_TITLE), t(ONBOARDING_DIALOG_TEXT))
                _mark_onboarding_done()

            while True:
                self.add_log(t("log.checking_automation"))
                if _check_automation_permission():
                    self.add_log(t("log.automation_granted"))
                    break

                self.add_log(t("log.automation_not_granted"))
                open_prefs = messagebox.askyesno(
                    t("dialog.permission_missing_title"),
                    t("dialog.permission_missing_message"),
                    icon="warning",
                )
                if not open_prefs:
                    self.add_log(t("log.automation_declined"))
                    break

                subprocess.Popen(
                    ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"],
                )
                messagebox.showinfo(
                    t("dialog.grant_permission_title"),
                    t("dialog.grant_permission_message"),
                )

        def _build_ui(self) -> None:
            self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
            self.main_frame.pack(fill="both", expand=True, padx=24, pady=20)
            self._build_header()
            self._build_input_section()
            self._build_progress_section()
            self._build_stats_grid()
            self._build_controls()
            self._build_log_area()
            self._build_footer()

        def _build_header(self) -> None:
            header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 16))
            left = ctk.CTkFrame(header, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True)
            icon_row = ctk.CTkFrame(left, fg_color="transparent")
            icon_row.pack(anchor="w")
            icon_frame = ctk.CTkFrame(
                icon_row, width=32, height=32, corner_radius=16, fg_color=ACCENT_BLUE,
            )
            icon_frame.pack(side="left", padx=(0, 10))
            icon_frame.pack_propagate(False)
            ctk.CTkLabel(icon_frame, text="📸", font=ctk.CTkFont(size=14)).pack(expand=True)
            ctk.CTkLabel(
                icon_row, text=APP_TITLE, font=ctk.CTkFont(size=18, weight="bold"),
            ).pack(side="left")
            ctk.CTkLabel(
                icon_row, text="v0.3.0", font=ctk.CTkFont(size=11),
                text_color=TEXT_SECONDARY,
            ).pack(side="left", padx=(8, 0))
            self.settings_btn = ctk.CTkButton(
                header, text="⚙️", width=32, height=32, corner_radius=8,
                fg_color="transparent", hover_color=BORDER, command=self._open_settings,
            )
            self.settings_btn.pack(side="right")

        def _build_input_section(self) -> None:
            """Build the combined input section: source folder, album, library."""
            card = ctk.CTkFrame(
                self.main_frame, corner_radius=12, fg_color=BG_CARD,
                border_width=1, border_color=BORDER,
            )
            card.pack(fill="x", pady=(0, 16))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)

            # Source Folder row
            row1 = ctk.CTkFrame(inner, fg_color="transparent")
            row1.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(
                row1, text=t("app.source_folder"), font=ctk.CTkFont(size=13, weight="bold"),
                width=110, anchor="w",
            ).pack(side="left")
            self.path_entry = ctk.CTkEntry(row1, textvariable=self.path_var, state="disabled")
            self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.browse_btn = ctk.CTkButton(
                row1, text=t("app.browse"), width=80, height=28, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=ACCENT_BLUE,
                text_color=ACCENT_BLUE, hover_color=("#e8f0fe", "#1a3a5c"),
                command=self._browse_folder,
            )
            self.browse_btn.pack(side="right")

            # Import Album row
            row2 = ctk.CTkFrame(inner, fg_color="transparent")
            row2.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(
                row2, text=t("app.import_album"), font=ctk.CTkFont(size=13, weight="bold"),
                width=110, anchor="w",
            ).pack(side="left")
            self.album_entry = ctk.CTkEntry(
                row2, textvariable=self.album_var,
                placeholder_text=t("app.album_placeholder"),
            )
            self.album_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.album_auto_btn = ctk.CTkButton(
                row2, text=t("app.auto"), width=60, height=28, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=TEXT_SECONDARY,
                text_color=TEXT_SECONDARY, hover_color=("#e8e8ed", "#3a3a3c"),
                command=self._auto_fill_album,
            )
            self.album_auto_btn.pack(side="right")

            # Target Library row
            row3 = ctk.CTkFrame(inner, fg_color="transparent")
            row3.pack(fill="x")
            ctk.CTkLabel(
                row3, text=t("app.target_library"), font=ctk.CTkFont(size=13, weight="bold"),
                width=110, anchor="w",
            ).pack(side="left")
            self.library_combo = ctk.CTkComboBox(
                row3, variable=self.library_var,
                values=[t("app.default_library")], state="readonly",
            )
            self.library_combo.pack(side="left", fill="x", expand=True)
            self._refresh_library_options()

        def _refresh_library_options(self) -> None:
            options = build_library_options(find_photo_libraries())
            labels = list(options)
            current = self.library_var.get()
            self._library_options = options
            self.library_combo.configure(values=labels)
            self.library_var.set(current if current in options else t("app.default_library"))

        def _get_selected_library(self) -> Path | None:
            return self._library_options.get(self.library_var.get())

        def _build_progress_section(self) -> None:
            frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            frame.pack(fill="x", pady=(0, 16))
            self.percent_label = ctk.CTkLabel(
                frame, text="0%", font=ctk.CTkFont(size=48, weight="bold"),
            )
            self.percent_label.pack()
            self.status_label = ctk.CTkLabel(
                frame, text="", font=ctk.CTkFont(size=13), text_color=TEXT_SECONDARY,
            )
            self.status_label.pack(pady=(2, 8))
            self.progress_bar = ctk.CTkProgressBar(
                frame, height=4, corner_radius=2, mode="determinate",
            )
            self.progress_bar.pack(fill="x")
            self.progress_bar.set(0)

        def _build_stats_grid(self) -> None:
            frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            frame.pack(fill="x", pady=(0, 16))
            frame.grid_columnconfigure((0, 1, 2), weight=1)
            labels = [
                (t("stats.discovered"), "discovered"),
                (t("stats.imported"), "imported"),
                (t("stats.staged"), "staged"),
                (t("stats.duplicates"), "duplicates"),
                (t("stats.errors"), "errors"),
                (t("stats.remaining"), "remaining"),
            ]
            self.stat_cards: dict[str, StatsCard] = {}
            for index, (label, key) in enumerate(labels):
                card = StatsCard(frame, label)
                card.grid(row=index // 3, column=index % 3, padx=4, pady=4, sticky="ew")
                self.stat_cards[key] = card

        def _build_controls(self) -> None:
            # Restart Photos banner (hidden by default, shown above controls when needed)
            self.restart_photos_btn = ctk.CTkButton(
                self.main_frame, text=t("app.restart_photos"),
                height=36, corner_radius=8,
                fg_color=WARNING, hover_color="#E68600", text_color="#ffffff",
                command=self._on_restart_photos,
            )
            # Don't pack yet — shown via _handle_progress when needed
            ctrl_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            ctrl_frame.pack(fill="x", pady=(0, 16))
            ctrl_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
            self._controls_frame = ctrl_frame

            self.start_btn = ctk.CTkButton(
                ctrl_frame, text=t("app.start"), height=36, corner_radius=8,
                fg_color=SUCCESS, hover_color="#2DB84E",
                command=self._on_start, state="disabled",
            )
            self.start_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")
            self.pause_btn = ctk.CTkButton(
                ctrl_frame, text=t("app.pause"), height=36, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=WARNING,
                text_color=WARNING, hover_color=("#fff3e0", "#3a3020"),
                command=self._on_pause, state="disabled",
            )
            self.pause_btn.grid(row=0, column=1, padx=4, sticky="ew")
            self.stop_btn = ctk.CTkButton(
                ctrl_frame, text=t("app.stop"), height=36, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=ERROR,
                text_color=ERROR, hover_color=("#ffe8e6", "#3a2020"),
                command=self._on_stop, state="disabled",
            )
            self.stop_btn.grid(row=0, column=2, padx=4, sticky="ew")
            self.retry_btn = ctk.CTkButton(
                ctrl_frame, text=t("app.retry"), height=36, corner_radius=8,
                fg_color="transparent", border_width=1, border_color=ACCENT_BLUE,
                text_color=ACCENT_BLUE, hover_color=("#e8f0fe", "#1a3a5c"),
                command=self._on_retry_errors, state="disabled",
            )
            self.retry_btn.grid(row=0, column=3, padx=(4, 0), sticky="ew")

        def _build_log_area(self) -> None:
            header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(
                header, text=t("app.activity_log"), font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(side="left")
            self.log_view = LogView(self.main_frame, height=120, corner_radius=8)
            self.log_view.pack(fill="both", expand=True)

        def _build_footer(self) -> None:
            footer = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            footer.pack(fill="x", pady=(8, 0))
            ctk.CTkLabel(
                footer, text="v0.3.0", font=ctk.CTkFont(size=10),
                text_color=TEXT_SECONDARY,
            ).pack(side="left")
            ctk.CTkButton(
                footer, text="GitHub", font=ctk.CTkFont(size=11, underline=True),
                fg_color="transparent", hover=False, text_color=ACCENT_BLUE,
                width=20, command=lambda: webbrowser.open(REPOSITORY_URL),
            ).pack(side="right")

        def _browse_folder(self) -> None:
            path = filedialog.askdirectory(title=t("dialog.browse_title"))
            if not path:
                return
            self._source_path = Path(path)
            self._set_path_display(str(self._source_path))
            self._auto_fill_album()
            if not self._is_running:
                self.start_btn.configure(state="normal")
            self.add_log(t("log.source_folder_chosen", path=path))

        def _auto_fill_album(self) -> None:
            if self._source_path:
                self.album_var.set(self._source_path.name)

        def _on_start(self) -> None:
            if not self._source_path:
                return
            self._refresh_library_options()
            self._start_import_run()

        def _check_for_incomplete_jobs(self) -> None:
            incomplete_jobs = [job for job in self._bridge.get_incomplete_jobs() if job.get("source_path")]
            if not incomplete_jobs:
                return

            job = incomplete_jobs[0]
            stats = job.get("stats", {})
            source_path = str(job.get("source_path", ""))
            imported = stats.get("imported", 0)
            total = stats.get("total", 0)
            should_resume = messagebox.askyesno(
                t("dialog.resume_title"),
                t("dialog.resume_message", path=source_path, imported=imported, total=total),
                icon="question",
            )
            if not should_resume:
                error_count = stats.get("error", 0)
                if error_count > 0:
                    self._last_job_id = job["id"]
                    self._last_error_count = error_count
                    self._source_path = Path(source_path)
                    self._set_path_display(source_path)
                    self.retry_btn.configure(state="normal")
                return

            self._source_path = Path(source_path)
            self._set_path_display(source_path)
            self._auto_fill_album()
            self.add_log(t("log.resume_saved_import", path=source_path))
            self._start_import_run(job_id=job["id"])

        def _start_import_run(self, job_id: str | None = None) -> None:
            if not self._source_path:
                return
            self._is_running = True
            self._is_paused = False
            self._last_error_count = 0
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text=t("app.pause"))
            self.stop_btn.configure(state="normal")
            self.retry_btn.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.album_entry.configure(state="disabled")
            self.album_auto_btn.configure(state="disabled")
            self.library_combo.configure(state="disabled")
            self._set_status(t("progress.scanning"), indeterminate=True)
            if job_id:
                self._last_job_id = job_id
                self.add_log(t("log.import_resumed"))
                self._bridge.resume_import(job_id)
                return
            self.add_log(t("log.import_started"))
            library = self._get_selected_library()
            album = self.album_var.get().strip()
            if library is not None:
                self.add_log(t("log.target_library", library=library))
            if album:
                self.add_log(t("log.import_album", album=album))
            self._bridge.start_import(self._source_path, library=library, album=album)

        def _on_pause(self) -> None:
            if not self._is_running:
                return
            if self._is_paused:
                self._is_paused = False
                self.pause_btn.configure(text=t("app.pause"))
                self._set_status(t("progress.importing", imported="…", total="…"))
                self._bridge.resume()
                self.add_log(t("log.import_resumed_action"))
                return
            self._is_paused = True
            self.pause_btn.configure(text=t("app.resume"))
            self._set_status(t("progress.paused"))
            self._bridge.pause()
            self.add_log(t("log.import_paused"))

        def _on_stop(self) -> None:
            if not self._is_running:
                return
            self._bridge.stop()
            self._finish_run(t("progress.stopped"), t("log.import_stopped"))

        def _on_retry_errors(self) -> None:
            if self._is_running or not self._last_job_id:
                return
            error_count = self._last_error_count
            should_retry = messagebox.askyesno(
                t("dialog.resume_title"),
                t("dialog.retry_message", count=error_count),
                icon="question",
            )
            if not should_retry:
                return
            self.add_log(t("log.retry_reimporting", count=error_count))
            self._is_running = True
            self._is_paused = False
            self._last_error_count = 0
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text=t("app.pause"))
            self.stop_btn.configure(state="normal")
            self.retry_btn.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.album_entry.configure(state="disabled")
            self.album_auto_btn.configure(state="disabled")
            self.library_combo.configure(state="disabled")
            self._set_status(t("progress.importing", imported="…", total="…"), indeterminate=True)
            self._bridge.retry_errors(self._last_job_id)

        def _on_restart_photos(self) -> None:
            self.restart_photos_btn.pack_forget()
            self._is_paused = False
            self.pause_btn.configure(text=t("app.pause"))
            self._set_status(t("progress.restarting_photos"))
            self.add_log(t("log.photos_restarting"))
            self._bridge.restart_photos()

        def _handle_progress(self, payload: dict) -> None:
            if isinstance(payload, dict):
                self._last_error_count = payload.get("errors", self._last_error_count)
                if "job_id" in payload:
                    self._last_job_id = payload["job_id"]
                pause_reason = payload.get("pause_reason")
                if pause_reason == "photos_unresponsive":
                    self.after(0, lambda: self.restart_photos_btn.pack(fill="x", pady=(0, 8), before=self._controls_frame))
                elif pause_reason is None:
                    self.after(0, self.restart_photos_btn.pack_forget)
                self.update_stats(payload)

        def _handle_complete(self) -> None:
            self.after(0, lambda: self._finish_run(t("progress.complete"), t("log.import_complete"), completed=True))

        def _handle_error(self, message: str) -> None:
            self.after(0, lambda: self._finish_run(t("progress.error"), t("log.error_prefix", message=message)))

        def _handle_permission_error(self) -> None:
            def _show_dialog() -> None:
                if self._is_running:
                    self._bridge.stop()
                self._finish_run(
                    t("progress.permission_required"),
                    t("log.import_permission_stopped"),
                )
                if _prompt_for_automation_permission():
                    _open_automation_settings()

            self.after(0, _show_dialog)

        def _finish_run(self, status_text: str, log_message: str, completed: bool = False) -> None:
            self._is_running = False
            self._is_paused = False
            self.start_btn.configure(state="normal" if self._source_path else "disabled")
            self.pause_btn.configure(state="disabled", text=t("app.pause"))
            self.stop_btn.configure(state="disabled")
            self.retry_btn.configure(state="normal" if self._last_error_count > 0 else "disabled")
            self.restart_photos_btn.pack_forget()
            self.browse_btn.configure(state="normal")
            self.album_entry.configure(state="normal")
            self.album_auto_btn.configure(state="normal")
            self.library_combo.configure(state="readonly")
            self._set_status(status_text)
            if completed:
                self.progress_bar.set(1)
                self.percent_label.configure(text="100%")
            self.add_log(log_message)

        def _set_path_display(self, text: str) -> None:
            self.path_entry.configure(state="normal")
            self.path_var.set(text)
            self.path_entry.configure(state="disabled")

        def _set_status(self, text: str, indeterminate: bool = False) -> None:
            self.status_label.configure(text=text)
            if indeterminate:
                self.progress_bar.configure(mode="indeterminate")
                self.progress_bar.start()
                return
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")

        def update_stats(self, stats: dict[str, int]) -> None:
            def _update() -> None:
                self._last_stats.update(stats)
                state = self._last_stats.get("state")
                staged_current = self._last_stats.get("staged", 0)
                staged_total = self._last_stats.get("staged_total", 0)
                values = {
                    "discovered": self._last_stats.get("discovered", self._last_stats.get("total", 0)),
                    "imported": self._last_stats.get("imported", 0),
                    "staged": f"{staged_current} (∑ {staged_total:,})".replace(",", ".") if staged_total > 0 else str(staged_current),
                    "duplicates": self._last_stats.get("duplicates", 0),
                    "errors": self._last_stats.get("errors", 0),
                }
                values["remaining"] = self._last_stats.get(
                    "remaining",
                    max(int(values["discovered"]) - (int(values["imported"]) + int(values["duplicates"]) + int(values["errors"])), 0),
                )
                done = max(int(values["discovered"]) - int(values["remaining"]), 0)
                total = values["discovered"]

                # Update stat cards with error highlighting
                for key, value in values.items():
                    if key == "errors" and int(values["errors"]) > 0:
                        self.stat_cards[key].set_value(value, highlight_color=ERROR)
                    else:
                        self.stat_cards[key].set_value(value)

                # Update percentage display
                if isinstance(total, int) and total > 0:
                    pct = min(int(done / total * 100), 100)
                    self.percent_label.configure(text=f"{pct}%")

                # Update status text
                if state == "scanning":
                    self._set_status(t("progress.scanning"), indeterminate=True)
                elif state == "deduplicating":
                    self._set_status(t("progress.deduplicating"))
                elif state == "staging":
                    self._set_status(t("progress.staging"))
                elif self._is_running and not self._is_paused and isinstance(total, int) and total > 0:
                    imported_count = int(values["imported"])
                    self.status_label.configure(
                        text=t("progress.importing", imported=f"{imported_count:,}", total=f"{total:,}"),
                    )
                    self.progress_bar.stop()
                    self.progress_bar.configure(mode="determinate")

                if isinstance(total, int) and total > 0 and state != "scanning":
                    self.progress_bar.set(min(done / total, 1))

            self.after(0, _update)

        def add_log(self, message: str) -> None:
            self.after(0, lambda: self.log_view.append(message))

        def _open_settings(self) -> None:
            SettingsDialog(self, self._settings, on_save=self._apply_settings)

        def _apply_settings(self, settings: ImportSettings) -> None:
            self._settings = settings
            load_locale(settings.locale)

        def _on_close(self) -> None:
            if self._is_running:
                self._bridge.stop()
            self.destroy()


    def main() -> None:
        app = ICloudPhotonatorApp()
        app.mainloop()
