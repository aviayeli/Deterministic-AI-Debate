"""Phase 3.1 — Pipeline orchestrator, metrics reporter, ledger truncation (RED)."""
import json
import tempfile
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

from src.debate.agents.base import BaseAgent
from src.debate.benchmarks.reporter import BenchmarkReporter
from src.debate.engine.pipeline import DebateResult, run_benchmarks, run_debate
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry, RoundSchema
from src.debate.schemas.verdict import VerdictSchema

_JUDGE = "src.debate.evaluation.judge.Judge.evaluate_debate"
_PIPE = "src.debate.engine.pipeline.run_debate"


def _verdict() -> VerdictSchema:
    return VerdictSchema(
        winner="PRO", pro_score=0.7, con_score=0.5, tiebreaker_used=None,
        evidence_quality_pro=0.8, evidence_quality_con=0.6,
        v1_distance_pro=0.1, v1_distance_con=0.2,
        responsiveness_pro=0.9, responsiveness_con=0.7,
        reasoning="Stub verdict.",
    )


def _result(n: int = 10) -> DebateResult:
    def _c(stance: Literal["PRO", "CON"], rn: int) -> ClaimPayloadSchema:
        return ClaimPayloadSchema(
            agent_id=stance, round_number=rn, stance=stance,
            claim_text="x", addressed_claim_ids=[],
        )

    return DebateResult(
        rounds=[
            RoundSchema(round_number=i + 1, pro_claim=_c("PRO", i + 1),
                        con_claim=_c("CON", i + 1),
                        responsiveness_score_pro=1.0, responsiveness_score_con=1.0)
            for i in range(n)
        ],
        verdict=_verdict(), latency_per_round=[0.1] * n,
        tokens_per_debate=2000, cost_per_debate=0.01, context_cache_efficiency=0.8,
    )


class _StubAgent(BaseAgent):
    def __init__(self, stance: str) -> None:
        super().__init__()
        self._stance = stance

    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema:
        ids = [e.claim.claim_id for e in opponent_ledger]
        return ClaimPayloadSchema(
            agent_id=self._stance, round_number=round_number,
            stance=self._stance,  # type: ignore[arg-type]
            claim_text="stub", addressed_claim_ids=ids[:1],
        )


@pytest.fixture()
def pro() -> _StubAgent:
    return _StubAgent("PRO")


@pytest.fixture()
def con() -> _StubAgent:
    return _StubAgent("CON")


@patch(_JUDGE)
def test_run_debate_returns_correct_number_of_rounds(mock_j, pro, con) -> None:
    mock_j.return_value = _verdict()
    assert len(run_debate(pro, con, max_rounds=5).rounds) == 5


@patch(_JUDGE)
def test_each_round_is_valid_round_schema(mock_j, pro, con) -> None:
    mock_j.return_value = _verdict()
    result = run_debate(pro, con, max_rounds=3)
    assert all(isinstance(r, RoundSchema) for r in result.rounds)


@patch(_JUDGE)
def test_result_contains_valid_verdict(mock_j, pro, con) -> None:
    mock_j.return_value = _verdict()
    result = run_debate(pro, con, max_rounds=3)
    assert isinstance(result.verdict, VerdictSchema)
    assert result.verdict.winner in {"PRO", "CON"}


@patch(_JUDGE)
def test_v1_anchor_set_on_both_agents_after_round_1(mock_j, pro, con) -> None:
    mock_j.return_value = _verdict()
    run_debate(pro, con, max_rounds=3)
    assert pro.v1_embedding is not None
    assert con.v1_embedding is not None


@patch(_JUDGE)
def test_ledger_truncation_preserves_v1_anchor(mock_j, pro, con) -> None:
    mock_j.return_value = _verdict()
    run_debate(pro, con, max_rounds=6)
    assert len(pro.get_windowed_ledger(3)) <= 3
    assert pro.v1_embedding is not None


@patch(_PIPE)
def test_run_benchmarks_returns_n_debate_results(mock_run) -> None:
    mock_run.return_value = _result()
    assert len(run_benchmarks(n=2)) == 2


@patch(_PIPE)
def test_debate_result_metrics_shape(mock_run) -> None:
    mock_run.return_value = _result(n=4)
    r = run_benchmarks(n=1, max_rounds=4)[0]
    assert len(r.latency_per_round) == 4
    assert r.tokens_per_debate > 0
    assert r.cost_per_debate > 0
    assert 0.0 <= r.context_cache_efficiency <= 1.0


def test_export_top_level_keys_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "debate_systems_research.json"
        BenchmarkReporter.export([_result()], p)
        data = json.loads(p.read_text())
        assert {"benchmark_metadata", "runs", "aggregates"} <= data.keys()


def test_export_aggregates_mean_tokens_per_debate() -> None:
    r1, r2 = _result(), _result()
    r1.tokens_per_debate, r2.tokens_per_debate = 1000, 3000
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "debate_systems_research.json"
        BenchmarkReporter.export([r1, r2], p)
        data = json.loads(p.read_text())
        assert data["aggregates"]["mean_tokens_per_debate"] == pytest.approx(2000.0)
