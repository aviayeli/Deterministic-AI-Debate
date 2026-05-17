"""Phase 6d — Data visualization: generate_all()."""
import json
from pathlib import Path

import pytest

from src.debate.analysis import generate_all

_SAMPLE = {
    "benchmark_metadata": {"timestamp": "2026-01-01T00:00:00+00:00", "n_runs": 2},
    "runs": [
        {
            "tokens_per_debate": 1000,
            "cost_per_debate": 0.01,
            "context_cache_efficiency": 0.8,
            "latency_per_round": [0.1, 0.2, 0.3],
            "winner": "PRO",
        },
        {
            "tokens_per_debate": 1500,
            "cost_per_debate": 0.015,
            "context_cache_efficiency": 0.9,
            "latency_per_round": [0.15, 0.25, 0.35],
            "winner": "CON",
        },
    ],
    "aggregates": {"mean_tokens_per_debate": 1250},
}

_EXPECTED_FILES = {
    "latency_per_round.png",
    "tokens_per_run.png",
    "cache_efficiency.png",
    "winner_distribution.png",
}


@pytest.fixture()
def json_file(tmp_path: Path) -> Path:
    p = tmp_path / "debate_systems_research.json"
    p.write_text(json.dumps(_SAMPLE))
    return p


def test_generate_all_returns_four_paths(json_file, tmp_path):
    paths = generate_all(json_file, tmp_path / "assets")
    assert len(paths) == 4


def test_all_returned_paths_exist_on_disk(json_file, tmp_path):
    paths = generate_all(json_file, tmp_path / "assets")
    assert all(p.exists() for p in paths)


def test_returned_filenames_match_expected(json_file, tmp_path):
    paths = generate_all(json_file, tmp_path / "assets")
    assert {p.name for p in paths} == _EXPECTED_FILES


def test_generate_all_creates_out_dir_if_missing(tmp_path, json_file):
    out_dir = tmp_path / "nested" / "assets"
    assert not out_dir.exists()
    generate_all(json_file, out_dir)
    assert out_dir.exists()


def test_raises_file_not_found_for_missing_json(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate_all(tmp_path / "missing.json", tmp_path / "out")


def test_raises_key_error_if_runs_key_missing(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"benchmark_metadata": {}}))
    with pytest.raises(KeyError):
        generate_all(bad, tmp_path / "out")


def test_format_from_config_is_png(json_file, tmp_path):
    paths = generate_all(json_file, tmp_path / "assets")
    assert all(p.suffix == ".png" for p in paths)


def test_dpi_from_config_not_zero(json_file, tmp_path):
    paths = generate_all(json_file, tmp_path / "assets")
    assert all(p.stat().st_size > 0 for p in paths)


def test_single_run_does_not_crash(tmp_path):
    single = {**_SAMPLE, "runs": [_SAMPLE["runs"][0]]}
    p = tmp_path / "single.json"
    p.write_text(json.dumps(single))
    paths = generate_all(p, tmp_path / "assets")
    assert len(paths) == 4


def test_five_runs_produce_correct_number_of_graphs(tmp_path):
    runs = [
        {
            "tokens_per_debate": i * 100,
            "cost_per_debate": i * 0.001,
            "context_cache_efficiency": 0.5,
            "latency_per_round": [0.1] * 10,
            "winner": "PRO" if i % 2 == 0 else "CON",
        }
        for i in range(1, 6)
    ]
    data = {**_SAMPLE, "runs": runs}
    p = tmp_path / "five.json"
    p.write_text(json.dumps(data))
    paths = generate_all(p, tmp_path / "assets")
    assert len(paths) == 4
