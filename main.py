import argparse

from src.debate.sdk import DebateSDK


def main() -> None:
    p = argparse.ArgumentParser(description="Deterministic AI Debate Benchmark")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--rounds", type=int, default=10)
    p.add_argument("--interactive", action="store_true")
    if (args := p.parse_args()).interactive:
        from src.debate.cli.menu import run_loop
        run_loop()
        return
    sdk = DebateSDK()
    sdk.export(sdk.run_benchmark(n=args.runs, max_rounds=args.rounds), "debate_systems_research.json")


if __name__ == "__main__":
    main()
