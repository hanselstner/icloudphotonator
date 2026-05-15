"""Modal dialog shown when the app is launched from a DMG or translocation path."""

from __future__ import annotations

import subprocess
import sys
from typing import Callable, Optional

try:
    import customtkinter as ctk
except ModuleNotFoundError:
    ctk = None

from icloudphotonator.i18n import t
from icloudphotonator.launch_environment import (
    KIND_DMG,
    KIND_TRANSLOCATION,
    LaunchEnvironment,
)

ACTION_MOVE = "move"
ACTION_CONTINUE = "continue"
ACTION_QUIT = "quit"

_ACCENT_BLUE = "#007AFF"
_WARNING = "#FF9500"
_BG_PRIMARY = ("#f5f5f7", "#1c1c1e")
_TEXT_SECONDARY = ("#8e8e93", "#8e8e93")


def _open_applications_folder() -> None:
    """Open Finder at /Applications so the user can drag the app there."""
    subprocess.run(["open", "/Applications"], check=False)


def default_on_move() -> None:
    """Default Move handler: reveal /Applications then quit the app."""
    _open_applications_folder()
    sys.exit(0)


def default_on_quit() -> None:
    """Default Quit handler: terminate the process."""
    sys.exit(0)


if ctk is None:

    class DmgLaunchDialog:  # type: ignore[no-redef]
        """Placeholder when Tk support is unavailable."""

        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - import guard
            raise RuntimeError(
                "Tkinter support is not available in this Python environment."
            )

else:

    class DmgLaunchDialog(ctk.CTkToplevel):  # type: ignore[no-redef]
        """Modal dialog warning that the app runs from a non-installed location."""

        _SIZE = (520, 340)

        def __init__(
            self,
            master,
            environment: LaunchEnvironment,
            on_move: Optional[Callable[[], None]] = None,
            on_continue: Optional[Callable[[], None]] = None,
            on_quit: Optional[Callable[[], None]] = None,
        ) -> None:
            super().__init__(master)
            self._environment = environment
            self._on_move = on_move or default_on_move
            self._on_continue = on_continue or (lambda: None)
            self._on_quit = on_quit or default_on_quit
            self.chosen_action: Optional[str] = None

            self.title(t("dmg_launch.title"))
            self.resizable(False, False)
            self.grab_set()
            self.configure(fg_color=_BG_PRIMARY)
            self._build_ui()
            self.protocol("WM_DELETE_WINDOW", self._handle_quit)
            self.update_idletasks()
            self.geometry(f"{self._SIZE[0]}x{self._SIZE[1]}")

        def _build_ui(self) -> None:
            ctk.CTkLabel(
                self, text=t("dmg_launch.title"),
                font=ctk.CTkFont(size=18, weight="bold"),
                wraplength=460, justify="center",
            ).pack(padx=24, pady=(20, 8))

            ctk.CTkLabel(
                self, text=t("dmg_launch.message"),
                font=ctk.CTkFont(size=12), text_color=_TEXT_SECONDARY,
                wraplength=460, justify="center",
            ).pack(padx=24, pady=(0, 8))

            if self._environment.kind == KIND_TRANSLOCATION:
                ctk.CTkLabel(
                    self, text=t("dmg_launch.translocation_hint"),
                    font=ctk.CTkFont(size=11), text_color=_WARNING,
                    wraplength=460, justify="center",
                ).pack(padx=24, pady=(0, 4))

            ctk.CTkLabel(
                self, text=self._environment.path or "—",
                font=ctk.CTkFont(family="Menlo", size=10),
                text_color=_TEXT_SECONDARY,
                wraplength=460, justify="center",
            ).pack(padx=24, pady=(0, 16))

            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(padx=24, pady=(0, 20))
            ctk.CTkButton(
                btn_frame, text=t("dmg_launch.move_btn"),
                width=180, height=32, corner_radius=8,
                fg_color=_ACCENT_BLUE, hover_color="#005EC4",
                command=self._handle_move,
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btn_frame, text=t("dmg_launch.continue_btn"),
                width=140, height=32, corner_radius=8,
                fg_color="transparent", border_width=1,
                border_color=_ACCENT_BLUE, text_color=_ACCENT_BLUE,
                hover_color=("#e8f0fe", "#1a3a5c"),
                command=self._handle_continue,
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btn_frame, text=t("dmg_launch.quit_btn"),
                width=100, height=32, corner_radius=8,
                fg_color=_WARNING, hover_color="#E68600", text_color="#ffffff",
                command=self._handle_quit,
            ).pack(side="left", padx=4)

        def _handle_move(self) -> None:
            self.chosen_action = ACTION_MOVE
            self.destroy()
            self._on_move()

        def _handle_continue(self) -> None:
            self.chosen_action = ACTION_CONTINUE
            self.destroy()
            self._on_continue()

        def _handle_quit(self) -> None:
            self.chosen_action = ACTION_QUIT
            self.destroy()
            self._on_quit()
