# PRD: Advanced Features — SDK/CLI, Multithreading, Data Visualization

**Status**: Approved for implementation  
**Deadline**: 2026-05-28 (1.5 weeks)  
**Goal**: Elevate the project to "Reference Project" grade via three mutually reinforcing features.

---

## 1. SDK / CLI Architecture

### 1.1 Problem

`main.py` is a thin argparse shim, but callers (tests, notebooks, future integrations) must
reach through internal modules directly. There is no stable public surface and no interactive
entry point for non-engineer evaluators.

### 1.2 SDK Layer (`src/debate/sdk.py`)

A single public facade that owns object lifecycle and wires all subsystems together.
Internal modules remain importable for tests, but external consumers (CLI, scripts) should
only ever import from `debate.sdk`.

```
Public API
──────────
DebateSDK(topic: str | None = None)
  .run_single(max_rounds: int) -> DebateResult
  .run_benchmark(n: int, max_rounds: int) -> list[DebateResult]
  .export(results, path)                -> Path
  .generate_analysis(json_path, out_dir) -> list[Path]
```

Lifecycle rules:
- `DebateSDK.__init__` instantiates the Anthropic client, `ApiGatekeeper`, and injects
  the selected topic into the agents' system prompts via a topic override.
- `ApiGatekeeper` is instantiated once per `DebateSDK` instance and shared across all
  threads — its token-bucket lock already ensures thread safety.
- `DebateSDK` is **not** a singleton; callers may instantiate multiple instances (e.g., one
  per CLI session).

### 1.3 Interactive CLI (`src/debate/cli/`)

Split across two files to respect the 150-line limit:

| File | Responsibility |
|---|---|
| `src/debate/cli/menu.py` | Main loop, display, user-input parsing |
| `src/debate/cli/handlers.py` | Action handlers that call `DebateSDK` methods |

**User flow:**

```
╔══════════════════════════════════════╗
║   Deterministic AI Debate System     ║
╠══════════════════════════════════════╣
║  1. Select debate topic              ║
║  2. Run single debate                ║
║  3. Run benchmark (N rounds)         ║
║  4. View last benchmark results      ║
║  5. Generate analysis graphs         ║
║  6. Exit                             ║
╚══════════════════════════════════════╝
```

Available topics are loaded from `config/topics.json` (list of strings). The user selects
by index; the chosen topic is passed to `DebateSDK(topic=...)`.

`main.py` detects the `--interactive` flag; absent that flag it retains the existing
argparse-driven non-interactive behaviour. This keeps `main.py` ≤ 20 lines.

### 1.4 File Budget

| File | Max lines |
|---|---|
| `src/debate/sdk.py` | 100 |
| `src/debate/cli/menu.py` | 120 |
| `src/debate/cli/handlers.py` | 100 |
| `main.py` | 20 |

---

## 2. Multithreading for Benchmarks

### 2.1 Problem

`run_benchmarks()` currently calls `run_debate()` sequentially. Each debate is
dominated by Anthropic API I/O (network round-trips). Wall-clock time scales linearly
with `n`; with threads it can scale sub-linearly bounded by `max_workers` and the
gatekeeper's token-bucket rate limit.

### 2.2 Strategy

Replace the list comprehension in `run_benchmarks()` with a
`concurrent.futures.ThreadPoolExecutor`:

```python
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
    futures = [pool.submit(run_debate, ProAgent(gk), ConAgent(gk), max_rounds)
               for _ in range(n)]
    results = [f.result() for f in as_completed(futures)]
```

`max_workers` is read from `config/rate_limits.json` → `GatekeeperConfig.max_workers`
and exposed on `Settings.MAX_WORKERS` (env override: `MAX_WORKERS=4`).

### 2.3 Thread-Safety Audit

| Component | Shared? | Safe? | Notes |
|---|---|---|---|
| `ApiGatekeeper` | Yes (one per SDK) | **Yes** | Token bucket uses `threading.Lock` |
| `DebateLogger` / `FifoRotatingHandler` | Yes (singleton) | **Yes** | `emit()` acquires lock before write |
| `EmbeddingService` | Yes (singleton) | **Yes** | `SentenceTransformer.encode()` is GIL-held; no mutable state |
| `ProAgent` / `ConAgent` | No (one per thread) | N/A | Each `run_debate()` call gets fresh agents |
| `BenchmarkReporter.export()` | No (called once after join) | N/A | Runs after all threads complete |

No additional locks are required. Each thread owns its own agent pair and result object.

### 2.4 Error Handling

If a `run_debate()` call raises an exception inside a worker, `Future.result()` re-raises
it in the caller. The pipeline logs the exception via the shared logger (thread-safe) before
re-raising so the benchmark run fails loudly rather than silently producing a short result
list.

---

## 3. Data Visualization (`src/debate/analysis.py`)

### 3.1 Problem

`debate_systems_research.json` is machine-readable but not human-presentable. For a thesis
defence or README, graphs are required.

### 3.2 Module Design

```python
# Public surface
def generate_all(json_path: str | Path, out_dir: str | Path) -> list[Path]:
    """Load JSON, render all graphs, return list of saved file paths."""
```

`generate_all` is the only public symbol. It loads `config/visualization_config.json` for
DPI, format, matplotlib style, and output directory override.

### 3.3 Graph Catalogue

| # | Graph | Chart type | Data source |
|---|---|---|---|
| 1 | `latency_per_round.png` | Line plot (mean ± std across runs) | `runs[*].latency_per_round` |
| 2 | `tokens_per_run.png` | Bar chart (one bar per run) | `runs[*].tokens_per_debate` |
| 3 | `cache_efficiency.png` | Bar chart (one bar per run) | `runs[*].context_cache_efficiency` |
| 4 | `winner_distribution.png` | Pie chart | `runs[*].winner` |

Each graph is saved as `{out_dir}/{name}.{format}` at the configured DPI.

### 3.4 File Budget

`src/debate/analysis.py` must stay ≤ 150 lines. Each graph is rendered by a private
`_plot_*` helper function; `generate_all` orchestrates them.

### 3.5 Dependencies

Add to `pyproject.toml`:
- `matplotlib>=3.8.0`
- `seaborn>=0.13.0`

---

## 4. Configuration Changes

### 4.1 `config/rate_limits.json` — add `max_workers`

```json
{ ..., "max_workers": 4 }
```

### 4.2 `config/topics.json` — new file

```json
{
  "topics": [
    "Will AI replace software engineers?",
    "Is remote work better than office work?",
    "Should AI systems be open-source?"
  ],
  "default": "Will AI replace software engineers?"
}
```

### 4.3 `config/visualization_config.json` — new file

```json
{
  "assets_dir": "assets/",
  "dpi": 150,
  "format": "png",
  "style": "seaborn-v0_8-darkgrid",
  "figsize": [10, 6]
}
```

### 4.4 `src/debate/config.py` — new fields

```python
MAX_WORKERS: int = 4         # env: MAX_WORKERS
ASSETS_DIR: str = "assets/"  # env: ASSETS_DIR
```

---

## 5. Constraints Checklist

| Constraint | Mechanism |
|---|---|
| No Python file ≥ 150 lines | Enforced in every phase gate |
| `uv run ruff check .` == 0 errors | Required before any commit |
| Test coverage ≥ 85% | `uv run pytest --cov=src --cov-report=term-missing` |
| No hardcoded values in Python | All tunable values in `.env` or `config/*.json` |
| Thread safety | Audit table in §2.3; no new locks needed |
