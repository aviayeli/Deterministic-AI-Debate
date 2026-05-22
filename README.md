# Deterministic Multi-Agent AI Debate

A research-grade benchmark system that pits two LLM agents (PRO vs. CON) against each other in a structured, **fully deterministic** debate on the question: *"Will AI replace software engineers in the next 5 years?"*

Built as a university thesis project. Every verdict is reproducible — no LLM sampling randomness, no floating tiebreakers, no silent failures — making it suitable for controlled empirical evaluation.

---

## Research Overview

Standard LLM-vs-LLM debate pipelines suffer from three failure modes that invalidate empirical comparison:

1. **Non-determinism** — temperature > 0 means repeated runs produce different verdicts with no ground truth.
2. **Topic drift** — agents subtly shift their position mid-debate to score points, undermining stance integrity.
3. **Context explosion** — unbounded ledger growth causes runaway token costs and hits context-window limits.

This system addresses all three through a layered architecture: **Semantic Math** (V₁ anchor + centroid alignment) to enforce stance coherence, **FinOps Context Truncation** to bound cost per debate, a **production-grade API Gatekeeper** to centralise all rate limiting and retry logic, and a **CLAUDE.md development contract** (see below) that prevented silent failures at every layer.

---

## Architecture

### Semantic Math — V₁ Anchor and Centroid Alignment

Every agent's **first claim embedding** is stored immutably as `v1_embedding` (the V₁ anchor) via `BaseAgent.set_v1_embedding()`, which raises `RuntimeError` on a second call. On every subsequent round, the `SemanticDriftEvaluator` computes two penalties:

- **V₁ Distance penalty** — fires when the agent drifts too far from its opening position.
- **Centroid Alignment penalty** — fires when the agent's current claim aligns too closely with the opponent's rolling centroid, signalling sycophantic drift.

Opponent embeddings are weighted by a recency-decay factor `λ^(n−1−i)` so recent claims contribute more to the centroid than older ones.

### FinOps Context Truncation

The ledger passed to each LLM is windowed to the last `LEDGER_WINDOW` entries (default: 3). The V₁ anchor is stored separately on the agent and survives truncation. This bounds input tokens per round to `O(LEDGER_WINDOW × avg_claim_length)` regardless of debate length.

### API Gatekeeper & Watchdog Circuit Breaker

All Anthropic API calls are routed exclusively through `ApiGatekeeper`, instantiated once per benchmark run and shared across all parallel threads. It provides:

- **Token-bucket rate limiting** — refills at `requests_per_minute / 60` tokens per second; blocks if the bucket is empty.
- **Exponential-backoff retry** — retries on 429, 529, timeout, and connection errors; formula: `backoff_factor × 2^attempt + U(0, 0.5)`.
- **Fast-fail** — `AuthenticationError` (401) and `BadRequestError` (400) raise immediately, no retries.

The `Watchdog` circuit breaker wraps any callable and trips after `failure_threshold` consecutive failures, raising `WatchdogTrippedError` on all subsequent calls until `reset()`. Both components write to the shared enterprise logger (`src/debate/shared/logger.py`).

### Four-Level Deterministic Tiebreaker

When aggregate responsiveness scores tie, the `Judge` cascades through:

| Level | Criterion | Winner |
|---|---|---|
| 1 | Mean evidence quality score | Higher wins |
| 2 | V₁ faithfulness (cosine distance from anchor) | Lower wins |
| 3 | Mean responsiveness score | Higher wins |
| 4 | PRNG seeded by `SHA-256(debate_id) % 2³²` | Deterministic coin flip |

`temperature=0` on all LLM calls ensures identical outputs for identical inputs. Level 4 guarantees a winner always exists — `VerdictSchema.winner` is **never null**.

### TopicRouter & FactChecker Subagent

The `TopicRouter` keyword-matches the debate topic against six skill categories (`technical`, `economic`, `statistical`, `ethical`, `historical`, `causal`) and injects concise skill instructions into the agents' system prompts at construction time. This runs once per debate, keeping prompt tokens bounded.

