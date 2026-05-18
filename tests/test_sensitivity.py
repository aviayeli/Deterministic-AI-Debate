"""Sensitivity Analysis tests — Section 9.1 Hyperparameter Sensitivity."""
from __future__ import annotations

from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from src.debate.engine.pipeline import DebateResult
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import RoundSchema
from src.debate.schemas.verdict import VerdictSchema
from src.debate.sensitivity_runner import (
    SensitivityConfig,
    SensitivityResult,
    SensitivityRunner,
    _count_truncations,
)

_SR = "src.debate.sensitivity_runner.run_debate"


def _claim(stance: Literal["PRO", "CON"], rn: int) -> ClaimPayloadSchema:
    return ClaimPayloadSchema(
        agent_id=stance, round_number=rn, stance=stance,
        claim_text="test", addressed_claim_ids=[],
    )


def _verdict(tiebreaker: str | None = None) -> VerdictSchema:
    return VerdictSchema(
        winner="PRO", pro_score=0.6, con_score=0.4, tiebreaker_used=tiebreaker,
        evidence_quality_pro=0.5, evidence_quality_con=0.5,
        v1_distance_pro=0.1, v1_distance_con=0.2,
        responsiveness_pro=0.6, responsiveness_con=0.4, reasoning="stub",
    )


def _result(rounds: int = 3, tiebreaker: str | None = None) -> DebateResult:
    rs = [
        RoundSchema(
            round_number=i + 1, pro_claim=_claim("PRO", i + 1),
            con_claim=_claim("CON", i + 1), responsiveness_score_pro=0.6,
            responsiveness_score_con=0.4,
        )
        for i in range(rounds)
    ]
    return DebateResult(
        rounds=rs, verdict=_verdict(tiebreaker), latency_per_round=[0.01] * rounds,
        tokens_per_debate=100, cost_per_debate=0.001, context_cache_efficiency=0.5,
    )


@pytest.fixture()
def gk() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def cfg() -> SensitivityConfig:
    return SensitivityConfig(
        temperatures=[0.0, 1.0], max_rounds_values=[2, 4], runs_per_config=1
    )


def test_sensitivity_config_defaults() -> None:
    c = SensitivityConfig()
    assert len(c.temperatures) > 0
    assert len(c.max_rounds_values) > 0 and c.runs_per_config >= 1


def test_sensitivity_config_custom() -> None:
    c = SensitivityConfig(temperatures=[0.2, 0.8], max_rounds_values=[1], runs_per_config=2)
    assert c.temperatures == [0.2, 0.8] and c.runs_per_config == 2


def test_sensitivity_result_fields() -> None:
    r = SensitivityResult(
        temperature=0.7, max_rounds=5, tiebreaker_count=1,
        context_truncation_count=3, mean_tokens=80.0, run_count=2,
    )
    assert r.temperature == 0.7 and r.max_rounds == 5


def test_count_truncations_zero_for_short_debate() -> None:
    assert _count_truncations(_result(rounds=2)) == 0


def test_count_truncations_positive_for_long_debate() -> None:
    assert _count_truncations(_result(rounds=6)) > 0


def test_count_truncations_grows_with_rounds() -> None:
    assert _count_truncations(_result(2)) < _count_truncations(_result(8))


def test_runner_result_count_matches_grid(gk, cfg) -> None:
    with patch(_SR, return_value=_result()):
        results = SensitivityRunner(gk, cfg).run()
    assert len(results) == len(cfg.temperatures) * len(cfg.max_rounds_values)


def test_runner_covers_full_cartesian_product(gk, cfg) -> None:
    with patch(_SR, return_value=_result()):
        results = SensitivityRunner(gk, cfg).run()
    pairs = {(r.temperature, r.max_rounds) for r in results}
    expected = {(t, r) for t in cfg.temperatures for r in cfg.max_rounds_values}
    assert pairs == expected


def test_runner_mean_tokens_non_negative(gk, cfg) -> None:
    with patch(_SR, return_value=_result()):
        results = SensitivityRunner(gk, cfg).run()
    assert all(r.mean_tokens >= 0.0 for r in results)


@pytest.mark.parametrize(("tb", "expected"), [("prng", 1), (None, 0)])
def test_runner_tiebreaker_count(gk, tb, expected) -> None:
    c = SensitivityConfig(temperatures=[0.0], max_rounds_values=[2], runs_per_config=1)
    with patch(_SR, return_value=_result(tiebreaker=tb)):
        results = SensitivityRunner(gk, c).run()
    assert results[0].tiebreaker_count == expected


def test_runner_uses_default_config_when_none(gk) -> None:
    with patch(_SR, return_value=_result()):
        results = SensitivityRunner(gk).run()
    d = SensitivityConfig()
    assert len(results) == len(d.temperatures) * len(d.max_rounds_values)


def test_runner_run_count_matches_config(gk) -> None:
    c = SensitivityConfig(temperatures=[0.0], max_rounds_values=[2], runs_per_config=3)
    with patch(_SR, return_value=_result()):
        results = SensitivityRunner(gk, c).run()
    assert results[0].run_count == 3


def test_runner_truncation_reflects_debate_length(gk) -> None:
    c_long = SensitivityConfig(temperatures=[0.0], max_rounds_values=[6], runs_per_config=1)
    c_short = SensitivityConfig(temperatures=[0.0], max_rounds_values=[2], runs_per_config=1)
    with patch(_SR, return_value=_result(rounds=6)):
        r_long = SensitivityRunner(gk, c_long).run()[0]
    with patch(_SR, return_value=_result(rounds=2)):
        r_short = SensitivityRunner(gk, c_short).run()[0]
    assert r_long.context_truncation_count > r_short.context_truncation_count
