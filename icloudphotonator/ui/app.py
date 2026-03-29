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

from icloudphotonator.importer import find_photo_libraries
from icloudphotonator.persistence import APP_DIR

from .bridge import BackendBridge

APP_TITLE = "iCloudPhotonator"
APP_SUBTITLE = "Foto-Migration für Apple Fotos"
REPOSITORY_URL = "https://github.com/hanselstner/icloudphototnator"
ACCENT_BLUE = "#007AFF"
DEFAULT_LIBRARY_OPTION = "Standard (Systemmediathek)"
AUTOMATION_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"
PERMISSION_DIALOG_TITLE = "Berechtigung erforderlich"
PERMISSION_DIALOG_TEXT = (
    "iCloudPhotonator benötigt die Automation-Berechtigung, um Medien an Fotos.app zu senden.\n\n"
    "Bitte erlaube der App unter Systemeinstellungen → Datenschutz & Sicherheit → Automation den Zugriff auf Fotos.app.\n\n"
    "Möchtest du die Systemeinstellungen jetzt öffnen?"
)
ONBOARDING_CONFIG_PATH = APP_DIR / "config.json"
ONBOARDING_DIALOG_TITLE = "Willkommen bei iCloudPhotonator"
ONBOARDING_DIALOG_TEXT = (
    "Für den Import Ihrer Fotos benötigt iCloudPhotonator folgende Berechtigungen:\n\n"
    "1️⃣  Automation (Fotos-App)\n"
    "     Erlaubt der App, Fotos in die Fotos-App zu importieren.\n\n"
    "2️⃣  Fotomediathek\n"
    "     Erlaubt der App, auf Ihre Fotomediathek zuzugreifen.\n\n"
    "macOS wird Sie gleich nach diesen Berechtigungen fragen.\n"
    "Bitte bestätigen Sie jeweils mit „OK“."
)


def build_library_options(libraries: list[Path]) -> dict[str, Path | None]:
    """Build display labels for selectable Photos libraries."""
    options: dict[str, Path | None] = {DEFAULT_LIBRARY_OPTION: None}
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
    return bool(messagebox.askyesno(PERMISSION_DIALOG_TITLE, PERMISSION_DIALOG_TEXT, icon="warning"))


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
                messagebox.showinfo(ONBOARDING_DIALOG_TITLE, ONBOARDING_DIALOG_TEXT)
                _mark_onboarding_done()

            while True:
                self.add_log("Prüfe Automation-Berechtigung...")
                if _check_automation_permission():
                    self.add_log("✅ Automation-Berechtigung erteilt.")
                    break

                self.add_log("⚠️ Automation-Berechtigung nicht erteilt.")
                open_prefs = messagebox.askyesno(
                    "Berechtigung fehlt",
                    "iCloudPhotonator benötigt die Automation-Berechtigung für Fotos.\n\n"
                    "Möchten Sie die Systemeinstellungen öffnen, um die Berechtigung zu erteilen?",
                    icon="warning",
                )
                if not open_prefs:
                    self.add_log("⚠️ Automation-Berechtigung abgelehnt — Funktionen eingeschränkt.")
                    break

                subprocess.Popen(
                    ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"],
                )
                messagebox.showinfo(
                    "Berechtigung erteilen",
                    "Bitte erteilen Sie die Berechtigung in den Systemeinstellungen.\n\n"
                    "Klicken Sie OK, wenn Sie fertig sind.",
                )

        def _ensure_source_access_if_needed(self) -> None:
            """If the last incomplete job's source folder is inaccessible, prompt the user."""
            incomplete_jobs = [job for job in self._bridge.get_incomplete_jobs() if job.get("source_path")]
            if not incomplete_jobs:
                return
            source_path = incomplete_jobs[0].get("source_path", "")
            if not source_path or _check_source_access(source_path):
                return
            self.add_log(f"⚠️ Quellordner nicht erreichbar: {source_path}")
            messagebox.showwarning(
                "Quellordner nicht erreichbar",
                (
                    f"Der Quellordner des letzten Imports ist nicht erreichbar:\n{source_path}\n\n"
                    "Bitte wählen Sie den Ordner erneut aus, damit macOS die Zugriffsberechtigung erteilt."
                ),
            )
            chosen = filedialog.askdirectory(title="Quellordner erneut auswählen")
            if chosen:
                self.add_log(f"Quellordner neu gewählt: {chosen}")

        def _run_startup_sequence(self) -> None:
            self._show_onboarding()
            self._ensure_source_access_if_needed()
            self._check_for_incomplete_jobs()


    def main() -> None:
        _raise_missing_ui_support()

