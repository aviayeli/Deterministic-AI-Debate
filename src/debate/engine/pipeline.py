"""Debate execution pipeline: single-debate orchestration and multithreaded benchmark runner."""
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import anthropic
from rich.progress import Progress

from ..agents.base import BaseAgent
from ..config import settings
from ..evaluation.judge import Judge
from ..evaluation.responsiveness import ResponsivenessCalculator
from ..events.bus import EventBus
from ..events.types import (
    AgentReplyEvent,
    BeforeEvaluationEvent,
    DebateEndEvent,
    DebateStartEvent,
    RoundEndEvent,
    RoundStartEvent,
)
from ..gatekeeper import ApiGatekeeper
from ..gatekeeper.config import GatekeeperConfig
from ..logging import get_logger
from ..schemas.round import LedgerEntry, RoundSchema
from ..schemas.verdict import VerdictSchema
from .agents_factory import make_agents
from .embeddings import EmbeddingService

_log = get_logger("pipeline")


@dataclass
class DebateResult:
    rounds: list[RoundSchema]
    verdict: VerdictSchema
    latency_per_round: list[float]
    tokens_per_debate: int
    cost_per_debate: float
    context_cache_efficiency: float


def run_debate(
    pro_agent: BaseAgent,
    con_agent: BaseAgent,
    max_rounds: int = 10,
    bus: EventBus | None = None,
    topic: str | None = None,
) -> DebateResult:
    _bus = bus or EventBus()
    emb = EmbeddingService()
    resp = ResponsivenessCalculator()
    rounds: list[RoundSchema] = []
    latencies: list[float] = []
    _log.info(f"Debate started | max_rounds={max_rounds}")
    _bus.emit("on_debate_start", DebateStartEvent(topic=topic, max_rounds=max_rounds))

    for rn in range(1, max_rounds + 1):
        t0 = time.perf_counter()
        _bus.emit("on_round_start", RoundStartEvent(rn, max_rounds))

        pro_opp = con_agent.get_windowed_ledger(settings.LEDGER_WINDOW)
        pro_claim = pro_agent.generate_claim(rn, pro_opp)
        pro_emb = emb.embed(pro_claim.claim_text)
        _bus.emit("on_agent_reply", AgentReplyEvent("PRO", rn, pro_claim))

        con_opp = pro_agent.get_windowed_ledger(settings.LEDGER_WINDOW)
        con_claim = con_agent.generate_claim(rn, con_opp)
        con_emb = emb.embed(con_claim.claim_text)
        _bus.emit("on_agent_reply", AgentReplyEvent("CON", rn, con_claim))

        if rn == 1:
            pro_agent.set_v1_embedding(pro_emb)
            con_agent.set_v1_embedding(con_emb)

        pro_agent.add_to_ledger(LedgerEntry(claim=pro_claim, embedding=pro_emb))
        con_agent.add_to_ledger(LedgerEntry(claim=con_claim, embedding=con_emb))

        round_schema = RoundSchema(
            round_number=rn,
            pro_claim=pro_claim,
            con_claim=con_claim,
            responsiveness_score_pro=resp.calculate(pro_claim, pro_opp),
            responsiveness_score_con=resp.calculate(con_claim, con_opp),
        )
        rounds.append(round_schema)
        latency = time.perf_counter() - t0
        latencies.append(latency)
        _log.info(f"Round {rn}/{max_rounds} complete | lat={latency:.3f}s")
        _bus.emit("on_round_end", RoundEndEvent(rn, round_schema, latency))

    _bus.emit("before_evaluation", BeforeEvaluationEvent(rounds))
    debate_id = str(uuid.uuid4())
    verdict = Judge().evaluate_debate(rounds, pro_agent, con_agent, debate_id)
    _log.info(f"Verdict | winner={verdict.winner} | tiebreaker={verdict.tiebreaker_used}")

    total_tokens = sum(getattr(a, "_tokens", 0) for a in [pro_agent, con_agent])
    total_calls = max_rounds * 2
    cache_hits = sum(getattr(a, "_cache_hits", 0) for a in [pro_agent, con_agent])

    result = DebateResult(
        rounds=rounds,
        verdict=verdict,
        latency_per_round=latencies,
        tokens_per_debate=total_tokens,
        cost_per_debate=total_tokens * 3e-6,
        context_cache_efficiency=cache_hits / total_calls if total_calls else 0.0,
    )
    _bus.emit("on_debate_end", DebateEndEvent(result))
    return result


def _collect_with_progress(futures: list, n: int) -> list[DebateResult]:
    from rich.progress import BarColumn, SpinnerColumn, TaskProgressColumn, TextColumn
    results: list[DebateResult] = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), TaskProgressColumn()) as prog:
        task = prog.add_task(f"Benchmarking {n} debates...", total=n)
        for f in as_completed(futures):
            results.append(f.result())
            prog.advance(task)
    return results


def run_benchmarks(
    n: int = 5, max_rounds: int = 10, topic: str | None = None
) -> list[DebateResult]:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    gk_config = GatekeeperConfig.load()
    gk = ApiGatekeeper(client, gk_config)
    max_workers = gk_config.max_workers
    _log.info(f"Benchmark | n={n} | rounds={max_rounds} | workers={max_workers}")

    def _single() -> DebateResult:
        return run_debate(*make_agents(gk, topic), max_rounds)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_single) for _ in range(n)]
        if sys.stdout.isatty():
            results = _collect_with_progress(futures, n)
        else:
            results = [f.result() for f in as_completed(futures)]

    _log.info(f"Benchmark complete | runs={n}")
    return results
