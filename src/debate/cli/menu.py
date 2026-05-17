"""Interactive terminal menu for the Debate CLI."""
from __future__ import annotations

import json
from pathlib import Path

_TOPICS_CONFIG = Path(__file__).parents[3] / "config" / "topics.json"

_BANNER = """
╔══════════════════════════════════════╗
║   Deterministic AI Debate System     ║
╠══════════════════════════════════════╣
║  1. Select debate topic              ║
║  2. Run single debate                ║
║  3. Run benchmark (N runs)           ║
║  4. View last benchmark results      ║
║  5. Generate analysis graphs         ║
║  6. Exit                             ║
╚══════════════════════════════════════╝"""


def load_topics() -> list[str]:
    data = json.loads(_TOPICS_CONFIG.read_text())
    return data["topics"]


def display_menu() -> None:
    print(_BANNER)


def display_topics(topics: list[str]) -> None:
    print("\nAvailable topics:")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. {t}")


def parse_choice(raw: str, max_val: int) -> int:
    try:
        val = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Expected an integer, got: {raw!r}") from exc
    if not (1 <= val <= max_val):
        raise ValueError(f"Choice {val} out of range [1, {max_val}]")
    return val


def run_loop(sdk: object | None = None) -> None:
    from ..sdk import DebateSDK
    from .handlers import (
        handle_generate_analysis,
        handle_run_benchmark,
        handle_run_single,
        handle_topic_selection,
        handle_view_results,
    )

    topics = load_topics()
    if sdk is None:
        sdk = DebateSDK()

    while True:
        display_menu()
        try:
            raw = input("Enter choice [1-6]: ")
            choice = parse_choice(raw, max_val=6)
        except (ValueError, EOFError):
            print("  Invalid input — enter a number 1-6.")
            continue

        if choice == 1:
            handle_topic_selection(sdk, topics)
        elif choice == 2:
            handle_run_single(sdk)
        elif choice == 3:
            handle_run_benchmark(sdk)
        elif choice == 4:
            handle_view_results()
        elif choice == 5:
            handle_generate_analysis(sdk)
        elif choice == 6:
            print("Goodbye.")
            break
