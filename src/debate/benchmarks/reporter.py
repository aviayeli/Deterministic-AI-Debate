import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from src.debate.engine.pipeline import DebateResult


class BenchmarkReporter:
    @staticmethod
    def export(results: list[DebateResult], path: Path | str) -> None:
        path = Path(path)
        data = {
            "benchmark_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "n_runs": len(results),
            },
            "runs": [
                {
                    "tokens_per_debate": r.tokens_per_debate,
                    "cost_per_debate": r.cost_per_debate,
                    "context_cache_efficiency": r.context_cache_efficiency,
                    "latency_per_round": r.latency_per_round,
                    "winner": r.verdict.winner,
                }
                for r in results
            ],
            "aggregates": {
                "mean_tokens_per_debate": mean(
                    r.tokens_per_debate for r in results
                ),
                "mean_cost_per_debate": mean(r.cost_per_debate for r in results),
                "mean_cache_efficiency": mean(
                    r.context_cache_efficiency for r in results
                ),
                "mean_latency_per_round": mean(
                    sum(r.latency_per_round) / len(r.latency_per_round)
                    for r in results
                    if r.latency_per_round
                ),
            },
        }
        path.write_text(json.dumps(data, indent=2))
