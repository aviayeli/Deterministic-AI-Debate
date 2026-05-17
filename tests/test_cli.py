"""Phase 6b — Interactive CLI: menu + handlers."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.debate.cli.handlers import (
    handle_generate_analysis,
    handle_run_benchmark,
    handle_run_single,
    handle_topic_selection,
    handle_view_results,
)
from src.debate.cli.menu import display_topics, parse_choice

_HANDLERS = "src.debate.cli.handlers"
_MENU = "src.debate.cli.menu"


def _sdk(topic: str = "Test Topic") -> MagicMock:
    sdk = MagicMock()
    sdk._topic = topic
    return sdk


# ── menu helpers ──────────────────────────────────────────────────────────────

def test_display_topics_prints_numbered_list(capsys) -> None:
    display_topics(["Alpha", "Beta"])
    out = capsys.readouterr().out
    assert "1." in out and "Alpha" in out
    assert "2." in out and "Beta" in out


def test_parse_choice_returns_valid_integer() -> None:
    assert parse_choice("2", max_val=3) == 2


def test_parse_choice_zero_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_choice("0", max_val=3)


def test_parse_choice_over_max_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_choice("4", max_val=3)


def test_parse_choice_non_integer_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_choice("abc", max_val=3)


# ── handlers ─────────────────────────────────────────────────────────────────

def test_handle_topic_selection_calls_set_topic() -> None:
    sdk = _sdk()
    with patch("builtins.input", return_value="1"):
        handle_topic_selection(sdk, ["Topic A", "Topic B"])
    sdk.set_topic.assert_called_once_with("Topic A")


def test_handle_topic_selection_invalid_input_leaves_topic_unchanged() -> None:
    sdk = _sdk("Original")
    with patch("builtins.input", return_value="999"):
        handle_topic_selection(sdk, ["Topic A"])
    sdk.set_topic.assert_not_called()


def test_handle_run_single_calls_sdk(capsys) -> None:
    sdk = _sdk()
    result = MagicMock()
    result.verdict.winner = "PRO"
    result.rounds = [MagicMock()] * 3
    sdk.run_single.return_value = result
    handle_run_single(sdk)
    sdk.run_single.assert_called_once()


def test_handle_run_benchmark_calls_sdk_with_n() -> None:
    sdk = _sdk()
    sdk.run_benchmark.return_value = [MagicMock()]
    with patch(f"{_HANDLERS}.BenchmarkReporter.export"):
        handle_run_benchmark(sdk, n=2)
    sdk.run_benchmark.assert_called_once_with(n=2)


def test_handle_generate_analysis_calls_sdk_when_file_exists() -> None:
    sdk = _sdk()
    sdk.generate_analysis.return_value = [Path("a.png")]
    with patch(f"{_HANDLERS}._OUTPUT_JSON") as mock_path:
        mock_path.exists.return_value = True
        handle_generate_analysis(sdk)
    sdk.generate_analysis.assert_called_once()


def test_handle_generate_analysis_skips_when_no_file(capsys) -> None:
    sdk = _sdk()
    with patch(f"{_HANDLERS}._OUTPUT_JSON") as mock_path:
        mock_path.exists.return_value = False
        result = handle_generate_analysis(sdk)
    sdk.generate_analysis.assert_not_called()
    assert result == []


def test_handle_view_results_prints_when_results_available(capsys) -> None:
    r = MagicMock()
    r.verdict.winner = "PRO"
    r.tokens_per_debate = 1000
    with patch(f"{_HANDLERS}._last_results", [r]):
        handle_view_results()
    out = capsys.readouterr().out
    assert "PRO" in out


def test_main_interactive_flag_triggers_run_loop() -> None:
    with (
        patch("sys.argv", ["main", "--interactive"]),
        patch("src.debate.cli.menu.run_loop") as mock_loop,
        patch("src.debate.sdk.anthropic.Anthropic"),
        patch("src.debate.sdk.ApiGatekeeper"),
        patch("src.debate.sdk.GatekeeperConfig.load"),
    ):
        from main import main
        main()
    mock_loop.assert_called_once()


def test_main_without_interactive_uses_benchmarks() -> None:
    with (
        patch("sys.argv", ["main", "--runs", "1", "--rounds", "3"]),
        patch("main.run_benchmarks", return_value=[]) as mock_bench,
        patch("main.BenchmarkReporter"),
    ):
        from main import main
        main()
    mock_bench.assert_called_once_with(n=1, max_rounds=3)
