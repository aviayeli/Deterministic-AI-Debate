"""Phase 6c — Multithreaded benchmark orchestration."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from unittest.mock import patch

import pytest

from src.debate.engine.pipeline import DebateResult, run_benchmarks
from src.debate.gatekeeper.config import GatekeeperConfig
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import RoundSchema
from src.debate.schemas.verdict import VerdictSchema

_PIPE = "src.debate.engine.pipeline.run_debate"
_GK = "src.debate.engine.pipeline.ApiGatekeeper"
_EXEC = "src.debate.engine.pipeline.ThreadPoolExecutor"


def _verdict() -> VerdictSchema:
    return VerdictSchema(
        winner="PRO", pro_score=0.7, con_score=0.5, tiebreaker_used=None,
        evidence_quality_pro=0.8, evidence_quality_con=0.6,
        v1_distance_pro=0.1, v1_distance_con=0.2,
        responsiveness_pro=0.9, responsiveness_con=0.7,
        reasoning="stub",
    )


def _c(stance: Literal["PRO", "CON"], rn: int) -> ClaimPayloadSchema:
    return ClaimPayloadSchema(
        agent_id=stance, round_number=rn, stance=stance,
        claim_text="x", addressed_claim_ids=[],
    )


def _result(n: int = 3) -> DebateResult:
    return DebateResult(
        rounds=[
            RoundSchema(round_number=i + 1, pro_claim=_c("PRO", i + 1),
                        con_claim=_c("CON", i + 1),
                        responsiveness_score_pro=1.0, responsiveness_score_con=1.0)
            for i in range(n)
        ],
        verdict=_verdict(), latency_per_round=[0.1] * n,
        tokens_per_debate=500, cost_per_debate=0.005, context_cache_efficiency=0.8,
    )


@patch(_PIPE, return_value=None)
def test_run_benchmarks_returns_n_results(mock_run) -> None:
    mock_run.return_value = _result()
    assert len(run_benchmarks(n=3)) == 3


@patch(_PIPE)
def test_results_returned_regardless_of_completion_order(mock_run) -> None:
    call_order = []

    def _ordered(*args, **kwargs):
        call_order.append(len(call_order))
        return _result()

    mock_run.side_effect = _ordered
    results = run_benchmarks(n=4)
    assert len(results) == 4


@patch(_PIPE, return_value=None)
@patch(_EXEC, wraps=ThreadPoolExecutor)
def test_executor_receives_max_workers_from_config(mock_exec, mock_run) -> None:
    mock_run.return_value = _result()
    cfg = GatekeeperConfig.load()
    run_benchmarks(n=1)
    mock_exec.assert_called_once_with(max_workers=cfg.max_workers)


@patch(_PIPE, return_value=None)
def test_max_workers_not_hardcoded_in_pipeline(mock_run) -> None:
    mock_run.return_value = _result()
    cfg = GatekeeperConfig.load()
    with patch("src.debate.engine.pipeline.GatekeeperConfig.load", return_value=cfg) as m:
        run_benchmarks(n=1)
    m.assert_called_once()


@patch(_PIPE, side_effect=RuntimeError("api failure"))
def test_worker_exception_is_reraised(mock_run) -> None:
    with pytest.raises(RuntimeError, match="api failure"):
        run_benchmarks(n=1)


@patch(_GK)
@patch(_PIPE)
def test_gatekeeper_instantiated_exactly_once(mock_run, mock_gk_class) -> None:
    mock_run.return_value = _result()
    run_benchmarks(n=3)
    assert mock_gk_class.call_count == 1


@patch(_PIPE)
def test_no_deadlock_with_concurrent_workers(mock_run) -> None:
    call_count = 0
    lock = threading.Lock()

    def _fast(*args, **kwargs):
        nonlocal call_count
        time.sleep(0.01)
        with lock:
            call_count += 1
        return _result()

    mock_run.side_effect = _fast
    results = run_benchmarks(n=4)
    assert len(results) == 4
    assert call_count == 4
