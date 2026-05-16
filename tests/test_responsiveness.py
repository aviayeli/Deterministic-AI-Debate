"""Phase 2a.3 — ResponsivenessCalculator contract tests."""
import pytest

from src.debate.evaluation.responsiveness import ResponsivenessCalculator
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry


def _make_claim(addressed: list[str], agent_id: str = "PRO") -> ClaimPayloadSchema:
    return ClaimPayloadSchema(
        agent_id=agent_id,
        round_number=1,
        stance="PRO",
        claim_text="Test claim.",
        addressed_claim_ids=addressed,
    )


def _make_ledger(*texts: str) -> list[LedgerEntry]:
    return [
        LedgerEntry(
            claim=ClaimPayloadSchema(
                agent_id="CON",
                round_number=i + 1,
                stance="CON",
                claim_text=text,
                addressed_claim_ids=[],
            )
        )
        for i, text in enumerate(texts)
    ]


@pytest.fixture
def calc() -> ResponsivenessCalculator:
    return ResponsivenessCalculator()


def test_score_is_one_when_all_ids_valid(calc: ResponsivenessCalculator) -> None:
    ledger = _make_ledger("claim A", "claim B")
    ids = [e.claim.claim_id for e in ledger]
    claim = _make_claim(addressed=ids)
    assert calc.calculate(claim, ledger) == pytest.approx(1.0)


def test_score_is_zero_when_no_ids_match(calc: ResponsivenessCalculator) -> None:
    ledger = _make_ledger("claim A", "claim B")
    claim = _make_claim(addressed=["fake-id-1", "fake-id-2"])
    assert calc.calculate(claim, ledger) == pytest.approx(0.0)


def test_score_is_half_when_half_ids_match(calc: ResponsivenessCalculator) -> None:
    ledger = _make_ledger("A", "B", "C", "D")
    valid_ids = [e.claim.claim_id for e in ledger[:2]]
    claim = _make_claim(addressed=valid_ids + ["fake-1", "fake-2"])
    assert calc.calculate(claim, ledger) == pytest.approx(0.5)


def test_score_is_zero_when_ledger_is_empty(calc: ResponsivenessCalculator) -> None:
    claim = _make_claim(addressed=["any-id"])
    assert calc.calculate(claim, []) == pytest.approx(0.0)


def test_invalid_ids_lower_score_no_raise(calc: ResponsivenessCalculator) -> None:
    # 3-entry ledger; only 1 addressed ID is valid → score = 1/3, no exception
    ledger = _make_ledger("claim A", "claim B", "claim C")
    valid_id = ledger[0].claim.claim_id
    claim = _make_claim(addressed=[valid_id, "bad-1", "bad-2"])
    score = calc.calculate(claim, ledger)
    assert 0.0 < score < 1.0


def test_score_is_deterministic(calc: ResponsivenessCalculator) -> None:
    ledger = _make_ledger("claim A", "claim B")
    ids = [e.claim.claim_id for e in ledger]
    claim = _make_claim(addressed=ids)
    assert calc.calculate(claim, ledger) == calc.calculate(claim, ledger)