else:


    class StatsCard(ctk.CTkFrame):
        """A single stat display card with a prominent number and label."""

        def __init__(self, master, label: str, **kwargs):
            super().__init__(master, corner_radius=16, border_width=1, border_color=("#d1d5db", "#374151"), **kwargs)
            self.value_label = ctk.CTkLabel(self, text="0", font=ctk.CTkFont(size=28, weight="bold"))
            self.value_label.pack(pady=(12, 2))
            self.name_label = ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=12), text_color=("#4b5563", "#9ca3af"))
            self.name_label.pack(pady=(0, 12))

        def set_value(self, value: int | str) -> None:
            self.value_label.configure(text=str(value))


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
            self.geometry("700x850")
            self.minsize(600, 700)

            self._source_path: Path | None = None
            self._is_running = False
            self._is_paused = False
            self._last_stats: dict[str, int] = {}
            self._last_error_count: int = 0
            self._last_job_id: str | None = None
            self.path_var = tk.StringVar(value="Noch kein Ordner ausgewählt")
            self.album_var = tk.StringVar(value="")
            self.library_var = tk.StringVar(value=DEFAULT_LIBRARY_OPTION)
            self._library_options: dict[str, Path | None] = {}
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
            self._set_status("⏸ Bereit")
            self.add_log("Anwendung bereit.")
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
            self.add_log(f"⚠️ Quellordner nicht erreichbar: {source_path}")
            messagebox.showwarning(
                "Quellordner nicht erreichbar",
                (
                    f"Der Quellordner des letzten Imports ist nicht erreichbar:\n{source_path}\n\n"
                    "Bitte wählen Sie den Ordner erneut aus, damit macOS die Zugriffsberechtigung erteilt."
                ),
            )
            chosen = filedialog.askdirectory(title="Quellordner erneut auswählen")
            if chosen:
                self.add_log(f"Quellordner neu gewählt: {chosen}")

        def _show_onboarding(self) -> None:
            """Check Automation permission on every launch; show intro only on first run."""
            if not _check_onboarding_done():
                messagebox.showinfo(ONBOARDING_DIALOG_TITLE, ONBOARDING_DIALOG_TEXT)
                _mark_onboarding_done()

            while True:
                self.add_log("Prüfe Automation-Berechtigung...")
                if _check_automation_permission():
                    self.add_log("✅ Automation-Berechtigung erteilt.")
                    break

                self.add_log("⚠️ Automation-Berechtigung nicht erteilt.")
                open_prefs = messagebox.askyesno(
                    "Berechtigung fehlt",
                    "iCloudPhotonator benötigt die Automation-Berechtigung für Fotos.\n\n"
                    "Möchten Sie die Systemeinstellungen öffnen, um die Berechtigung zu erteilen?",
                    icon="warning",
                )
                if not open_prefs:
                    self.add_log("⚠️ Automation-Berechtigung abgelehnt — Funktionen eingeschränkt.")
                    break

                subprocess.Popen(
                    ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation"],
                )
                messagebox.showinfo(
                    "Berechtigung erteilen",
                    "Bitte erteilen Sie die Berechtigung in den Systemeinstellungen.\n\n"
                    "Klicken Sie OK, wenn Sie fertig sind.",
                )

        def _build_ui(self) -> None:
            self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
            self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            self._build_header()
            self._build_input_section()
            self._build_status_section()
            self._build_stats_grid()
            self._build_controls()
            self._build_log_area()
            self._build_footer()

        def _build_header(self) -> None:
            header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 6))
            icon_frame = ctk.CTkFrame(header, width=40, height=40, corner_radius=12, fg_color=ACCENT_BLUE)
            icon_frame.pack(side="left", padx=(0, 12))
            icon_frame.pack_propagate(False)
            ctk.CTkLabel(icon_frame, text="🖼️", font=ctk.CTkFont(size=18)).pack(expand=True)
            text_frame = ctk.CTkFrame(header, fg_color="transparent")
            text_frame.pack(side="left", fill="x")
            ctk.CTkLabel(text_frame, text=APP_TITLE, font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w")
            ctk.CTkLabel(text_frame, text=APP_SUBTITLE, font=ctk.CTkFont(size=11), text_color=("#4b5563", "#9ca3af")).pack(anchor="w")

        def _build_input_section(self) -> None:
            """Build the combined input section: source folder, album, library."""
            frame = ctk.CTkFrame(self.main_frame)
            frame.pack(fill="x", pady=(0, 10))
            inner = ctk.CTkFrame(frame, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=12)

            ctk.CTkLabel(inner, text="Quellordner", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            row1 = ctk.CTkFrame(inner, fg_color="transparent")
            row1.pack(fill="x", pady=(4, 8))
            self.path_entry = ctk.CTkEntry(row1, textvariable=self.path_var, state="disabled")
            self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.browse_btn = ctk.CTkButton(
                row1,
                text="Ordner wählen…",
                width=130,
                fg_color=ACCENT_BLUE,
                hover_color="#0062cc",
                command=self._browse_folder,
            )
            self.browse_btn.pack(side="right")

            ctk.CTkLabel(inner, text="Import-Album", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            row2 = ctk.CTkFrame(inner, fg_color="transparent")
            row2.pack(fill="x", pady=(4, 8))
            self.album_entry = ctk.CTkEntry(
                row2,
                textvariable=self.album_var,
                placeholder_text="Album-Name (leer = kein Album)",
            )
            self.album_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.album_auto_btn = ctk.CTkButton(
                row2,
                text="↻ Auto",
                width=70,
                fg_color="#6c757d",
                hover_color="#5a6268",
                command=self._auto_fill_album,
            )
            self.album_auto_btn.pack(side="right")

            ctk.CTkLabel(inner, text="Ziel-Mediathek", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
            self.library_combo = ctk.CTkComboBox(
                inner,
                variable=self.library_var,
                values=[DEFAULT_LIBRARY_OPTION],
                state="readonly",
            )
            self.library_combo.pack(fill="x", pady=(4, 0))
            self._refresh_library_options()

        def _refresh_library_options(self) -> None:
            options = build_library_options(find_photo_libraries())
            labels = list(options)
            current = self.library_var.get()
            self._library_options = options
            self.library_combo.configure(values=labels)
            self.library_var.set(current if current in options else DEFAULT_LIBRARY_OPTION)

        def _get_selected_library(self) -> Path | None:
            return self._library_options.get(self.library_var.get())

        def _build_status_section(self) -> None:
            frame = ctk.CTkFrame(self.main_frame)
            frame.pack(fill="x", pady=(0, 8))
            inner = ctk.CTkFrame(frame, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)
            self.status_label = ctk.CTkLabel(inner, text="", font=ctk.CTkFont(size=15, weight="bold"))
            self.status_label.pack(anchor="w")
            self.progress_bar = ctk.CTkProgressBar(inner, mode="determinate")
            self.progress_bar.pack(fill="x", pady=(10, 0))
            self.progress_bar.set(0)

        def _build_stats_grid(self) -> None:
            frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            frame.pack(fill="x", pady=(0, 8))
            frame.grid_columnconfigure((0, 1, 2), weight=1)
            labels = ["Entdeckt", "Importiert", "Übersprungen", "Duplikate", "Fehler", "Verbleibend"]
            self.stat_cards: dict[str, StatsCard] = {}
            for index, label in enumerate(labels):
                key = label.lower().replace("ü", "ue")
                card = StatsCard(frame, label)
                card.grid(row=index // 3, column=index % 3, padx=4, pady=4, sticky="ew")
                self.stat_cards[key] = card

        def _build_controls(self) -> None:
            frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            frame.pack(fill="x", pady=(0, 6))
            self.start_btn = ctk.CTkButton(frame, text="▶ Start", fg_color="#28a745", hover_color="#218838", command=self._on_start, state="disabled")
            self.start_btn.pack(side="left", padx=(0, 6), expand=True, fill="x")
            self.pause_btn = ctk.CTkButton(frame, text="⏸ Pause", fg_color="#ffc107", hover_color="#e0a800", text_color="black", command=self._on_pause, state="disabled")
            self.pause_btn.pack(side="left", padx=6, expand=True, fill="x")
            self.stop_btn = ctk.CTkButton(frame, text="⏹ Stop", fg_color="#dc3545", hover_color="#c82333", command=self._on_stop, state="disabled")
            self.stop_btn.pack(side="left", padx=6, expand=True, fill="x")
            self.retry_btn = ctk.CTkButton(frame, text="🔄 Retry Fehler", fg_color="#6f42c1", hover_color="#5a32a3", command=self._on_retry_errors, state="disabled")
            self.retry_btn.pack(side="left", padx=(6, 0), expand=True, fill="x")

        def _build_log_area(self) -> None:
            ctk.CTkLabel(self.main_frame, text="Log", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 6))
            self.log_view = LogView(self.main_frame, height=150)
            self.log_view.pack(fill="both", expand=True)

        def _build_footer(self) -> None:
            footer = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            footer.pack(fill="x", pady=(8, 0))
            ctk.CTkLabel(footer, text="iCloudPhotonator v0.1.0", font=ctk.CTkFont(size=11), text_color=("#6b7280", "#9ca3af")).pack(side="left")
            ctk.CTkButton(footer, text="Projektseite öffnen", font=ctk.CTkFont(size=11, underline=True), fg_color="transparent", hover=False, text_color=ACCENT_BLUE, width=20, command=lambda: webbrowser.open(REPOSITORY_URL)).pack(side="right")

        def _browse_folder(self) -> None:
            path = filedialog.askdirectory(title="Quellordner auswählen")
            if not path:
                return
            self._source_path = Path(path)
            self._set_path_display(str(self._source_path))
            self._auto_fill_album()
            if not self._is_running:
                self.start_btn.configure(state="normal")
            self.add_log(f"Quellordner gewählt: {path}")

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
            source_path = str(job.get("source_path", "Unbekannter Ordner"))
            imported = stats.get("imported", 0)
            total = stats.get("total", 0)
            should_resume = messagebox.askyesno(
                APP_TITLE,
                (
                    f"Unvollständiger Import gefunden:\n{source_path}\n\n"
                    f"Fortschritt: {imported}/{total} Dateien importiert.\n\n"
                    "Möchtest du den Import fortsetzen?"
                ),
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
            self.add_log(f"Setze gespeicherten Import fort: {source_path}")
            self._start_import_run(job_id=job["id"])

        def _start_import_run(self, job_id: str | None = None) -> None:
            if not self._source_path:
                return
            self._is_running = True
            self._is_paused = False
            self._last_error_count = 0
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text="⏸ Pause")
            self.stop_btn.configure(state="normal")
            self.retry_btn.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.album_entry.configure(state="disabled")
            self.album_auto_btn.configure(state="disabled")
            self.library_combo.configure(state="disabled")
            self._set_status("🔄 Scanne...", indeterminate=True)
            if job_id:
                self._last_job_id = job_id
                self.add_log("Import wird fortgesetzt...")
                self._bridge.resume_import(job_id)
                return
            self.add_log("Import gestartet...")
            library = self._get_selected_library()
            album = self.album_var.get().strip()
            if library is not None:
                self.add_log(f"Ziel-Mediathek: {library}")
            if album:
                self.add_log(f"Import-Album: {album}")
            self._bridge.start_import(self._source_path, library=library, album=album)

        def _on_pause(self) -> None:
            if not self._is_running:
                return
            if self._is_paused:
                self._is_paused = False
                self.pause_btn.configure(text="⏸ Pause")
                self._set_status("🔄 Importiere...")
                self._bridge.resume()
                self.add_log("Import fortgesetzt.")
                return
            self._is_paused = True
            self.pause_btn.configure(text="▶ Fortsetzen")
            self._set_status("⏸ Pausiert")
            self._bridge.pause()
            self.add_log("Import pausiert.")

        def _on_stop(self) -> None:
            if not self._is_running:
                return
            self._bridge.stop()
            self._finish_run("⏹ Gestoppt", "Import gestoppt.")

        def _on_retry_errors(self) -> None:
            if self._is_running or not self._last_job_id:
                return
            error_count = self._last_error_count
            should_retry = messagebox.askyesno(
                APP_TITLE,
                (
                    f"{error_count} Dateien mit Fehlern gefunden.\n\n"
                    "Möchtest du diese Dateien erneut importieren?"
                ),
                icon="question",
            )
            if not should_retry:
                return
            self.add_log(f"Retry: {error_count} fehlerhafte Dateien werden erneut importiert...")
            self._is_running = True
            self._is_paused = False
            self._last_error_count = 0
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal", text="⏸ Pause")
            self.stop_btn.configure(state="normal")
            self.retry_btn.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.album_entry.configure(state="disabled")
            self.album_auto_btn.configure(state="disabled")
            self.library_combo.configure(state="disabled")
            self._set_status("🔄 Importiere...", indeterminate=True)
            self._bridge.retry_errors(self._last_job_id)

        def _handle_progress(self, payload: dict) -> None:
            if isinstance(payload, dict):
                self._last_error_count = payload.get("errors", self._last_error_count)
                if "job_id" in payload:
                    self._last_job_id = payload["job_id"]
                self.update_stats(payload)

        def _handle_complete(self) -> None:
            self.after(0, lambda: self._finish_run("✅ Fertig", "Import abgeschlossen.", completed=True))

        def _handle_error(self, message: str) -> None:
            self.after(0, lambda: self._finish_run("⚠️ Fehler", f"Fehler: {message}"))

        def _handle_permission_error(self) -> None:
            def _show_dialog() -> None:
                if self._is_running:
                    self._bridge.stop()
                self._finish_run(
                    "⚠️ Berechtigung erforderlich",
                    "Import wegen fehlender Automation-Berechtigung gestoppt.",
                )
                if _prompt_for_automation_permission():
                    _open_automation_settings()

            self.after(0, _show_dialog)

        def _finish_run(self, status_text: str, log_message: str, completed: bool = False) -> None:
            self._is_running = False
            self._is_paused = False
            self.start_btn.configure(state="normal" if self._source_path else "disabled")
            self.pause_btn.configure(state="disabled", text="⏸ Pause")
            self.stop_btn.configure(state="disabled")
            self.retry_btn.configure(state="normal" if self._last_error_count > 0 else "disabled")
            self.browse_btn.configure(state="normal")
            self.album_entry.configure(state="normal")
            self.album_auto_btn.configure(state="normal")
            self.library_combo.configure(state="readonly")
            self._set_status(status_text)
            if completed:
                self.progress_bar.set(1)
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
                values = {
                    "entdeckt": self._last_stats.get("discovered", self._last_stats.get("total", 0)),
                    "importiert": self._last_stats.get("imported", 0),
                    "uebersprungen": self._last_stats.get("skipped", 0),
                    "duplikate": self._last_stats.get("duplicates", 0),
                    "fehler": self._last_stats.get("errors", 0),
                }
                values["verbleibend"] = self._last_stats.get(
                    "remaining",
                    max(values["entdeckt"] - (values["importiert"] + values["uebersprungen"] + values["duplikate"] + values["fehler"]), 0),
                )
                done = max(values["entdeckt"] - values["verbleibend"], 0)
                for key, value in values.items():
                    self.stat_cards[key].set_value(value)
                total = values["entdeckt"]
                if state == "scanning":
                    self._set_status("🔄 Scanne...", indeterminate=True)
                elif state == "deduplicating":
                    self._set_status("🔄 Prüfe Duplikate...")
                elif state == "staging":
                    self._set_status("🔄 Stage Dateien...")
                elif self._is_running and not self._is_paused and total > 0:
                    self._set_status("🔄 Importiere...")

                if total > 0 and state != "scanning":
                    self.progress_bar.set(min(done / total, 1))

            self.after(0, _update)

        def add_log(self, message: str) -> None:
            self.after(0, lambda: self.log_view.append(message))

        def _on_close(self) -> None:
            if self._is_running:
                self._bridge.stop()
            self.destroy()


    def main() -> None:
        app = ICloudPhotonatorApp()
        app.mainloop()
