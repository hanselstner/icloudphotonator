"""Detect risky launch locations (DMG, App Translocation) before startup.

The Apple TCC subsystem ties permissions to the resolved app bundle path. When
the app runs from a mounted DMG (``/Volumes/...``) or from macOS's App
Translocation quarantine (``/private/var/folders/.../AppTranslocation/...``) the
path changes between launches, so granted Full Disk Access / Automation
permissions silently stop applying. This module exposes a small pure function
the UI uses to detect those situations at startup.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

KIND_OK = "ok"
KIND_DMG = "dmg"
KIND_TRANSLOCATION = "translocation"


@dataclass(frozen=True)
class LaunchEnvironment:
    """Structured result of :func:`detect_launch_environment`."""

    kind: str
    path: str

    @property
    def is_risky(self) -> bool:
        """True when the launch location is known to break TCC."""
        return self.kind in (KIND_DMG, KIND_TRANSLOCATION)


def _candidate_path() -> str:
    """Return the best path that represents where the app is currently running."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return str(meipass)
    executable = sys.executable
    return str(executable) if executable else ""


def detect_launch_environment(path: str | None = None) -> LaunchEnvironment:
    """Classify the runtime location of the app.

    Pass *path* explicitly for tests. With ``path=None`` the function inspects
    :pydata:`sys._MEIPASS` (PyInstaller bundle extraction path) and falls back
    to :pydata:`sys.executable`.
    """
    resolved = path if path is not None else _candidate_path()
    if not resolved:
        return LaunchEnvironment(kind=KIND_OK, path="")

    if "/AppTranslocation/" in resolved:
        return LaunchEnvironment(kind=KIND_TRANSLOCATION, path=resolved)
    if resolved.startswith("/Volumes/"):
        return LaunchEnvironment(kind=KIND_DMG, path=resolved)
    return LaunchEnvironment(kind=KIND_OK, path=resolved)
