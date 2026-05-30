"""Phase 14-A.1 — FIFO queue behavior tests: blocking, error propagation, thread safety."""
import threading
import time
from unittest.mock import MagicMock

import anthropic
import pytest

from src.debate.gatekeeper import (
    ApiGatekeeper,
    GatekeeperRateLimitError,
    GatekeeperTimeoutError,
)
from src.debate.gatekeeper.config import GatekeeperConfig


def _cfg(rpm: int = 600, retries: int = 0, queue_maxsize: int = 100) -> GatekeeperConfig:
    return GatekeeperConfig(
        requests_per_minute=rpm,
        max_retries=retries,
        timeout_seconds=30.0,
        backoff_factor=0.0,
        retryable_status_codes=[429, 529],
        queue_maxsize=queue_maxsize,
    )


def _make(rpm: int = 600, retries: int = 0) -> tuple[ApiGatekeeper, MagicMock]:
    client = MagicMock()
    return ApiGatekeeper(client, _cfg(rpm=rpm, retries=retries)), client


def _ok() -> MagicMock:
    return MagicMock(
        content=[MagicMock(text='{"claim_text":"x","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )


def test_empty_bucket_blocks_not_raises() -> None:
    """call() must block (not raise) when the token bucket is empty."""
    gk, client = _make()
    gk._tokens = 0.0
    client.messages.create.return_value = _ok()

    completed = threading.Event()

    def _go() -> None:
        gk.call(model="m", max_tokens=10, messages=[])
        completed.set()

    def _refill() -> None:
        time.sleep(0.05)
        gk._tokens = 2.0

    t = threading.Thread(target=_go)
    r = threading.Thread(target=_refill)
    t.start()
    r.start()
    t.join(timeout=5.0)
    r.join(timeout=1.0)

    assert completed.is_set(), "call() raised or deadlocked instead of blocking until tokens refilled"


def test_timeout_error_propagates_through_queue() -> None:
    """GatekeeperTimeoutError must still surface when routed through the queue."""
    gk, client = _make(retries=0)
    client.messages.create.side_effect = anthropic.APITimeoutError(request=MagicMock())
    with pytest.raises(GatekeeperTimeoutError):
        gk.call(model="m", max_tokens=10, messages=[])


def test_rate_limit_error_propagates_through_queue() -> None:
    """GatekeeperRateLimitError must surface after exhausted retries via the queue."""
    gk, client = _make(retries=1)
    client.messages.create.side_effect = anthropic.RateLimitError(
        "rl", response=MagicMock(status_code=429), body={}
    )
    with pytest.raises(GatekeeperRateLimitError):
        gk.call(model="m", max_tokens=10, messages=[])


def test_thread_safety_no_deadlock() -> None:
    """8 concurrent threads each submitting 3 calls must all complete within 10 s."""
    gk, client = _make(rpm=600)
    client.messages.create.return_value = _ok()

    errors: list[Exception] = []

    def _worker() -> None:
        try:
            for _ in range(3):
                gk.call(model="m", max_tokens=10, messages=[])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert not errors, f"Thread errors during concurrent calls: {errors}"
    assert all(not t.is_alive() for t in threads), "Deadlock: threads still alive after 10 s"
