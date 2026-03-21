from __future__ import annotations

import json
from pathlib import Path


APP_DIR = Path.home() / ".icloudphotonator"
DEFAULT_DB_PATH = APP_DIR / "icloudphotonator.db"
DEFAULT_ACTIVE_JOB_PATH = APP_DIR / "active_job.json"


def _normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def load_active_job(active_job_path: Path | None = None) -> dict[str, str] | None:
    path = Path(active_job_path) if active_job_path else DEFAULT_ACTIVE_JOB_PATH
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    return {key: str(value) for key, value in payload.items() if value is not None}


def save_active_job(
    job_id: str,
    source_path: str | Path,
    db_path: str | Path,
    active_job_path: Path | None = None,
) -> None:
    path = Path(active_job_path) if active_job_path else DEFAULT_ACTIVE_JOB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        "source_path": _normalize_path(source_path),
        "db_path": _normalize_path(db_path),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def clear_active_job(active_job_path: Path | None = None) -> None:
    path = Path(active_job_path) if active_job_path else DEFAULT_ACTIVE_JOB_PATH
    try:
        path.unlink()
    except FileNotFoundError:
        return