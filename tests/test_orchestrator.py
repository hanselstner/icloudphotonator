from pathlib import Path

from icloudphotonator.db import Database
from icloudphotonator.importer import PhotoImporter
from icloudphotonator.orchestrator import ImportOrchestrator
from icloudphotonator.staging import StagingManager
from icloudphotonator.throttle import ThrottleController


def test_orchestrator_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    staging_dir = tmp_path / "staging"

    orchestrator = ImportOrchestrator(db_path, staging_dir)

    assert isinstance(orchestrator.db, Database)
    assert isinstance(orchestrator.throttle, ThrottleController)
    assert isinstance(orchestrator.staging, StagingManager)
    assert isinstance(orchestrator.importer, PhotoImporter)
    assert orchestrator.db.db_path == db_path
    assert orchestrator.staging.staging_dir == staging_dir
    assert orchestrator._paused.is_set()
    assert orchestrator._cancelled is False


def test_pause_resume_cancel_flags(tmp_path: Path) -> None:
    orchestrator = ImportOrchestrator(tmp_path / "jobs.db")

    orchestrator.pause()
    assert orchestrator._paused.is_set() is False

    orchestrator.resume()
    assert orchestrator._paused.is_set() is True

    orchestrator.cancel()
    assert orchestrator._cancelled is True
    assert orchestrator._paused.is_set() is True