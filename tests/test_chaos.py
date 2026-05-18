"""Chaos Engineering — Section 6.3 Edge Cases & Graceful Degradation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.debate.agents.base import BaseAgent
from src.debate.agents.pro import ProAgent
from src.debate.gatekeeper import ApiGatekeeper, GatekeeperError
from src.debate.gatekeeper.config import GatekeeperConfig
from src.debate.gatekeeper.watchdog import Watchdog, WatchdogTrippedError

_SLP = "src.debate.gatekeeper.gatekeeper.time.sleep"

_MALFORMED: list[str] = [
    "", "\x00\xff\xfe" * 5, "☃" * 100, '{"claim_text":', "\n\r\t" * 20, "a" * 500, "{not: valid json}",
]


def _cfg(retries: int = 0, extra: list[int] | None = None) -> GatekeeperConfig:
    return GatekeeperConfig(
        requests_per_minute=60, max_retries=retries, timeout_seconds=30.0,
        backoff_factor=0.0, retryable_status_codes=[429, 529] + (extra or []), queue_maxsize=100,
    )


def _make(retries: int = 0, extra: list[int] | None = None):
    client = MagicMock()
    return ApiGatekeeper(client, _cfg(retries=retries, extra=extra)), client


def _resp(text: str) -> MagicMock:
    m = MagicMock()
    m.content, m.usage = [MagicMock(text=text)], MagicMock(input_tokens=5, output_tokens=5)
    return m


@patch(_SLP)
def test_connection_drop_retries_and_recovers(mock_sleep) -> None:
    gk, client = _make(retries=2)
    ok = _resp('{"claim_text":"ok","addressed_claim_ids":[]}')
    err = anthropic.APIConnectionError(request=MagicMock())
    client.messages.create.side_effect = [err, err, ok]
    assert gk.call(model="m", max_tokens=10, messages=[]) is ok
    assert client.messages.create.call_count == 3


@patch(_SLP)
def test_connection_drop_exhausted_raises_gatekeeper_error(mock_sleep) -> None:
    gk, client = _make(retries=1)
    client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
    with pytest.raises(GatekeeperError):
        gk.call(model="m", max_tokens=10, messages=[])


@patch(_SLP)
def test_http_503_non_retryable_raises_immediately(mock_sleep) -> None:
    gk, client = _make(retries=3)
    client.messages.create.side_effect = anthropic.InternalServerError(
        "service unavailable", response=MagicMock(status_code=503), body={}
    )
    with pytest.raises(anthropic.InternalServerError):
        gk.call(model="m", max_tokens=10, messages=[])
    assert client.messages.create.call_count == 1


@patch(_SLP)
def test_http_502_retryable_when_configured_recovers(mock_sleep) -> None:
    gk, client = _make(retries=2, extra=[502])
    ok = _resp('{"claim_text":"ok","addressed_claim_ids":[]}')
    bad = anthropic.InternalServerError("bad gw", response=MagicMock(status_code=502), body={})
    client.messages.create.side_effect = [bad, ok]
    assert gk.call(model="m", max_tokens=10, messages=[]) is ok


@pytest.mark.parametrize("bad_text", _MALFORMED)
def test_extract_json_raises_on_garbage(bad_text: str) -> None:
    with pytest.raises(ValueError):
        BaseAgent._extract_json(bad_text)


@patch(_SLP)
def test_agent_propagates_error_on_unicode_garbage(mock_sleep) -> None:
    gk, client = _make()
    client.messages.create.return_value = _resp("☃" * 200)
    with pytest.raises(ValueError):
        ProAgent(gk).generate_claim(1, [])


@patch(_SLP)
def test_agent_recovers_with_valid_response_after_chaos(mock_sleep) -> None:
    gk, client = _make()
    client.messages.create.return_value = _resp(
        '{"claim_text":"recovered","addressed_claim_ids":[]}'
    )
    assert ProAgent(gk).generate_claim(1, []).claim_text == "recovered"


@patch(_SLP)
def test_agent_retries_on_truncated_json_and_succeeds(mock_sleep) -> None:
    gk, client = _make()
    truncated = _resp('{"claim_text":"long arg","addressed_claim_ids":["b0\'')
    ok = _resp('{"claim_text":"recovered after truncation","addressed_claim_ids":[]}')
    client.messages.create.side_effect = [truncated, ok]
    result = ProAgent(gk).generate_claim(1, [])
    assert result.claim_text == "recovered after truncation"
    assert client.messages.create.call_count == 2


@patch(_SLP)
def test_agent_raises_after_all_json_retries_exhausted(mock_sleep) -> None:
    gk, client = _make()
    client.messages.create.return_value = _resp('{"truncated":')
    with pytest.raises(ValueError):
        ProAgent(gk).generate_claim(1, [])


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
