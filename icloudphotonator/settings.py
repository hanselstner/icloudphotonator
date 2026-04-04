"""Persistent settings for iCloudPhotonator."""
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict

SETTINGS_PATH = Path.home() / ".icloudphotonator" / "settings.json"


@dataclass
class ImportSettings:
    # Batch
    min_batch_size: int = 5
    max_batch_size: int = 20
    # Cooldown
    cooldown_seconds: int = 60
    extended_cooldown_seconds: int = 180
    extended_cooldown_every: int = 50
    # Photos restart
    restart_photos_every: int = 500
    restart_wait_seconds: int = 120
    # Staging
    max_staging_size_gb: float = 10.0
    # Language
    locale: str = "en"

    def save(self) -> None:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> "ImportSettings":
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text("utf-8"))
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()

    def reset(self) -> None:
        """Reset to defaults."""
        defaults = ImportSettings()
        for k, v in asdict(defaults).items():
            setattr(self, k, v)
        self.save()

