from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import Database
from .state import InvalidTransitionError, JobState, transition


class Job:
    def __init__(self, db: Database, job_id: str | None = None):
        self.db = db
        self.job_id = job_id or self.db.create_job("", {"previous_state": None})
        self._load()

    @property
    def state(self) -> JobState:
        self._load()
        return self._state

    @property
    def source_path(self) -> Path | None:
        self._load()
        return self._source_path

    @property
    def stats(self) -> dict[str, int]:
        return self.db.get_job_stats(self.job_id)

    def start(self, source_path: Path) -> None:
        next_state = transition(self.state, JobState.SCANNING)
        self.db.update_job_source_path(self.job_id, source_path)
        self._update_config(previous_state=None)
        self.db.update_job_state(self.job_id, next_state)
        self.db.log_action(self.job_id, None, "start", f"source={source_path}")
        self._load()

    def pause(self) -> None:
        current_state = self.state
        next_state = transition(current_state, JobState.PAUSED)
        self._update_config(previous_state=current_state.value)
        self.db.update_job_state(self.job_id, next_state)
        self.db.log_action(self.job_id, None, "pause", f"from={current_state.value}")
        self._load()

    def resume(self) -> None:
        if self.state != JobState.PAUSED:
            raise InvalidTransitionError("Only paused jobs can be resumed.")
        previous_state_value = self._config.get("previous_state")
        if not previous_state_value:
            raise InvalidTransitionError("Paused job has no previous state to resume to.")
        next_state = transition(JobState.PAUSED, JobState(previous_state_value))
        self._update_config(previous_state=None)
        self.db.update_job_state(self.job_id, next_state)
        self.db.log_action(self.job_id, None, "resume", f"to={next_state.value}")
        self._load()

    def cancel(self) -> None:
        next_state = transition(self.state, JobState.CANCELLED)
        self._update_config(previous_state=None)
        self.db.update_job_state(self.job_id, next_state)
        self.db.log_action(self.job_id, None, "cancel", "job cancelled")
        self._load()

    def complete(self) -> None:
        next_state = transition(self.state, JobState.COMPLETED)
        self._update_config(previous_state=None)
        self.db.update_job_state(self.job_id, next_state)
        self.db.log_action(self.job_id, None, "complete", "job completed")
        self._load()

    def fail(self, error: str) -> None:
        next_state = transition(self.state, JobState.ERROR)
        self.db.update_job_state(self.job_id, next_state)
        self.db.log_action(self.job_id, None, "error", error)
        self._load()

    def _load(self) -> None:
        job = self.db.get_job(self.job_id)
        if job is None:
            raise ValueError(f"Job {self.job_id!r} does not exist.")
        self._state = JobState(job["state"])
        self._source_path = Path(job["source_path"]) if job["source_path"] else None
        self._config = json.loads(job["config_json"] or "{}")

    def _update_config(self, **updates: Any) -> None:
        config = dict(self._config)
        config.update(updates)
        self.db.update_job_config(self.job_id, config)
        self._config = config