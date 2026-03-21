from __future__ import annotations

from enum import Enum


class InvalidTransitionError(ValueError):
    """Raised when a job state transition is not allowed."""


class JobState(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    DEDUPLICATING = "deduplicating"
    STAGING = "staging"
    IMPORTING = "importing"
    VERIFYING = "verifying"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class FileStatus(Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    STAGED = "staged"
    IMPORTING = "importing"
    IMPORTED = "imported"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_ERROR = "skipped_error"
    ERROR = "error"
    RETRYING = "retrying"


VALID_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.IDLE: {JobState.SCANNING},
    JobState.SCANNING: {JobState.DEDUPLICATING, JobState.PAUSED, JobState.ERROR},
    JobState.DEDUPLICATING: {
        JobState.STAGING,
        JobState.IMPORTING,
        JobState.PAUSED,
        JobState.ERROR,
    },
    JobState.STAGING: {JobState.IMPORTING, JobState.PAUSED, JobState.ERROR},
    JobState.IMPORTING: {JobState.VERIFYING, JobState.PAUSED, JobState.ERROR},
    JobState.VERIFYING: {
        JobState.COMPLETED,
        JobState.IMPORTING,
        JobState.PAUSED,
        JobState.ERROR,
    },
    JobState.PAUSED: {
        JobState.SCANNING,
        JobState.DEDUPLICATING,
        JobState.STAGING,
        JobState.IMPORTING,
        JobState.VERIFYING,
    },
    JobState.COMPLETED: set(),
    JobState.ERROR: {JobState.IDLE, JobState.SCANNING},
    JobState.CANCELLED: set(),
}

for state in JobState:
    VALID_TRANSITIONS.setdefault(state, set()).add(JobState.CANCELLED)


def transition(current: JobState, target: JobState) -> JobState:
    """Validate and return the requested target state."""

    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(
            f"Cannot transition job from {current.value!r} to {target.value!r}."
        )
    return target