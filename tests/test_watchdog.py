"""Watchdog circuit breaker tests."""
from __future__ import annotations

import pytest

from src.debate.gatekeeper.watchdog import Watchdog, WatchdogTrippedError


def test_watchdog_not_tripped_initially() -> None:
    assert not Watchdog(failure_threshold=3).tripped


def test_watchdog_trips_exactly_at_threshold() -> None:
    wd = Watchdog(failure_threshold=2)
    wd.record_failure()
    assert not wd.tripped
    wd.record_failure()
    assert wd.tripped


def test_watchdog_guard_raises_when_circuit_open() -> None:
    wd = Watchdog(failure_threshold=1)
    wd.record_failure()
    with pytest.raises(WatchdogTrippedError):
        wd.guard(lambda: None)


def test_watchdog_guard_records_success_and_decrements() -> None:
    wd = Watchdog(failure_threshold=5)
    wd.record_failure()
    wd.guard(lambda: "ok")
    assert wd._failures == 0


def test_watchdog_guard_propagates_exception_and_records_failure() -> None:
    wd = Watchdog(failure_threshold=5)

    def _raise() -> None:
        raise ValueError("chaos!")

    with pytest.raises(ValueError):
        wd.guard(_raise)
    assert wd._failures == 1


def test_watchdog_reset_clears_all_state() -> None:
    wd = Watchdog(failure_threshold=1)
    wd.record_failure()
    wd.reset()
    assert not wd.tripped and wd._failures == 0


def test_watchdog_success_decrements_failure_count() -> None:
    wd = Watchdog(failure_threshold=10)
    wd.record_failure()
    wd.record_failure()
    wd.record_success()
    assert wd._failures == 1
