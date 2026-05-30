"""Phase 12 — Cost Forecasting: estimate_tokens, estimate_cost, confirm_benchmark."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.debate.cli.forecaster import confirm_benchmark, estimate_cost, estimate_tokens
from src.debate.cli.handlers import handle_run_benchmark

_HANDLERS = "src.debate.cli.handlers"


def test_estimate_tokens_scales_with_runs_and_rounds() -> None:
    assert estimate_tokens(n_runs=2, max_rounds=5) == 2 * 5 * 2 * 500


def test_estimate_tokens_zero_runs_is_zero() -> None:
    assert estimate_tokens(n_runs=0, max_rounds=10) == 0


def test_estimate_tokens_single_run_single_round() -> None:
    assert estimate_tokens(n_runs=1, max_rounds=1) == 1 * 1 * 2 * 500


def test_estimate_cost_matches_token_rate() -> None:
    tokens = estimate_tokens(n_runs=1, max_rounds=10)
    assert estimate_cost(n_runs=1, max_rounds=10) == pytest.approx(tokens * 0.01 / 1000)


def test_estimate_cost_zero_runs_is_zero() -> None:
    assert estimate_cost(n_runs=0, max_rounds=10) == 0.0


def test_estimate_cost_increases_with_scale() -> None:
    assert estimate_cost(n_runs=10, max_rounds=10) > estimate_cost(n_runs=1, max_rounds=10)


def test_confirm_benchmark_returns_true_on_y() -> None:
    with patch("builtins.input", return_value="y"):
        assert confirm_benchmark(n_runs=1, max_rounds=3) is True


def test_confirm_benchmark_returns_true_on_capital_y() -> None:
    with patch("builtins.input", return_value="Y"):
        assert confirm_benchmark(n_runs=1, max_rounds=3) is True


def test_confirm_benchmark_returns_false_on_n() -> None:
    with patch("builtins.input", return_value="n"):
        assert confirm_benchmark(n_runs=1, max_rounds=3) is False


def test_confirm_benchmark_returns_false_on_capital_n() -> None:
    with patch("builtins.input", return_value="N"):
        assert confirm_benchmark(n_runs=1, max_rounds=3) is False


def test_confirm_benchmark_returns_false_on_empty_enter() -> None:
    with patch("builtins.input", return_value=""):
        assert confirm_benchmark(n_runs=1, max_rounds=3) is False


def test_confirm_benchmark_returns_false_on_eoferror() -> None:
    with patch("builtins.input", side_effect=EOFError):
        assert confirm_benchmark(n_runs=1, max_rounds=3) is False


def test_confirm_benchmark_displays_cost_estimate(capsys) -> None:
    with patch("builtins.input", return_value="n"):
        confirm_benchmark(n_runs=5, max_rounds=10)
    assert "$" in capsys.readouterr().out


def test_confirm_benchmark_displays_token_count(capsys) -> None:
    with patch("builtins.input", return_value="n"):
        confirm_benchmark(n_runs=2, max_rounds=5)
    assert "token" in capsys.readouterr().out.lower()


def test_handle_run_benchmark_aborts_on_rejection() -> None:
    sdk = MagicMock()
    with (
        patch(f"{_HANDLERS}.confirm_benchmark", return_value=False),
        patch(f"{_HANDLERS}.BenchmarkReporter.export"),
    ):
        result = handle_run_benchmark(sdk, n=3)
    sdk.run_benchmark.assert_not_called()
    assert result == []


def test_handle_run_benchmark_proceeds_on_confirmation() -> None:
    sdk = MagicMock()
    sdk.run_benchmark.return_value = [MagicMock()]
    with (
        patch(f"{_HANDLERS}.confirm_benchmark", return_value=True),
        patch(f"{_HANDLERS}.BenchmarkReporter.export"),
    ):
        result = handle_run_benchmark(sdk, n=3)
    sdk.run_benchmark.assert_called_once_with(n=3)
    assert len(result) == 1
