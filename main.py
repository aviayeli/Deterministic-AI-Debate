import argparse

from src.debate.benchmarks.reporter import BenchmarkReporter
from src.debate.engine.pipeline import run_benchmarks


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic AI Debate Benchmark")
    parser.add_argument("--runs", type=int, default=5, help="Number of debate runs")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per debate")
    args = parser.parse_args()
    results = run_benchmarks(n=args.runs, max_rounds=args.rounds)
    BenchmarkReporter.export(results, "debate_systems_research.json")
    print(f"Done: {args.runs} runs x {args.rounds} rounds -> debate_systems_research.json")


if __name__ == "__main__":
    main()
