"""CLI action handlers — each delegates to DebateSDK."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..benchmarks.reporter import BenchmarkReporter
from .menu import display_topics, parse_choice

if TYPE_CHECKING:
    from ..engine.pipeline import DebateResult
    from ..sdk import DebateSDK

_OUTPUT_JSON = Path("debate_systems_research.json")
_ASSETS_DIR = Path("assets/")
_last_results: list[DebateResult] = []


def handle_topic_selection(sdk: DebateSDK, topics: list[str]) -> None:
    display_topics(topics)
    try:
        idx = parse_choice(input("Select topic number: "), max_val=len(topics))
    except (ValueError, EOFError):
        print("  Invalid selection; topic unchanged.")
        return
    sdk.set_topic(topics[idx - 1])
    print(f"  Topic set to: {sdk._topic}")


def handle_run_single(sdk: DebateSDK) -> DebateResult:
    print(f"  Running debate: '{sdk._topic}' ...")
    result = sdk.run_single()
    print(f"  Winner: {result.verdict.winner} | Rounds: {len(result.rounds)}")
    return result


def handle_run_benchmark(sdk: DebateSDK, n: int | None = None) -> list[DebateResult]:
    global _last_results
    if n is None:
        try:
            raw = input("Number of runs [5]: ").strip()
            n = int(raw) if raw else 5
        except (ValueError, EOFError):
            n = 5
    print(f"  Running benchmark: {n} debates ...")
    results = sdk.run_benchmark(n=n)
    BenchmarkReporter.export(results, _OUTPUT_JSON)
    _last_results = results
    print(f"  Done. Results saved to {_OUTPUT_JSON}")
    return results


def handle_view_results() -> None:
    if not _last_results:
        print("  No results yet — run a benchmark first.")
        return
    for i, r in enumerate(_last_results, 1):
        print(f"  Run {i}: winner={r.verdict.winner} | tokens={r.tokens_per_debate}")


def handle_generate_analysis(sdk: DebateSDK) -> list[Path]:
    if not _OUTPUT_JSON.exists():
        print(f"  No benchmark file at {_OUTPUT_JSON} — run a benchmark first.")
        return []
    paths = sdk.generate_analysis(_OUTPUT_JSON, _ASSETS_DIR)
    print(f"  Generated {len(paths)} graphs in {_ASSETS_DIR}")
    return paths
