"""Phase 9 — rich progress bar TTY guard and CLI entry point."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

_PIPELINE = "src.debate.engine.pipeline"
_ISATTY = "sys.stdout.isatty"
_PROGRESS = f"{_PIPELINE}.Progress"
_RUN = f"{_PIPELINE}.run_debate"
_ANTH = f"{_PIPELINE}.anthropic.Anthropic"
_GK = f"{_PIPELINE}.ApiGatekeeper"
_GK_CFG = f"{_PIPELINE}.GatekeeperConfig.load"


def _make_result():
    from src.debate.engine.pipeline import DebateResult
    from src.debate.schemas.verdict import VerdictSchema

    v = VerdictSchema(
        winner="PRO", pro_score=0.7, con_score=0.5, tiebreaker_used=None,
        evidence_quality_pro=0.8, evidence_quality_con=0.6,
        v1_distance_pro=0.1, v1_distance_con=0.2,
        responsiveness_pro=0.9, responsiveness_con=0.7, reasoning="s",
    )
    return DebateResult([], v, [], 0, 0.0, 0.0)


@patch(_ANTH)
@patch(_GK)
@patch(_GK_CFG)
@patch(_RUN)
@patch(_ISATTY, return_value=False)
def test_no_progress_bar_when_not_tty(mock_tty, mock_run, mock_cfg, mock_gk, mock_a):
    mock_run.return_value = _make_result()
    mock_cfg.return_value.max_workers = 2
    from src.debate.engine.pipeline import run_benchmarks

    with patch(_PROGRESS) as mock_prog:
        run_benchmarks(n=1, max_rounds=1)
    mock_prog.assert_not_called()


@patch(_ANTH)
@patch(_GK)
@patch(_GK_CFG)
@patch(_RUN)
@patch(_ISATTY, return_value=True)
def test_progress_bar_shown_when_tty(mock_tty, mock_run, mock_cfg, mock_gk, mock_a):
    mock_run.return_value = _make_result()
    mock_cfg.return_value.max_workers = 2
    mock_ctx = MagicMock()
    mock_ctx.add_task.return_value = 0
    from src.debate.engine.pipeline import run_benchmarks

    with patch(_PROGRESS) as mock_prog:
        mock_prog.return_value.__enter__.return_value = mock_ctx
        mock_prog.return_value.__exit__.return_value = False
        run_benchmarks(n=1, max_rounds=1)
    mock_prog.assert_called_once()


def test_entry_point_main_is_callable() -> None:
    from src.debate.cli.entry import main

    assert callable(main)
