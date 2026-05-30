"""Phase 1 — schema and settings contract tests."""
import uuid

import pytest
from pydantic import ValidationError

from src.debate.config import settings
from src.debate.schemas.claim import ClaimPayloadSchema, EvidenceSchema
from src.debate.schemas.round import LedgerEntry, RoundSchema
from src.debate.schemas.verdict import VerdictSchema


@pytest.fixture
def valid_claim() -> ClaimPayloadSchema:
    return ClaimPayloadSchema(
        agent_id="PRO",
        round_number=1,
        stance="PRO",
        claim_text="AI will replace software engineers.",
        addressed_claim_ids=[],
    )


def test_evidence_rejects_quality_above_1() -> None:
    with pytest.raises(ValidationError):
        EvidenceSchema(source="s", quality_score=1.1, citation="c")


def test_evidence_rejects_quality_below_0() -> None:
    with pytest.raises(ValidationError):
        EvidenceSchema(source="s", quality_score=-0.1, citation="c")


def test_evidence_accepts_boundary_values() -> None:
    lo = EvidenceSchema(source="s", quality_score=0.0, citation="c")
    hi = EvidenceSchema(source="s", quality_score=1.0, citation="c")
    assert lo.quality_score == 0.0
    assert hi.quality_score == 1.0


def test_claim_requires_addressed_claim_ids() -> None:
    with pytest.raises(ValidationError):
        ClaimPayloadSchema(  # type: ignore[call-arg]
            agent_id="PRO", round_number=1, stance="PRO", claim_text="Test.",
        )


def test_claim_requires_agent_id() -> None:
    with pytest.raises(ValidationError):
        ClaimPayloadSchema(  # type: ignore[call-arg]
            round_number=1, stance="PRO", claim_text="Test.", addressed_claim_ids=[],
        )


def test_claim_autogenerates_valid_uuid(valid_claim: ClaimPayloadSchema) -> None:
    parsed = uuid.UUID(valid_claim.claim_id, version=4)
    assert str(parsed) == valid_claim.claim_id


def test_claim_ids_are_distinct() -> None:
    c1 = ClaimPayloadSchema(
        agent_id="PRO", round_number=1, stance="PRO",
        claim_text="A.", addressed_claim_ids=[],
    )
    c2 = ClaimPayloadSchema(
        agent_id="PRO", round_number=1, stance="PRO",
        claim_text="B.", addressed_claim_ids=[],
    )
    assert c1.claim_id != c2.claim_id


def test_claim_rejects_invalid_stance() -> None:
    with pytest.raises(ValidationError):
        ClaimPayloadSchema(
            agent_id="PRO", round_number=1, stance="NEUTRAL",
            claim_text="Test.", addressed_claim_ids=[],
        )


def test_ledger_entry_wraps_claim(valid_claim: ClaimPayloadSchema) -> None:
    entry = LedgerEntry(claim=valid_claim)
    assert entry.claim == valid_claim
    assert entry.embedding is None


def test_round_schema_holds_pro_and_con_claims() -> None:
    pro = ClaimPayloadSchema(
        agent_id="PRO", round_number=1, stance="PRO",
        claim_text="PRO claim.", addressed_claim_ids=[],
    )
    con = ClaimPayloadSchema(
        agent_id="CON", round_number=1, stance="CON",
        claim_text="CON claim.", addressed_claim_ids=[],
    )
    r = RoundSchema(
        round_number=1, pro_claim=pro, con_claim=con,
        responsiveness_score_pro=1.0, responsiveness_score_con=1.0,
    )
    assert r.pro_claim.stance == "PRO"
    assert r.con_claim.stance == "CON"


def _make_verdict(**overrides: object) -> VerdictSchema:
    base = {
        "winner": "PRO", "pro_score": 6.0, "con_score": 5.0,
        "tiebreaker_used": None,
        "evidence_quality_pro": 0.8, "evidence_quality_con": 0.7,
        "v1_distance_pro": 0.1, "v1_distance_con": 0.2,
        "responsiveness_pro": 0.9, "responsiveness_con": 0.8,
        "reasoning": "PRO wins.",
    }
    base.update(overrides)
    return VerdictSchema(**base)


def test_verdict_rejects_invalid_winner() -> None:
    with pytest.raises(ValidationError):
        _make_verdict(winner="DRAW")


def test_verdict_accepts_none_tiebreaker() -> None:
    v = _make_verdict(tiebreaker_used=None)
    assert v.tiebreaker_used is None


def test_settings_recency_decay_lambda_is_float() -> None:
    assert isinstance(settings.RECENCY_DECAY_LAMBDA, float)


def test_settings_v1_distance_threshold_is_float() -> None:
    assert isinstance(settings.V1_DISTANCE_THRESHOLD, float)


def test_settings_ledger_window_default() -> None:
    assert settings.LEDGER_WINDOW == 3
