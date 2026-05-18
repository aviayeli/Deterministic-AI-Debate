"""Cost forecasting for benchmark runs."""
from __future__ import annotations

_COST_PER_1K_TOKENS: float = 0.01
_AVG_TOKENS_PER_CALL: int = 500
_CALLS_PER_ROUND: int = 2  # PRO + CON per round


def estimate_tokens(n_runs: int, max_rounds: int) -> int:
    return n_runs * max_rounds * _CALLS_PER_ROUND * _AVG_TOKENS_PER_CALL


def estimate_cost(n_runs: int, max_rounds: int) -> float:
    return estimate_tokens(n_runs, max_rounds) * _COST_PER_1K_TOKENS / 1000.0


def confirm_benchmark(n_runs: int, max_rounds: int) -> bool:
    tokens = estimate_tokens(n_runs, max_rounds)
    cost = estimate_cost(n_runs, max_rounds)
    print(f"  Estimated: ~{tokens:,} tokens | {n_runs} run(s) × {max_rounds} round(s) × 2 agents.")
    print(f"  Estimated cost ~${cost:.2f}.")
    try:
        raw = input("  Proceed? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return raw == "y"
