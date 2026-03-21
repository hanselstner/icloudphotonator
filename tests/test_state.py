import pytest

from icloudphotonator.state import (
    VALID_TRANSITIONS,
    InvalidTransitionError,
    JobState,
    transition,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current, targets in VALID_TRANSITIONS.items()
        for target in sorted(targets, key=lambda state: state.value)
    ],
)
def test_all_valid_transitions(current: JobState, target: JobState) -> None:
    assert transition(current, target) is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (current, target)
        for current in JobState
        for target in JobState
        if target not in VALID_TRANSITIONS[current]
    ],
)
def test_invalid_transitions_raise(current: JobState, target: JobState) -> None:
    with pytest.raises(InvalidTransitionError):
        transition(current, target)


@pytest.mark.parametrize("current", list(JobState))
def test_cancelled_reachable_from_any_state(current: JobState) -> None:
    assert transition(current, JobState.CANCELLED) is JobState.CANCELLED