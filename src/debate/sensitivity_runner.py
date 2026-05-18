"""Hyperparameter sensitivity analysis — Section 9.1.

Sweeps (temperature × max_rounds) and collects debate metrics to quantify
how parameter changes affect context truncation and tiebreaker frequency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import settings
from .engine.pipeline import DebateResult, run_debate


@dataclass
class SensitivityConfig:
    temperatures: list[float] = field(default_factory=lambda: [0.0, 0.5, 1.0])
    max_rounds_values: list[int] = field(default_factory=lambda: [2, 5, 10])
    runs_per_config: int = 1


@dataclass
class SensitivityResult:
    temperature: float
    max_rounds: int
    tiebreaker_count: int
    context_truncation_count: int
    mean_tokens: float
    run_count: int


class SensitivityRunner:
    """Sweeps temperature × max_rounds and collects aggregate debate metrics."""

    def __init__(self, gatekeeper: Any, config: SensitivityConfig | None = None) -> None:
        self._gk = gatekeeper
        self._cfg = config or SensitivityConfig()

    def run(self) -> list[SensitivityResult]:
        return [
            self._run_config(temp, rounds)
            for temp in self._cfg.temperatures
            for rounds in self._cfg.max_rounds_values
        ]

    def _run_config(self, temperature: float, max_rounds: int) -> SensitivityResult:
        from .agents.con import ConAgent
        from .agents.pro import ProAgent

        tiebreakers = 0
        truncations = 0
        total_tokens = 0
        n = self._cfg.runs_per_config
        for _ in range(n):
            result = run_debate(ProAgent(self._gk), ConAgent(self._gk), max_rounds=max_rounds)
            if result.verdict.tiebreaker_used:
                tiebreakers += 1
            total_tokens += result.tokens_per_debate
            truncations += _count_truncations(result)
        return SensitivityResult(
            temperature=temperature,
            max_rounds=max_rounds,
            tiebreaker_count=tiebreakers,
            context_truncation_count=truncations,
            mean_tokens=total_tokens / n,
            run_count=n,
        )


def _count_truncations(result: DebateResult) -> int:
    """Number of rounds where the opponent's context view was windowed."""
    return max(0, len(result.rounds) - settings.LEDGER_WINDOW)