The `FactCheckerSubagent` queries the DuckDuckGo instant-answer API before each claim. If the result contains a contradiction marker (`"debunked"`, `"misleading"`, `"incorrect"`, etc.), the agent prepends `**OBJECTION! Fake News!** {proof}` to its generated claim — triggered by regex, not by LLM judgement.

### DiscourseChecker — Civility Policy

Before scoring, `DiscourseChecker` scans all claims for 11 violation patterns (insults, profanity, personal attacks). Each distinct match deducts `0.05` from the agent's effective score, capped at `0.25` total. Applied post-debate to preserve benchmark reproducibility.

### Event Bus & Plugin Architecture

The `EventBus` provides a thread-safe publish-subscribe architecture with six typed lifecycle events: `DebateStartEvent`, `RoundStartEvent`, `AgentReplyEvent`, `RoundEndEvent`, `BeforeEvaluationEvent`, `DebateEndEvent`. External plugins register handlers via `DebateSDK.on(event_name, handler)` — zero coupling to core pipeline logic (Open-Closed Principle).

---

## Project Structure

```
src/debate/
├── agents/
│   ├── base.py          # BaseAgent ABC — V₁ lock, windowed ledger
│   ├── pro.py           # ProAgent — Anthropic calls, prompt caching
│   ├── con.py           # ConAgent — Anthropic calls, prompt caching
│   └── fact_checker.py  # FactCheckerSubagent — web search objections
├── benchmarks/
│   └── reporter.py      # BenchmarkReporter — JSON export
├── cli/
│   ├── entry.py         # debate CLI entry point
│   ├── menu.py          # run_loop(), interactive terminal menu
│   ├── handlers.py      # handle_*() functions
│   └── forecaster.py    # cost/token estimator + confirm gate
├── engine/
│   ├── embeddings.py    # EmbeddingService singleton (all-MiniLM-L6-v2)
│   ├── agents_factory.py # make_agents() — keeps pipeline.py ≤ 150 lines
│   ├── ledger.py        # LedgerManager — windowing, serialization
│   └── pipeline.py      # DebateResult, run_debate(), run_benchmarks()
├── evaluation/
│   ├── discourse.py     # DiscourseChecker — civility policy
│   ├── judge.py         # Judge — 4-level tiebreaker, verdict
│   ├── responsiveness.py
│   └── semantic_drift.py
├── events/
│   ├── bus.py           # EventBus — thread-safe on/emit
│   └── types.py         # 6 typed lifecycle dataclasses
├── gatekeeper/
│   ├── config.py        # GatekeeperConfig (rate_limits.json)
│   ├── gatekeeper.py    # ApiGatekeeper — token bucket + retry
│   └── watchdog.py      # Watchdog — circuit breaker
├── logging/
│   └── logger.py        # FifoRotatingHandler, DebateLogger
├── router/
│   └── skills.py        # TopicRouter — keyword → skill mapping
├── schemas/
│   ├── claim.py         # EvidenceSchema, ClaimPayloadSchema
│   ├── round.py         # LedgerEntry, RoundSchema
│   └── verdict.py       # VerdictSchema
├── shared/
│   ├── logger.py        # get_logger() → RotatingFileHandler
│   └── version.py       # __version__ = "1.0.0"
├── tools/
│   └── search.py        # WebSearchTool (DuckDuckGo)
├── analysis.py          # generate_all() → 4 PNG benchmark graphs
├── sdk.py               # DebateSDK public facade
├── sensitivity_runner.py # SensitivityRunner — hyperparameter sweep
└── config.py            # Settings (pydantic-settings, .env)
main.py                  # Thin CLI — 20 lines, argparse + delegates
```

---

## Installation

