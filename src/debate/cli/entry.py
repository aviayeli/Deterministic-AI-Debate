"""Entry point for the `debate` console script."""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    from ..sdk import DebateSDK
    from .menu import run_loop

    parser = argparse.ArgumentParser(description="Deterministic AI Debate System")
    parser.add_argument("--topic", default=None, help="Override the debate topic")
    args = parser.parse_args()
    sdk = DebateSDK(topic=args.topic)
    try:
        run_loop(sdk=sdk)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
