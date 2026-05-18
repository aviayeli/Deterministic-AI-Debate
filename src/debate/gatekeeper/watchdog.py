"""Circuit-breaker watchdog for the debate gatekeeper layer."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from ..shared.logger import get_logger

_logger = get_logger("watchdog")


class WatchdogTrippedError(Exception):
    """Raised when a guarded call is attempted on a tripped Watchdog."""


class Watchdog:
    """Monitors failure rate and trips an open-circuit breaker at threshold."""

    def __init__(self, failure_threshold: int = 3) -> None:
        self._threshold = failure_threshold
        self._lock = threading.Lock()
        self._failures: int = 0
        self._tripped: bool = False

    @property
    def tripped(self) -> bool:
        with self._lock:
            return self._tripped

    def record_success(self) -> None:
        with self._lock:
            self._failures = max(0, self._failures - 1)

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._tripped = True
                _logger.warning("Watchdog tripped: %d consecutive failures.", self._failures)

    def reset(self) -> None:
        with self._lock:
            self._failures = 0
            self._tripped = False

    def guard(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call *fn*, record the outcome, and raise if the circuit is open."""
        if self.tripped:
            _logger.error("Guard rejected: circuit open.")
            raise WatchdogTrippedError("Circuit breaker open — too many failures.")
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise
