"""Data visualization for debate benchmark results."""
import contextlib
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_VIZ_CONFIG = Path(__file__).parents[2] / "config" / "visualization_config.json"
_LINE_ALPHA: float = 0.4  # per-run trace opacity in latency chart


@dataclass
class _VizConfig:
    assets_dir: str
    dpi: int
    format: str
    style: str
    figsize: list

    @classmethod
    def load(cls, path: Path = _VIZ_CONFIG) -> "_VizConfig":
        data = json.loads(path.read_text())
        return cls(**data)


def _apply_style(style: str) -> None:
    with contextlib.suppress(OSError):
        plt.style.use(style)


def _plot_latency(runs: list[dict], out_dir: Path, cfg: "_VizConfig") -> Path:
    fig, ax = plt.subplots(figsize=cfg.figsize)
    for run in runs:
        lat = run["latency_per_round"]
        ax.plot(range(1, len(lat) + 1), lat, alpha=_LINE_ALPHA, color="steelblue")
    max_len = max(len(r["latency_per_round"]) for r in runs)
    means = [
        sum(
            r["latency_per_round"][i]
            for r in runs
            if i < len(r["latency_per_round"])
        )
        / sum(1 for r in runs if i < len(r["latency_per_round"]))
        for i in range(max_len)
    ]
    ax.plot(range(1, max_len + 1), means, color="steelblue", linewidth=2, label="Mean")
    ax.set(xlabel="Round", ylabel="Latency (s)", title="Latency per Round")
    ax.legend()
    p = out_dir / f"latency_per_round.{cfg.format}"
    fig.savefig(p, dpi=cfg.dpi, bbox_inches="tight")
    plt.close(fig)
    return p


def _plot_tokens(runs: list[dict], out_dir: Path, cfg: "_VizConfig") -> Path:
    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.bar(
        range(1, len(runs) + 1),
        [r["tokens_per_debate"] for r in runs],
        color="steelblue",
    )
    ax.set(xlabel="Run", ylabel="Tokens", title="Token Usage per Run")
    p = out_dir / f"tokens_per_run.{cfg.format}"
    fig.savefig(p, dpi=cfg.dpi, bbox_inches="tight")
    plt.close(fig)
    return p


def _plot_cache(runs: list[dict], out_dir: Path, cfg: "_VizConfig") -> Path:
    fig, ax = plt.subplots(figsize=cfg.figsize)
    ax.bar(
        range(1, len(runs) + 1),
        [r["context_cache_efficiency"] for r in runs],
        color="coral",
    )
    ax.set(xlabel="Run", ylabel="Cache Efficiency", title="Cache Efficiency per Run")
    ax.set_ylim(0, 1)
    p = out_dir / f"cache_efficiency.{cfg.format}"
    fig.savefig(p, dpi=cfg.dpi, bbox_inches="tight")
    plt.close(fig)
    return p


def _plot_winners(runs: list[dict], out_dir: Path, cfg: "_VizConfig") -> Path:
    fig, ax = plt.subplots(figsize=cfg.figsize)
    winners = [r["winner"] for r in runs]
    counts = {w: winners.count(w) for w in dict.fromkeys(winners)}
    colors = ["steelblue", "coral", "mediumseagreen"][: len(counts)]
    ax.pie(list(counts.values()), labels=list(counts.keys()), autopct="%1.0f%%",
           colors=colors)
    ax.set_title("Winner Distribution")
    p = out_dir / f"winner_distribution.{cfg.format}"
    fig.savefig(p, dpi=cfg.dpi, bbox_inches="tight")
    plt.close(fig)
    return p


def generate_all(json_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Load benchmark JSON and write 4 analysis graphs to out_dir."""
    json_path = Path(json_path)
    out_dir = Path(out_dir)
    if not json_path.exists():
        raise FileNotFoundError(f"Benchmark JSON not found: {json_path}")
    data = json.loads(json_path.read_text())
    runs = data["runs"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = _VizConfig.load()
    _apply_style(cfg.style)
    return [
        _plot_latency(runs, out_dir, cfg),
        _plot_tokens(runs, out_dir, cfg),
        _plot_cache(runs, out_dir, cfg),
        _plot_winners(runs, out_dir, cfg),
    ]