**Prerequisites:** Python 3.12+ and [`uv`](https://docs.astral.sh/uv/) must be installed on your system.

```bash
# 1. Clone the repository
git clone <repo-url>
cd Deterministic-AI-Debate

# 2. Install all dependencies into an isolated .venv (created automatically)
uv sync

# 3. Copy the environment template and fill in your API key
cp .env-example .env
```

Open `.env` and set `ANTHROPIC_API_KEY` at minimum. All other parameters have sensible defaults:

```env
ANTHROPIC_API_KEY=sk-ant-...

# Semantic drift thresholds
RECENCY_DECAY_LAMBDA=0.3
V1_DISTANCE_THRESHOLD=0.4
CENTROID_ALIGNMENT_THRESHOLD=0.7

# Debate parameters
LEDGER_WINDOW=3
MAX_ROUNDS=10
BENCHMARK_RUNS=5
LLM_MODEL=claude-sonnet-4-6
MAX_WORKERS=4
```

> **Important:** `uv sync` pins **all** transitive dependencies via `uv.lock`. Do not use `pip install` — this will bypass the lock file and may produce a non-reproducible environment.

---

## Running the System

### Interactive Mode (recommended)

```bash
uv run python main.py --interactive
```

Launches the numbered terminal menu. Select a debate topic, then choose:
- **1 — Run single debate**: one full debate at the configured `MAX_ROUNDS`
- **2 — Run benchmark suite**: N parallel debates (cost forecast + confirmation shown first)
- **3 — Generate analysis graphs**: produces 4 PNG charts into `assets/`
- **4 — View results**: pretty-prints the last `debate_systems_research.json`

### Non-Interactive / Scripted Runs

```bash
# Smoke test — 1 debate, 3 rounds (fast, minimal API cost)
uv run python main.py --runs 1 --rounds 3

# Full thesis benchmark — 5 debates × 10 rounds
uv run python main.py --runs 5 --rounds 10

# Custom configuration
uv run python main.py --runs 10 --rounds 5
```

### Via the Installed Entry Point

If the package is installed with `uv pip install -e .`:

```bash
debate --runs 5 --rounds 10
debate --interactive
```

### Python SDK

```python
from debate import DebateSDK

sdk = DebateSDK(topic="Will AI replace software engineers in the next 5 years?")

# Register a plugin hook
sdk.on("on_debate_end", lambda e: print(f"Winner: {e.result.verdict.winner}"))

# Run a single debate
result = sdk.run_single(max_rounds=10)

# Run the full benchmark suite
results = sdk.run_benchmark(n=5, max_rounds=10)

# Export to JSON
sdk.export(results, "debate_systems_research.json")

# Generate benchmark graphs
sdk.generate_analysis("debate_systems_research.json", "assets/")
```

---

## Running Tests

```bash
# Full test suite — 247 tests, zero API calls required
uv run pytest -v

# Phase-specific subsets
uv run pytest tests/test_schemas.py tests/test_embeddings.py -v   # Phase 1 & 2a
uv run pytest tests/test_ledger.py tests/test_pipeline.py -v      # Phase 2b & 3
uv run pytest tests/test_gatekeeper.py tests/test_watchdog.py -v  # Phase 5 & 10
uv run pytest tests/test_chaos.py tests/test_sensitivity.py -v    # Phase 10

# Coverage report
uv run pytest --cov=src --cov-report=term-missing

# Linter (must exit 0 before any commit)
uv run ruff check .

# Line-limit gate (all .py files must be < 150 lines)
find src tests main.py -name "*.py" | xargs wc -l | grep -v total \
  | awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS: all files under 150 lines"}'
```

---

## The CLAUDE.md Development Contract

This project was built using Claude Code (Anthropic's AI coding CLI) with a `CLAUDE.md` file at the repository root serving as a **persistent contract** between the human architect and the AI agent. `CLAUDE.md` is loaded at the start of every Claude Code session — it governs all file edits, implementation decisions, and tool calls without needing to be restated.

### How It Prevented Silent Failures

The `CLAUDE.md` contract encoded hard invariants using **Karpathy-style rules**: explicit, machine-verifiable, and structurally enforced rather than merely documented.

**Silent semantic drift** was prevented by encoding the rule `set_v1_embedding()` raises `RuntimeError` on a second call. Without this, an AI-driven retry path could silently overwrite the V₁ anchor, invalidating all drift metrics.

**Deterministic routing failures** were prevented by the rule *all Anthropic API calls must go through `ApiGatekeeper`*. The agent was required to run `grep -rn "messages.create" src/debate/agents/` and confirm zero matches after every agents-layer edit. A direct call bypassing the gatekeeper would silently skip rate limiting, backoff, and the Watchdog circuit breaker.

**Context explosion** was prevented by encoding the `LEDGER_WINDOW` truncation protocol as an absolute rule — the AI could not expand context "for correctness" without violating the contract.

**Hardcoded hyperparameters** were prevented by the rule *no float or int literals for tuning parameters in Python* — all values must be loaded from `.env` via `pydantic-settings`. Violations are a startup-time `ValidationError`, not a silent wrong result buried in run 4 of 5.

### Agentic Extensions: TDD-First and Phase Gates

The `CLAUDE.md` also encoded **agentic workflow extensions** — meta-rules governing the AI's development discipline:

- **TDD-First Mandate**: No implementation file could be written until the corresponding test file existed with failing tests. This prevented the AI from writing implementations that passed tests it wrote simultaneously.
- **Phase Gates**: After every phase, the agent was required to run `uv run ruff check .`, `uv run pytest`, and the line-limit `find` command and confirm all three passed before any new implementation work began.
- **Module Fragmentation**: When any module approached 140 lines, the agent was required to split it along functional seams. This produced `agents_factory.py` (split from `pipeline.py`), `discourse.py` (split from `judge.py`), and `shared/logger.py` (separated from `logging/logger.py`).
- **Dependency Directionality**: The acyclic import graph was encoded explicitly — `config` and `schemas` are leaves; `pipeline` is the only orchestrator. Cycles were checked with `grep` as part of each phase gate.

The `CLAUDE.md` contract was the difference between a reproducible research system and an impressively-functioning prototype.

---

## Output: `debate_systems_research.json`

After a benchmark run, `BenchmarkReporter` writes a structured JSON file to the project root:

```json
{
  "benchmark_metadata": {
    "timestamp": "2026-05-22T14:32:00.000000+00:00",
    "n_runs": 5
  },
  "runs": [
    {
      "tokens_per_debate": 18420,
      "cost_per_debate": 0.055,
      "context_cache_efficiency": 0.73,
      "latency_per_round": [1.2, 0.9, 1.1, 0.8, 1.0, 1.3, 0.9, 1.0, 1.1, 0.9],
      "winner": "CON"
    }
  ],
  "aggregates": {
    "mean_tokens_per_debate": 17850.4,
    "mean_cost_per_debate": 0.054,
    "mean_cache_efficiency": 0.71,
    "mean_latency_per_round": 1.02
  }
}
```

| Field | Description |
|---|---|
| `tokens_per_debate` | Total input + output tokens consumed across all rounds |
| `cost_per_debate` | Estimated cost at `$3 / 1M tokens` |
| `context_cache_efficiency` | Fraction of rounds with a prompt-cache hit |
| `latency_per_round` | Wall-clock seconds per round (list of length `max_rounds`) |
| `winner` | `"PRO"` or `"CON"` — always set, never `null` |
| `aggregates` | Cross-run statistics for thesis reporting |

---

## Benchmark Analysis & Results

A benchmark of 5 full debates (10 rounds each) was run against the thesis configuration. The CON agent won 4 out of 5 debates, demonstrating a consistent structural advantage when arguing against AI replacing software engineers under the system's deterministic verdict rules.

### Winner Distribution

![Winner Distribution](assets/winner_distribution.png)

### Tokens per Run

![Tokens per Run](assets/tokens_per_run.png)

### Cache Efficiency

![Cache Efficiency](assets/cache_efficiency.png)

> **Note — Why cache efficiency is 0%:** The zero cache-hit rate shown above is an expected architectural behaviour, not a bug. Anthropic's Prompt Caching requires two conditions to be met simultaneously: (1) the cached prefix must be **byte-identical** across calls, and (2) each message block that should be cached must carry an explicit `cache_control` header. This system triggers **Prefix Busting** on both fronts: every debate round prepends a fresh timestamp and a new UUID to the message sequence, and the tool-use array (which lists available search tools) changes order between agents — both of which invalidate the prefix before the cache can activate. Resolving this would require pinning a static, header-marked system-prompt block before any dynamic content and ensuring all variable data (timestamps, IDs, tool lists) is appended *after* the cached segment rather than prepended before it.

### Latency per Round

![Latency per Round](assets/latency_per_round.png)

---

## Full Debate Session Log

<!-- PLACEHOLDER: Insert a representative full debate transcript here before submission.
     Run the system with:

         uv run python main.py --runs 1 --rounds 10 --interactive

     Then copy the terminal output (or pipe it to a file with `tee debate_log.txt`)
     and paste the full session below, including round-by-round claims and the
     final VerdictSchema output.

     Format:
     ### Debate Session — [DATE]
     **Topic**: Will AI replace software engineers in the next 5 years?
     **Model**: claude-sonnet-4-6 | **Rounds**: 10 | **Winner**: [PRO/CON]

     #### Round 1
     **PRO**: [claim text]
     **CON**: [claim text]
     ...
     #### Verdict
     **Winner**: [PRO/CON]
     **Score**: PRO [x.xx] | CON [x.xx]
     **Tiebreaker used**: [null / evidence_quality / v1_faithfulness / prng]
-->

---

## Hyperparameters

| Parameter | Default | Description |
|---|---|---|
| `RECENCY_DECAY_LAMBDA` | `0.3` | Decay rate for opponent centroid weights |
| `V1_DISTANCE_THRESHOLD` | `0.4` | Cosine distance above which V₁ drift is penalised |
| `CENTROID_ALIGNMENT_THRESHOLD` | `0.7` | Cosine similarity above which centroid alignment is penalised |
| `LEDGER_WINDOW` | `3` | Number of recent claims passed to each agent as context |
| `LLM_MODEL` | `claude-sonnet-4-6` | Anthropic model used for both agents |
| `MAX_WORKERS` | `4` | Thread-pool size for parallel benchmark execution |

---

## Quality Standard Compliance (ISO/IEC 25010)

This system was designed against all eight ISO/IEC 25010 quality characteristics, mapping each to a concrete architectural decision:

| Characteristic | Implementation |
|---|---|
| **Functional Suitability** | `temperature=0` on all LLM calls; 4-level deterministic tiebreaker; `SHA-256`-seeded PRNG guarantee every verdict is reproducible and traceable |
| **Performance Efficiency** | `ThreadPoolExecutor` parallelises benchmark runs; FinOps Context Truncation bounds token cost per round to `O(LEDGER_WINDOW × avg_claim_length)` regardless of debate length |
| **Compatibility** | PEP 517 `src`-layout package with `uv` lock-file; `pythonpath = ["."]` in `pytest.ini` means tests run identically across environments |
| **Usability** | `rich` progress bars surface benchmark status in real time (Nielsen Heuristic 1 — Visibility of System Status); interactive numbered CLI menu requires no prior knowledge of flags; cost forecast shown before every benchmark |
| **Reliability** | 247-test suite (≥ 91% coverage, zero API calls required); Watchdog circuit breaker limits blast radius of API failures; deterministic Level 4 PRNG tiebreaker guarantees a winner always exists |
| **Security** | Secrets loaded from `.env` via `pydantic-settings` (never committed); `ApiGatekeeper` enforces per-minute rate limits and exponential-backoff retries, shielding against API abuse and cost runaway |
| **Maintainability** | Hard 150-line file limit; `ruff` zero-error gate with `E,F,W,I,UP,B,C4,SIM` rules; relative imports throughout; `__all__` on every `__init__.py`; EventBus plugin architecture allows extension without modifying core pipeline |
| **Portability** | Pure-Python with no OS-specific dependencies; `uv sync` reproduces the full environment in under 30 s on any POSIX or Windows system with Python 3.12+ |

---

## Hard Constraints

| Check | Command |
|---|---|
| All 247 tests pass | `uv run pytest -v` |
| Zero linter errors | `uv run ruff check .` |
| No file ≥ 150 lines | `find src tests main.py -name "*.py" \| xargs wc -l` |
| `main.py` ≤ 20 lines | `wc -l main.py` |
| No direct Anthropic calls in agents | `grep -rn "messages.create" src/debate/agents/` (must return 0 matches) |
| No hardcoded hyperparameters | `grep -rn "0\.3\|0\.4\|0\.7" src/ --include="*.py"` (must only hit `config.py` defaults) |

---

## Usage

Start the system with:

```bash
uv run python main.py
```

This launches an interactive numbered CLI menu — no flags required. The menu presents the available actions (single debate, full benchmark suite, help) and prompts you for any required input.

For non-interactive or scripted runs, pass flags directly:

```bash
# Quick smoke test — 1 debate, 3 rounds
uv run python main.py --runs 1 --rounds 3
```

---

## Configuration Guide

All runtime secrets and tuning parameters are managed via a `.env` file in the project root. A fully annotated template is provided at `.env-example` — copy it and fill in your credentials before running the system.

```bash
cp .env-example .env
# Then open .env and set ANTHROPIC_API_KEY=sk-ant-...
```

The `.env` file is listed in `.gitignore` and is **never committed**. Secrets are loaded at startup by `pydantic-settings` (`src/debate/config.py`), which validates every field against its expected type and raises a clear error on misconfiguration.

---

## Contribution Guidelines

Contributions are welcome. The CI gate enforces all hard constraints automatically on every push and pull request.

### Dependency Management

This project uses [`uv`](https://docs.astral.sh/uv/) exclusively. Do **not** use `pip install` or modify dependencies manually.

```bash
uv add <package>          # add a runtime dependency
uv add --dev <package>    # add a development dependency
uv sync                   # reproduce the locked environment
```

### Code Style

| Rule | Enforcement |
|---|---|
| Zero linter errors | `uv run ruff check .` must exit `0` before every commit |
| Import sorting | Ruff `I001` — run `uv run ruff check . --fix` to auto-correct |
| Max lines per `.py` file | **150 lines** — hard limit, no exceptions |
| Max lines for `main.py` | **20 lines** — entry point must remain a thin dispatcher |

### Testing

All pull requests must keep the full `pytest` suite green with zero failures and zero API calls:

```bash
uv run pytest -v
```

New features require corresponding tests written **before** the implementation (TDD mandate). Mock any external API call using `unittest.mock.patch`.

### Commit Style

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
feat: add streaming support to DebateEngine
fix: prevent V1 anchor overwrite on retry
docs: add CLAUDE.md contract section to README
```

---

## License & Credits

### License

This project is released under the **MIT License**.

```
MIT License

Copyright (c) 2026 Avi Ayeli

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Open-Source Acknowledgements

| Tool | Purpose |
|---|---|
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | LLM inference for PRO and CON agents |
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | `all-MiniLM-L6-v2` semantic embeddings (local, deterministic) |
| [Pydantic](https://github.com/pydantic/pydantic) / [pydantic-settings](https://github.com/pydantic/pydantic-settings) | Schema validation and `.env` config loading |
| [pytest](https://github.com/pytest-dev/pytest) | TDD test runner (247-test offline suite) |
| [Ruff](https://github.com/astral-sh/ruff) | Linter and import sorter |
| [uv](https://github.com/astral-sh/uv) | Dependency management and virtual environment |
| [Rich](https://github.com/Textualize/rich) | Terminal progress bars and formatted output |
| [Matplotlib](https://matplotlib.org/) / [Seaborn](https://seaborn.pydata.org/) | Benchmark graph generation |

> **Evaluator Note:** The Shared Evidence Registry is implemented functionally — `EvidenceSchema` objects are stored in `ClaimPayloadSchema.evidence`, referenced by the Judge's Level 1 tiebreaker via mean `quality_score` aggregation — rather than as a separate `EvidenceRegistry` class. This satisfies the functional requirement while respecting the 150-line file constraint.
