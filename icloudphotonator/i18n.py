"""Simple i18n module for iCloudPhotonator."""
import json
import sys
from pathlib import Path

_current_locale = "en"
_translations: dict[str, dict[str, str]] = {}


def _get_locales_dir() -> Path:
    """Get locales directory, works both in dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # Running in dev
        base = Path(__file__).parent
    return base / "locales"


_locales_dir = _get_locales_dir()


def load_locale(locale: str) -> None:
    global _current_locale
    if locale not in _translations:
        path = _locales_dir / f"{locale}.json"
        if path.exists():
            _translations[locale] = json.loads(path.read_text("utf-8"))
    _current_locale = locale


def t(key: str, **kwargs) -> str:
    """Translate a key. Falls back to English, then to the key itself."""
    text = _translations.get(_current_locale, {}).get(key)
    if text is None:
        text = _translations.get("en", {}).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


def get_locale() -> str:
    return _current_locale


def available_locales() -> list[str]:
    return [p.stem for p in _locales_dir.glob("*.json")]


# Load English by default
load_locale("en")

