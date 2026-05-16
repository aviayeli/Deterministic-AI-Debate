"""Phase 2b.1 — BaseAgent V₁ state, LedgerManager, and multiplicative weighting."""
import json

import pytest

from src.debate.agents.base import BaseAgent
from src.debate.config import settings
from src.debate.engine.ledger import LedgerManager
from src.debate.schemas.claim import ClaimPayloadSchema, EvidenceSchema
from src.debate.schemas.round import LedgerEntry


class _StubAgent(BaseAgent):
    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema:
        raise NotImplementedError


def _bare_entry(text: str = "claim") -> LedgerEntry:
    return LedgerEntry(
        claim=ClaimPayloadSchema(
            agent_id="CON",
            round_number=1,
            stance="CON",
            claim_text=text,
            addressed_claim_ids=[],
        )
    )


def _evidence_entry(quality: float, text: str = "claim") -> LedgerEntry:
    ev = EvidenceSchema(source="s", quality_score=quality, citation="c")
    return LedgerEntry(
        claim=ClaimPayloadSchema(
            agent_id="CON",
            round_number=1,
            stance="CON",
            claim_text=text,
            addressed_claim_ids=[],
            evidence=[ev],
        )
    )


def test_v1_is_none_before_set() -> None:
    agent = _StubAgent()
    assert agent.v1_embedding is None


def test_set_v1_stores_value() -> None:
    agent = _StubAgent()
    vec = [1.0, 0.0, 0.0]
    agent.set_v1_embedding(vec)
    assert agent.v1_embedding == vec


def test_set_v1_raises_on_second_call() -> None:
    agent = _StubAgent()
    agent.set_v1_embedding([1.0, 0.0, 0.0])
    with pytest.raises(RuntimeError):
        agent.set_v1_embedding([0.0, 1.0, 0.0])


def test_windowed_ledger_caps_at_n() -> None:
    entries = [_bare_entry(f"c{i}") for i in range(5)]
    mgr = LedgerManager(entries)
    assert len(mgr.get_windowed_ledger(3)) == 3


def test_windowed_ledger_returns_last_n() -> None:
    entries = [_bare_entry(f"c{i}") for i in range(5)]
    mgr = LedgerManager(entries)
    assert mgr.get_windowed_ledger(2) == entries[-2:]


def test_v1_not_in_windowed_ledger() -> None:
    entries = [_bare_entry(f"c{i}") for i in range(5)]
    mgr = LedgerManager(entries)
    window = mgr.get_windowed_ledger(3)
    assert entries[0].claim.claim_id not in {e.claim.claim_id for e in window}


def test_serialize_for_llm_returns_valid_json() -> None:
    mgr = LedgerManager([_bare_entry()])
    raw = mgr.serialize_for_llm(window=1)
    parsed = json.loads(raw)
    assert isinstance(parsed, list)


def test_serialize_contains_claim_id_and_text() -> None:
    mgr = LedgerManager([_bare_entry("hello")])
    parsed = json.loads(mgr.serialize_for_llm(window=1))
    assert "claim_id" in parsed[0]
    assert "claim_text" in parsed[0]


def test_get_claim_ids_returns_set() -> None:
    e1, e2 = _bare_entry("a"), _bare_entry("b")
    mgr = LedgerManager([e1, e2])
    ids = mgr.get_claim_ids()
    assert isinstance(ids, set)
    assert e1.claim.claim_id in ids
    assert e2.claim.claim_id in ids


def test_weights_are_decay_times_confidence() -> None:
    lam = 0.3
    e0 = _evidence_entry(quality=0.8)
    e1 = _evidence_entry(quality=0.5)
    mgr = LedgerManager([e0, e1])
    weights = mgr.compute_weights(lam)
    # n=2: decay=[lam^1, lam^0]=[0.3, 1.0]; confidence=[0.8, 0.5]
    assert weights[0] == pytest.approx(lam * 0.8, rel=1e-6)
    assert weights[1] == pytest.approx(1.0 * 0.5, rel=1e-6)


def test_no_evidence_defaults_confidence_to_one() -> None:
    lam = 0.3
    entries = [_bare_entry("no-ev-a"), _bare_entry("no-ev-b")]
    mgr = LedgerManager(entries)
    weights = mgr.compute_weights(lam)
    # n=2: decay=[0.3, 1.0]; confidence=[1.0, 1.0]
    assert weights[0] == pytest.approx(lam, rel=1e-6)
    assert weights[1] == pytest.approx(1.0, rel=1e-6)


def test_three_entries_lambda_0_3_weights() -> None:
    lam = settings.RECENCY_DECAY_LAMBDA  # 0.3
    entries = [_bare_entry(f"c{i}") for i in range(3)]
    mgr = LedgerManager(entries)
    weights = mgr.compute_weights(lam)
    # n=3: decay=[lam^2, lam^1, lam^0]=[0.09, 0.3, 1.0]; all confidence=1.0
    assert weights == pytest.approx([0.09, 0.3, 1.0], rel=1e-6)
