from __future__ import annotations


class ThrottleController:
    """Dynamically adjusts batch sizes and cooldown periods."""

    def __init__(
        self,
        initial_batch_size: int = 5,
        max_batch_size: int = 50,
        min_batch_size: int = 1,
        cooldown_seconds: float = 30,
        extended_cooldown_seconds: float = 120,
        extended_cooldown_every: int = 100,
    ):
        self._min_batch_size = max(1, min_batch_size)
        self._max_batch_size = max(self._min_batch_size, max_batch_size)
        self._current_batch_size = min(
            self._max_batch_size,
            max(self._min_batch_size, initial_batch_size),
        )
        self._cooldown_seconds = float(cooldown_seconds)
        self._extended_cooldown_seconds = float(extended_cooldown_seconds)
        self._extended_cooldown_every = max(0, extended_cooldown_every)
        self._total_processed = 0

    def get_batch_size(self) -> int:
        """Return current recommended batch size."""
        return self._current_batch_size

    def report_success(self, count: int):
        """Report successful import of count files. May increase batch size."""
        processed = max(0, count)
        self._total_processed += processed
        if processed == 0:
            return
        growth = max(1, processed // max(1, self._current_batch_size))
        self._current_batch_size = min(
            self._max_batch_size,
            self._current_batch_size + growth,
        )

    def report_failure(self, count: int):
        """Report failed import. Halves batch size."""
        self._total_processed += max(0, count)
        halved = max(1, self._current_batch_size // 2)
        self._current_batch_size = max(self._min_batch_size, halved)

    def get_cooldown(self) -> float:
        """Return seconds to wait before next batch. Extended cooldown every N files."""
        if (
            self._extended_cooldown_every > 0
            and self._total_processed > 0
            and self._total_processed % self._extended_cooldown_every == 0
        ):
            return self._extended_cooldown_seconds
        return self._cooldown_seconds

    @property
    def total_processed(self) -> int:
        return self._total_processed

    @property
    def current_batch_size(self) -> int:
        return self._current_batch_size