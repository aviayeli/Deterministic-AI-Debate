import argparse

from src.debate.benchmarks.reporter import BenchmarkReporter
from src.debate.engine.pipeline import run_benchmarks
from src.debate.logging import get_logger


def main() -> None:
    p = argparse.ArgumentParser(description="Deterministic AI Debate Benchmark")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--interactive", action="store_true")
    if (args := p.parse_args()).interactive:
        from src.debate.cli.menu import run_loop
        run_loop()
        return
    BenchmarkReporter.export(run_benchmarks(n=args.runs, max_rounds=args.rounds), "debate_systems_research.json")
    get_logger("main").info(f"Done: {args.runs} x {args.rounds} rounds")
if __name__ == "__main__":
    main()
