"""Public SDK surface for the Deterministic AI Debate system."""
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic

from . import analysis
from .agents.con import ConAgent
from .agents.pro import ProAgent
from .benchmarks.reporter import BenchmarkReporter
from .config import settings
from .engine.pipeline import DebateResult, run_benchmarks, run_debate
from .events.bus import EventBus
from .gatekeeper import ApiGatekeeper
from .gatekeeper.config import GatekeeperConfig

_TOPICS_CONFIG = Path(__file__).parents[2] / "config" / "topics.json"


def _load_default_topic() -> str:
    data = json.loads(_TOPICS_CONFIG.read_text())
    default = data.get("default", "")
    if not default:
        raise ValueError("No default topic configured in topics.json")
    return default


class DebateSDK:
    def __init__(self, topic: str | None = None) -> None:
        self._topic: str = topic if topic is not None else _load_default_topic()
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._gk = ApiGatekeeper(client, GatekeeperConfig.load())
        self._bus = EventBus()

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        """Register a plugin hook for a debate lifecycle event."""
        self._bus.on(event, handler)

    def set_topic(self, topic: str) -> None:
        self._topic = topic

    def run_single(self, max_rounds: int = 10) -> DebateResult:
        pro = ProAgent(self._gk, topic=self._topic)
        con = ConAgent(self._gk, topic=self._topic)
        return run_debate(pro, con, max_rounds, bus=self._bus, topic=self._topic)

    def run_benchmark(self, n: int = 5, max_rounds: int = 10) -> list[DebateResult]:
        return run_benchmarks(n=n, max_rounds=max_rounds, topic=self._topic)

    def export(self, results: list[DebateResult], path: str | Path) -> Path:
        path = Path(path)
        BenchmarkReporter.export(results, path)
        return path

    def generate_analysis(
        self, json_path: str | Path, out_dir: str | Path
    ) -> list[Path]:
        return analysis.generate_all(json_path, out_dir)
