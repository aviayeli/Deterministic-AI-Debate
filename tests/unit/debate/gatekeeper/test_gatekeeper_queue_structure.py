"""Phase 14-A.1 — FIFO queue structure tests: attribute, drain, and ordering."""
import queue
import threading
import time
from unittest.mock import MagicMock

from src.debate.gatekeeper import ApiGatekeeper
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


def test_gatekeeper_has_fifo_queue() -> None:
    """ApiGatekeeper must expose a queue.Queue for FIFO backpressure."""
    gk, _ = _make()
    assert hasattr(gk, "_queue"), "_queue attribute missing — FIFO queue not implemented"
    assert isinstance(gk._queue, queue.Queue)


def test_queue_drains_to_zero_after_all_calls() -> None:
    """Internal queue must be empty once all pending calls have resolved."""
    gk, client = _make()
    client.messages.create.return_value = _ok()

    threads = [
        threading.Thread(target=gk.call, kwargs={"model": "m", "max_tokens": 10, "messages": []})
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert gk._queue.qsize() == 0, "Queue not fully drained after all calls completed"


def test_fifo_ordering_first_enqueued_first_served() -> None:
    """Call submitted first must complete before a later-submitted call."""
    gk, client = _make(rpm=60)
    gk._tokens = 0.3  # near-empty: forces both callers to queue up

    order: list[int] = []
    responses = [_ok(), _ok()]
    call_idx = 0

    def _side_effect(**_kw):
        nonlocal call_idx
        result = responses[call_idx]
        call_idx += 1
        return result

    client.messages.create.side_effect = _side_effect

    def _call(tag: int, delay: float) -> None:
        time.sleep(delay)
        gk.call(model="m", max_tokens=10, messages=[])
        order.append(tag)

    t1 = threading.Thread(target=_call, args=(1, 0.0))
    t2 = threading.Thread(target=_call, args=(2, 0.02))  # t1 enqueues 20 ms before t2
    t1.start()
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    assert order == [1, 2], f"Expected FIFO order [1, 2], got {order}"
