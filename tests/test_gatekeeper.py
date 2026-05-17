"""Phase 5.1 — ApiGatekeeper: config, rate limiting, timeout, retry, agent wiring."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.debate.gatekeeper import ApiGatekeeper, GatekeeperRateLimitError, GatekeeperTimeoutError
from src.debate.gatekeeper.config import GatekeeperConfig

_SLP = "src.debate.gatekeeper.gatekeeper.time.sleep"
_MON = "src.debate.gatekeeper.gatekeeper.time.monotonic"
_CFG = {
    "requests_per_minute": 50, "max_retries": 3, "timeout_seconds": 30.0,
    "backoff_factor": 1.0, "retryable_status_codes": [429, 529], "queue_maxsize": 100,
}


def _cfg(**kw) -> GatekeeperConfig:
    return GatekeeperConfig(
        requests_per_minute=kw.get("rpm", 60), max_retries=kw.get("retries", 3),
        timeout_seconds=30.0, backoff_factor=kw.get("backoff", 0.0),
        retryable_status_codes=[429, 529], queue_maxsize=100,
    )


def _make(retries: int = 3) -> tuple[ApiGatekeeper, MagicMock]:
    client = MagicMock()
    return ApiGatekeeper(client, _cfg(retries=retries)), client


def _ok() -> MagicMock:
    return MagicMock(
        content=[MagicMock(text='{"claim_text":"x","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )


def test_config_loads_fields(tmp_path: Path) -> None:
    p = tmp_path / "rl.json"
    p.write_text(json.dumps(_CFG))
    cfg = GatekeeperConfig.load(p)
    assert cfg.requests_per_minute == 50 and cfg.max_retries == 3


def test_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        GatekeeperConfig.load(tmp_path / "missing.json")


@patch(_SLP)
def test_call_passes_timeout_and_returns_response(mock_sleep) -> None:
    gk, client = _make()
    client.messages.create.return_value = _ok()
    gk.call(model="m", max_tokens=10, messages=[])
    client.messages.create.assert_called_once()
    assert client.messages.create.call_args.kwargs["timeout"] == 30.0


@patch(_SLP)
@patch(_MON, return_value=0.0)
def test_empty_bucket_triggers_sleep(mock_mon, mock_sleep) -> None:
    gk, client = _make()
    gk._tokens = 0.0
    client.messages.create.return_value = _ok()
    mock_sleep.side_effect = lambda _: setattr(gk, "_tokens", 2.0)
    gk.call(model="m", max_tokens=10, messages=[])
    mock_sleep.assert_called_once()


@patch(_SLP)
def test_timeout_raises_gatekeeper_timeout_error(mock_sleep) -> None:
    gk, client = _make(retries=0)
    client.messages.create.side_effect = anthropic.APITimeoutError(request=MagicMock())
    with pytest.raises(GatekeeperTimeoutError):
        gk.call(model="m", max_tokens=10, messages=[])


@patch(_SLP)
def test_retries_on_429_and_returns_success(mock_sleep) -> None:
    gk, client = _make(retries=2)
    ok = _ok()
    client.messages.create.side_effect = [
        anthropic.RateLimitError("rl", response=MagicMock(status_code=429), body={}), ok,
    ]
    assert gk.call(model="m", max_tokens=10, messages=[]) is ok
    assert client.messages.create.call_count == 2


@patch(_SLP)
def test_retries_on_529_and_returns_success(mock_sleep) -> None:
    gk, client = _make(retries=2)
    ok, resp = _ok(), MagicMock()
    resp.status_code = 529
    client.messages.create.side_effect = [
        anthropic.InternalServerError("ov", response=resp, body={}), ok,
    ]
    assert gk.call(model="m", max_tokens=10, messages=[]) is ok


@patch(_SLP)
def test_no_retry_on_auth_error(mock_sleep) -> None:
    gk, client = _make()
    client.messages.create.side_effect = anthropic.AuthenticationError(
        "auth", response=MagicMock(status_code=401), body={},
    )
    with pytest.raises(anthropic.AuthenticationError):
        gk.call(model="m", max_tokens=10, messages=[])
    assert client.messages.create.call_count == 1


@patch(_SLP)
def test_no_retry_on_bad_request(mock_sleep) -> None:
    gk, client = _make()
    client.messages.create.side_effect = anthropic.BadRequestError(
        "bad", response=MagicMock(status_code=400), body={},
    )
    with pytest.raises(anthropic.BadRequestError):
        gk.call(model="m", max_tokens=10, messages=[])
    assert client.messages.create.call_count == 1


@patch(_SLP)
def test_exhausted_429_retries_raises_rate_limit_error(mock_sleep) -> None:
    gk, client = _make(retries=1)
    client.messages.create.side_effect = anthropic.RateLimitError(
        "rl", response=MagicMock(status_code=429), body={},
    )
    with pytest.raises(GatekeeperRateLimitError):
        gk.call(model="m", max_tokens=10, messages=[])


@patch(_SLP)
def test_pro_agent_calls_gatekeeper(mock_sleep) -> None:
    from src.debate.agents.pro import ProAgent
    gk, client = _make()
    client.messages.create.return_value = _ok()
    ProAgent(gk).generate_claim(1, [])
    client.messages.create.assert_called_once()


@patch(_SLP)
def test_con_agent_calls_gatekeeper(mock_sleep) -> None:
    from src.debate.agents.con import ConAgent
    gk, client = _make()
    client.messages.create.return_value = _ok()
    ConAgent(gk).generate_claim(1, [])
    client.messages.create.assert_called_once()
