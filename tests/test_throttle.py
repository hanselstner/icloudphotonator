from icloudphotonator.throttle import ThrottleController


def test_initial_batch_size_is_five() -> None:
    throttle = ThrottleController()

    assert throttle.get_batch_size() == 5


def test_batch_size_increases_after_success() -> None:
    throttle = ThrottleController(initial_batch_size=5)

    throttle.report_success(5)

    assert throttle.get_batch_size() > 5


def test_batch_size_halves_after_failure() -> None:
    throttle = ThrottleController(initial_batch_size=8)

    throttle.report_failure(8)

    assert throttle.get_batch_size() == 4


def test_batch_size_does_not_exceed_max() -> None:
    throttle = ThrottleController(initial_batch_size=5, max_batch_size=6)

    throttle.report_success(5)
    throttle.report_success(6)

    assert throttle.get_batch_size() == 6


def test_batch_size_does_not_go_below_min() -> None:
    throttle = ThrottleController(initial_batch_size=2, min_batch_size=2)

    throttle.report_failure(2)
    throttle.report_failure(2)

    assert throttle.get_batch_size() == 2


def test_extended_cooldown_triggers_every_n_files() -> None:
    throttle = ThrottleController(cooldown_seconds=10, extended_cooldown_seconds=60, extended_cooldown_every=10)

    throttle.report_success(10)

    assert throttle.get_cooldown() == 60