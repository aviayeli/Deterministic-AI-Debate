"""Tests for DiscourseChecker and Judge civility integration."""
from unittest.mock import MagicMock

import pytest

from src.debate.evaluation.discourse import DISCOURSE_POLICY, DiscourseChecker
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry, RoundSchema


def _claim(agent_id: str, text: str) -> ClaimPayloadSchema:
    return ClaimPayloadSchema(
        agent_id=agent_id,
        round_number=1,
        stance=agent_id,  # type: ignore[arg-type]
        claim_text=text,
        addressed_claim_ids=[],
    )


def _agent(agent_id: str, text: str) -> MagicMock:
    agent = MagicMock()
    agent._ledger = [LedgerEntry(claim=_claim(agent_id, text))]
    agent.v1_embedding = None
    return agent


def test_clean_text_has_zero_penalty():
    assert DiscourseChecker().penalty("AI will automate routine tasks effectively.") == 0.0


def test_single_violation_incurs_penalty():
    assert DiscourseChecker().penalty("That is a stupid argument.") == pytest.approx(0.05)


def test_multiple_violations_accumulate():
    assert DiscourseChecker().penalty("You are an idiot and a moron.") == pytest.approx(0.10)


def test_penalty_is_capped_at_max():
    text = "idiot stupid moron dumb fool worthless useless disgusting imbecile pathetic"
    assert DiscourseChecker().penalty(text) == pytest.approx(0.25)


def test_violations_returns_matched_patterns():
    v = DiscourseChecker().violations("What a dumb and pathetic take.")
    assert any("dumb" in p for p in v)
    assert any("pathetic" in p for p in v)


def test_violations_returns_empty_for_clean_text():
    assert DiscourseChecker().violations("Software engineering requires creativity.") == []


def test_check_is_case_insensitive():
    assert DiscourseChecker().penalty("That is STUPID.") > 0.0


def test_discourse_policy_is_non_empty_string():
    assert isinstance(DISCOURSE_POLICY, str) and len(DISCOURSE_POLICY) > 0


def test_judge_penalizes_offending_agent():
    from src.debate.evaluation.judge import Judge

    rounds = [
        RoundSchema(
            round_number=1,
            pro_claim=_claim("PRO", "AI is highly capable."),
            con_claim=_claim("CON", "That is a stupid and moronic argument."),
            responsiveness_score_pro=0.8,
            responsiveness_score_con=0.8,
        )
    ]
    pro_agent = _agent("PRO", "AI is highly capable.")
    con_agent = _agent("CON", "That is a stupid and moronic argument.")

    verdict = Judge().evaluate_debate(rounds, pro_agent, con_agent, "test-debate")
    assert verdict.winner == "PRO"


def test_judge_reasoning_includes_discourse_info():
    from src.debate.evaluation.judge import Judge

    rounds = [
        RoundSchema(
            round_number=1,
            pro_claim=_claim("PRO", "Good point."),
            con_claim=_claim("CON", "Good counter."),
            responsiveness_score_pro=0.7,
            responsiveness_score_con=0.5,
        )
    ]
    pro_agent = _agent("PRO", "Good point.")
    con_agent = _agent("CON", "Good counter.")

    verdict = Judge().evaluate_debate(rounds, pro_agent, con_agent, "x")
    assert "Discourse penalties" in verdict.reasoning


def test_judge_clean_debate_produces_zero_penalties_in_reasoning():
    from src.debate.evaluation.judge import Judge

    rounds = [
        RoundSchema(
            round_number=1,
            pro_claim=_claim("PRO", "AI enhances productivity."),
            con_claim=_claim("CON", "Human creativity cannot be replaced."),
            responsiveness_score_pro=0.9,
            responsiveness_score_con=0.5,
        )
    ]
    pro_agent = _agent("PRO", "AI enhances productivity.")
    con_agent = _agent("CON", "Human creativity cannot be replaced.")

    verdict = Judge().evaluate_debate(rounds, pro_agent, con_agent, "y")
    assert "PRO: 0.00" in verdict.reasoning
    assert "CON: 0.00" in verdict.reasoning
