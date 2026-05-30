"""Phase 7 — EventBus lifecycle hooks and plugin architecture."""
from __future__ import annotations

import threading
from typing import Literal
from unittest.mock import patch

import pytest

from src.debate.agents.base import BaseAgent
from src.debate.events.bus import EventBus
from src.debate.events.types import DebateStartEvent
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry

_SDK = "src.debate.sdk.sdk"
_ANTH = f"{_SDK}.anthropic.Anthropic"
_GK = f"{_SDK}.ApiGatekeeper"
_GK_CFG = f"{_SDK}.GatekeeperConfig.load"
_JUDGE = "src.debate.evaluation.judge.Judge.evaluate_debate"


class _Stub(BaseAgent):
    def __init__(self, stance: Literal["PRO", "CON"]) -> None:
        super().__init__()
        self._stance = stance

    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema:
        return ClaimPayloadSchema(
            agent_id=self._stance,
            round_number=round_number,
            stance=self._stance,  # type: ignore[arg-type]
            claim_text="stub",
            addressed_claim_ids=[],
        )


def _make_sdk(topic: str | None = None):
    with patch(_ANTH), patch(_GK), patch(_GK_CFG):
        from src.debate.sdk import DebateSDK

        return DebateSDK(topic=topic)


def _verdict():
    from src.debate.schemas.verdict import VerdictSchema
    return VerdictSchema(
        winner="PRO", pro_score=0.7, con_score=0.5, tiebreaker_used=None,
        evidence_quality_pro=0.8, evidence_quality_con=0.6,
        v1_distance_pro=0.1, v1_distance_con=0.2,
        responsiveness_pro=0.9, responsiveness_con=0.7, reasoning="stub",
    )




def test_emit_no_handlers_is_noop() -> None:
    EventBus().emit("on_round_start", None)


def test_single_handler_called_once() -> None:
    bus = EventBus()
    calls: list = []
    bus.on("evt", calls.append)
    bus.emit("evt", "payload")
    assert calls == ["payload"]


def test_multiple_handlers_called_in_order() -> None:
    bus = EventBus()
    order: list = []
    bus.on("evt", lambda _: order.append(1))
    bus.on("evt", lambda _: order.append(2))
    bus.emit("evt", None)
    assert order == [1, 2]


def test_handler_exception_propagates() -> None:
    bus = EventBus()
    bus.on("evt", lambda _: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        bus.emit("evt", None)


def test_on_is_thread_safe() -> None:
    bus = EventBus()
    calls: list = []

    def _reg() -> None:
        bus.on("evt", calls.append)

    threads = [threading.Thread(target=_reg) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    bus.emit("evt", "x")
    assert len(calls) == 20




@patch(_JUDGE)
def test_run_debate_fires_all_event_types(mock_j) -> None:
    mock_j.return_value = _verdict()
    from src.debate.engine.pipeline import run_debate

    bus = EventBus()
    seen: set[str] = set()
    for name in (
        "on_debate_start",
        "on_round_start",
        "on_agent_reply",
        "on_round_end",
        "before_evaluation",
        "on_debate_end",
    ):
        bus.on(name, lambda _, n=name: seen.add(n))
    run_debate(_Stub("PRO"), _Stub("CON"), max_rounds=2, bus=bus)
    assert seen == {
        "on_debate_start",
        "on_round_start",
        "on_agent_reply",
        "on_round_end",
        "before_evaluation",
        "on_debate_end",
    }


# --- SDK integration ---


def test_sdk_on_delegates_to_bus() -> None:
    sdk = _make_sdk()
    calls: list = []
    sdk.on("test_evt", calls.append)
    sdk._bus.emit("test_evt", "payload")
    assert calls == ["payload"]


def test_plugin_registered_before_run_fires() -> None:
    sdk = _make_sdk()
    received: list = []
    sdk.on("on_debate_start", received.append)
    sdk._bus.emit("on_debate_start", DebateStartEvent(topic="t", max_rounds=3))
    assert len(received) == 1
    assert received[0].max_rounds == 3
