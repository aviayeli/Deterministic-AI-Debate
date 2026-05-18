# TODO: Phased TDD Execution Plan

## Protocol

- **Tests before implementation**: Every phase begins with test files. No implementation starts until the test skeleton exists.
- **Phase gates**: A phase is complete only when all tests pass AND `uv run ruff check .` exits 0.
- **150-line check**: Run `find src tests main.py -name "*.py" | xargs wc -l` after every phase. Any file ≥ 150 lines must be split before proceeding.
- **No skipping phases**: Phase 2a and 2b are independent and can run in parallel; Phase 3 depends on both.

---

## Phase 1: Foundation — Schemas & Configuration

**Goal**: All Pydantic schemas typed, validated, and tested. `.env` hyperparameters load correctly.

### 1.1 — Tests First (`tests/test_schemas.py`)

- [ ] Test `EvidenceSchema` rejects `quality_score` outside `[0.0, 1.0]`
- [ ] Test `EvidenceSchema` accepts boundary values `0.0` and `1.0`
- [ ] Test `ClaimPayloadSchema` requires `addressed_claim_ids` field (missing → `ValidationError`)
- [ ] Test `ClaimPayloadSchema` requires non-empty `agent_id`
- [ ] Test `ClaimPayloadSchema` auto-generates `claim_id` as a valid UUID4 string
- [ ] Test `ClaimPayloadSchema` two instances get distinct `claim_id` values
- [ ] Test `ClaimPayloadSchema.stance` rejects values outside `["PRO", "CON"]`
- [ ] Test `LedgerEntry` correctly wraps a `ClaimPayloadSchema` with optional `embedding=None`
- [ ] Test `RoundSchema` holds exactly one `pro_claim` and one `con_claim`
- [ ] Test `VerdictSchema.winner` rejects values outside `["PRO", "CON"]`
- [ ] Test `VerdictSchema.tiebreaker_used` accepts `None` (no tie)
- [ ] Test `settings.RECENCY_DECAY_LAMBDA` loads from `.env` as `float`
- [ ] Test `settings.V1_DISTANCE_THRESHOLD` loads from `.env` as `float`
- [ ] Test default `settings.LEDGER_WINDOW == 3` when `.env` omits it

### 1.2 — Implementation

- [ ] `pyproject.toml`: add `anthropic>=0.40.0`, `sentence-transformers>=3.0.0`, `numpy>=1.26.0`, `pydantic-settings>=2.0.0`
- [ ] `uv sync`
- [ ] `src/debate/__init__.py`
- [ ] `src/debate/config.py` — `Settings(BaseSettings)` with all hyperparameters, `settings` singleton
- [ ] `src/debate/schemas/__init__.py`
- [ ] `src/debate/schemas/claim.py` — `EvidenceSchema`, `ClaimPayloadSchema`
- [ ] `src/debate/schemas/round.py` — `LedgerEntry`, `RoundSchema`
- [ ] `src/debate/schemas/verdict.py` — `VerdictSchema`
- [ ] `tests/conftest.py` — shared fixtures: `sample_claim()`, `sample_evidence()`, `sample_ledger_entry()`
- [ ] Create `.env` with `RECENCY_DECAY_LAMBDA=0.3`, `V1_DISTANCE_THRESHOLD=0.4`

### Phase 1 Gate

```bash
uv run pytest tests/test_schemas.py -v                     # all green
uv run ruff check .                                        # 0 errors
find src tests main.py -name "*.py" | xargs wc -l          # no file ≥ 150
```

---

## Phase 2a: Core Evaluation Logic — Embeddings, Drift, Responsiveness

**Goal**: All evaluation logic implemented and tested with zero LLM calls. Pure Python and local embeddings only.

### 2a.1 — Tests First (`tests/test_embeddings.py`)

- [ ] Test `EmbeddingService.embed("hello")` returns a `List[float]`
- [ ] Test embedding dimension is 384 (all-MiniLM-L6-v2 output size)
- [ ] Test `embed(x) == embed(x)` (same input → identical output, determinism)
- [ ] Test `cosine_distance(v, v) ≈ 0.0` for any vector `v`
- [ ] Test `cosine_distance("AI automation", "apple pie recipe") > 0.5`
- [ ] Test `cosine_similarity(v, v) ≈ 1.0`
- [ ] Test `weighted_centroid([v], [1.0]) == v` (single-element case)
- [ ] Test `weighted_centroid([a, b], [1.0, 1.0])` equals simple mean of `a` and `b`
- [ ] Test `EmbeddingService` is a singleton (same object on multiple imports)

### 2a.2 — Tests First (`tests/test_semantic_drift.py`)

- [ ] Test no penalty when `cosine_distance(current, v1) < V1_DISTANCE_THRESHOLD`
- [ ] Test drift penalty > 0 when `cosine_distance(current, v1) > V1_DISTANCE_THRESHOLD`
- [ ] Test `drift_penalty == 0` when centroid alignment below `CENTROID_ALIGNMENT_THRESHOLD`
- [ ] Test centroid alignment penalty > 0 when similarity exceeds threshold
- [ ] Test `evaluate()` reads `v1_embedding` from `agent.v1_embedding`, not ledger
- [ ] Test `evaluate()` raises `ValueError` if `agent.v1_embedding is None`
- [ ] Test decay weighting: more recent embeddings have higher weight in centroid
- [ ] Test `DriftResult` fields: `v1_distance`, `centroid_alignment`, `drift_penalty`

### 2a.3 — Tests First (`tests/test_responsiveness.py`)

- [ ] Test score `== 1.0` when all `addressed_claim_ids` are valid in opponent ledger
- [ ] Test score `== 0.0` when no `addressed_claim_ids` match opponent ledger
- [ ] Test score `== 0.5` when exactly half of IDs match (2 of 4)
- [ ] Test score `== 0.0` (not division error) when opponent ledger is empty
- [ ] Test that IDs not in opponent ledger but declared do not raise — only lower score
- [ ] Test score is deterministic for identical inputs

### 2a.4 — Implementation

- [ ] `src/debate/engine/__init__.py`
- [ ] `src/debate/engine/embeddings.py` — `EmbeddingService` singleton, cosine ops, centroid
- [ ] `src/debate/evaluation/__init__.py`
- [ ] `src/debate/evaluation/responsiveness.py` — `ResponsivenessCalculator`
- [ ] `src/debate/evaluation/semantic_drift.py` — `SemanticDriftEvaluator`, `DriftResult`

### Phase 2a Gate

```bash
uv run pytest tests/test_embeddings.py tests/test_semantic_drift.py tests/test_responsiveness.py -v
uv run ruff check .
find src tests main.py -name "*.py" | xargs wc -l
```

---

## Phase 2b: Agents & Judge

**Goal**: V₁ immutability enforced in `BaseAgent`. Judge produces singular, deterministic verdicts via pure-Python tiebreaker.

### 2b.1 — Tests First (`tests/test_ledger.py`)

- [ ] Test `BaseAgent.v1_embedding` is `None` before any claim is generated
- [ ] Test `set_v1_embedding(emb)` stores the embedding in `agent.v1_embedding`
- [ ] Test `set_v1_embedding()` raises `RuntimeError` when called a second time
- [ ] Test `get_windowed_ledger(3)` returns at most 3 entries regardless of ledger size
- [ ] Test `get_windowed_ledger(3)` returns the *last* 3 entries, not the first
- [ ] Test `v1_embedding` is NOT returned by `get_windowed_ledger()` (separate state)
- [ ] Test `LedgerManager.serialize_for_llm(entries)` returns valid JSON string
- [ ] Test serialized JSON contains `claim_id` and `claim_text` fields
- [ ] Test `LedgerManager.get_claim_ids()` returns a `Set[str]` of all `claim_id` values

### 2b.2 — Tests First (`tests/test_judge.py`)

- [ ] Test `Judge.evaluate_debate()` returns a `VerdictSchema` for a 10-round debate
- [ ] Test `VerdictSchema.winner` is exactly `"PRO"` or `"CON"`, never `None`
- [ ] Test no tiebreaker when PRO scores are clearly higher (`tiebreaker_used == None`)
- [ ] Test **Level 1 tiebreaker** (Evidence Quality): agent with higher mean evidence score wins
- [ ] Test **Level 2 tiebreaker** (V₁ Faithfulness): agent with *lower* V₁ distance wins
- [ ] Test **Level 3 tiebreaker** (Responsiveness): agent with higher mean score wins
- [ ] Test **Level 4 tiebreaker** (PRNG): output is deterministic for identical `debate_id`
- [ ] Test Level 4 tiebreaker seeds from `debate_id` hash (different IDs → may differ)
- [ ] Test `VerdictSchema.tiebreaker_used` records which level resolved the tie
- [ ] Test `VerdictSchema` contains `v1_distance_pro` and `v1_distance_con` fields
- [ ] Test `_resolve_tiebreaker` makes zero LLM calls (mock Anthropic client: assert not called)

### 2b.3 — Implementation

- [ ] `src/debate/agents/__init__.py`
- [ ] `src/debate/agents/base.py` — `BaseAgent(ABC)` with permanent V₁, windowed ledger
- [ ] `src/debate/agents/pro.py` — `ProAgent`, Anthropic call, prompt caching, `temperature=0`
- [ ] `src/debate/agents/con.py` — `ConAgent`, Anthropic call, prompt caching, `temperature=0`
- [ ] `src/debate/engine/ledger.py` — `LedgerManager` with serialize + claim_ids
- [ ] `src/debate/evaluation/judge.py` — `Judge`, `RoundScores`, 4-level tiebreaker

### Phase 2b Gate

```bash
uv run pytest tests/test_ledger.py tests/test_judge.py -v
uv run ruff check .
find src tests main.py -name "*.py" | xargs wc -l
# Spot-checks:
wc -l src/debate/agents/base.py     # must be < 90
wc -l src/debate/evaluation/judge.py  # must be < 140
```

---

## Phase 3: Pipeline, CLI & Benchmarks

**Goal**: End-to-end debate runs. N=5 × 10-round benchmark exports `debate_systems_research.json`. All hard limits verified.

### 3.1 — Tests First (`tests/test_pipeline.py`)

- [ ] Test `run_debate()` returns a result with exactly `max_rounds` rounds
- [ ] Test each round in result is a valid `RoundSchema`
- [ ] Test `run_debate()` result contains a valid `VerdictSchema`
- [ ] Test `VerdictSchema.winner` is set (not `None`)
- [ ] Test both agents have `v1_embedding` set (not `None`) after round 1
- [ ] Test PRO agent's `get_windowed_ledger(3)` returns ≤ 3 entries at round 6
- [ ] Test `run_benchmarks(n=2)` returns exactly 2 `DebateResult` objects
- [ ] Test each `DebateResult` has `latency_per_round` list of length `max_rounds`
- [ ] Test each `DebateResult` has `tokens_per_debate: int > 0`
- [ ] Test each `DebateResult` has `cost_per_debate: float > 0`
- [ ] Test each `DebateResult` has `context_cache_efficiency: float` in `[0.0, 1.0]`
- [ ] Test `BenchmarkReporter.export(results)` writes a valid JSON file
- [ ] Test exported JSON contains `benchmark_metadata`, `runs`, `aggregates` keys
- [ ] Test `aggregates.mean_tokens_per_debate` equals mean of per-run token counts

### 3.2 — Implementation

- [ ] `src/debate/engine/pipeline.py` — `DebateResult`, `run_debate()`, `run_benchmarks()`
- [ ] `src/debate/benchmarks/__init__.py`
- [ ] `src/debate/benchmarks/reporter.py` — `BenchmarkReporter`, JSON export
- [ ] `main.py` — thin CLI ≤ 20 lines: argparse + `pipeline.run_benchmarks()` call

### Phase 3 Gate (Full System Verification)

```bash
# All tests green
uv run pytest -v

# Zero linter errors
uv run ruff check .

# No file exceeds 150 lines
find src tests main.py -name "*.py" | xargs wc -l | grep -v total | awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS: all files under 150 lines"}'

# main.py stays under 20 lines
wc -l main.py

# Smoke test (1 run, 3 rounds — uses real API)
uv run python main.py --runs 1 --rounds 3

# Validate output JSON
python -c "import json; d=json.load(open('debate_systems_research.json')); print('runs:', len(d['runs']))"

# Full benchmark (requires ANTHROPIC_API_KEY in .env)
uv run python main.py --runs 5 --rounds 10
```

---

## Summary Table

| Phase | Key Deliverables | Gate Checks |
|---|---|---|
| **1** | Schemas, config, `.env` loading | `test_schemas.py` green; ruff 0 errors |
| **2a** | Embeddings, drift evaluator, responsiveness | `test_embeddings.py` + drift + responsiveness green |
| **2b** | BaseAgent V₁ isolation, Judge tiebreaker | `test_ledger.py` + `test_judge.py` green; no LLM in tiebreaker |
| **3** | Pipeline, CLI, benchmark JSON export | Full suite green; line limit verified; JSON valid |

---

## Phase 5: Production-Grade API Gatekeeper & Watchdog

**Goal**: All Anthropic API calls pass through a single `ApiGatekeeper`. Rate limiting,
timeout enforcement, and retry-with-backoff are centralized and config-driven.

**Reference**: `docs/PRD_gatekeeper.md` | Config: `config/rate_limits.json`

### 5.1 — Tests First (`tests/test_gatekeeper.py`)

All tests use `unittest.mock` — zero real network calls.

**GatekeeperConfig**
- [ ] Test config loads `requests_per_minute` from `config/rate_limits.json`
- [ ] Test config loads `max_retries`, `timeout_seconds`, `backoff_factor` from JSON
- [ ] Test config raises `FileNotFoundError` if `rate_limits.json` is missing

**Rate Limiting**
- [ ] Test a single `gatekeeper.call()` succeeds when bucket has tokens
- [ ] Test `gatekeeper.call()` blocks (sleeps) when bucket is empty, then succeeds
- [ ] Test that N calls within a minute do not exceed `requests_per_minute`

**Timeout**
- [ ] Test `gatekeeper.call()` raises `GatekeeperTimeoutError` when SDK raises `APITimeoutError` on every attempt
- [ ] Test timeout is passed to the underlying SDK call as `timeout=timeout_seconds`

**Retry Logic**
- [ ] Test `gatekeeper.call()` retries on `RateLimitError` (429) up to `max_retries` times
- [ ] Test `gatekeeper.call()` retries on `InternalServerError` with status 529
- [ ] Test `gatekeeper.call()` does NOT retry on `AuthenticationError` (401)
- [ ] Test `gatekeeper.call()` does NOT retry on `BadRequestError` (400)
- [ ] Test after successful retry, the return value is the mock response (not an exception)
- [ ] Test exponential backoff: sleep duration on retry 0 = `backoff_factor * (2**0) ± jitter`
- [ ] Test all retries exhausted → `GatekeeperRateLimitError` raised (not swallowed)

**Integration with Agents**
- [ ] Test `ProAgent.generate_claim()` calls `gatekeeper.call()` exactly once per invocation
- [ ] Test `ConAgent.generate_claim()` calls `gatekeeper.call()` exactly once per invocation
- [ ] Test agents do NOT call `anthropic.Anthropic.messages.create()` directly (assert not called)

### 5.2 — Implementation

- [ ] `src/debate/gatekeeper/__init__.py` — exports `ApiGatekeeper`, `GatekeeperError`, `GatekeeperTimeoutError`, `GatekeeperRateLimitError`
- [ ] `src/debate/gatekeeper/config.py` — `GatekeeperConfig` dataclass, loads `config/rate_limits.json`
- [ ] `src/debate/gatekeeper/gatekeeper.py` — `ApiGatekeeper` class with token bucket, timeout, retry (≤ 150 lines)

### 5.3 — Refactor: Wire Gatekeeper into Agents & Pipeline

- [ ] `src/debate/agents/pro.py` — accept `ApiGatekeeper` in `__init__`, replace direct SDK call
- [ ] `src/debate/agents/con.py` — accept `ApiGatekeeper` in `__init__`, replace direct SDK call
- [ ] `src/debate/engine/pipeline.py` — instantiate `ApiGatekeeper` once, inject into both agents
- [ ] Verify: `grep -rn "messages.create" src/debate/agents/` returns 0 matches

### Phase 5 Gate

```bash
# All tests green (including new test_gatekeeper.py)
uv run pytest -v

# Zero linter errors
uv run ruff check .

# No file ≥ 150 lines
find src tests main.py -name "*.py" | xargs wc -l | grep -v total | awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS: all files under 150 lines"}'

# No direct Anthropic calls in agents
grep -rn "messages.create" src/debate/agents/ && echo "FAIL: direct SDK call found" || echo "PASS: all calls via gatekeeper"

# Coverage check
uv run pytest --cov=src --cov-report=term-missing | tail -5
```

---

## Phase 11: CI/CD — GitHub Actions Pipeline

**Goal**: Every `push` and `pull_request` to `master` / `main` automatically
lints and tests the codebase via GitHub Actions. `uv` is the single
package and task runner — no direct `pip` or `python -m` calls.

**Reference**: `.github/workflows/ci.yml`

### 11.1 — Documentation (Phase 1)

- [x] Update `docs/TODO.md` with Phase 11 tasks (this section)
- [x] Update `docs/PLAN.md` with CI/CD automation summary

### 11.2 — Workflow File (Phase 2 — pending approval)

- [x] Create `.github/workflows/` directory
- [x] Write `.github/workflows/ci.yml` with:
  - Trigger: `push` and `pull_request` to `master` and `main`
  - Runner: `ubuntu-latest`
  - Steps: checkout → install `uv` → `uv sync` → `uv run ruff check .` → `uv run pytest`

### Phase 11 Gate

```bash
# Local pre-push gate (mirrors CI exactly)
uv run ruff check .      # must exit 0
uv run pytest            # all tests green

# Verify workflow file is valid YAML
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "PASS"

# Confirm trigger branches
grep -A2 "branches:" .github/workflows/ci.yml
```

---

## Hard Constraints (never skip)

| Check | Command |
|---|---|
| All tests pass | `uv run pytest -v` |
| Linter clean | `uv run ruff check .` |
| No file ≥ 150 lines | `find src tests main.py -name "*.py" \| xargs wc -l` |
| `main.py` ≤ 22 lines | `wc -l main.py` (--interactive adds 3 lines) |
| `pipeline.py` ≤ 150 lines | `wc -l src/debate/engine/pipeline.py` |
| No hardcoded hyperparameters | `grep -r "0\.3\|0\.4" src/ --include="*.py"` (should hit only defaults in config.py) |

---

## Phase 7: Hooks & Plugin Architecture

**Goal**: Implement a thread-safe, typed `EventBus` with six lifecycle hook
points. External plugins register callables against named events via
`DebateSDK.on()` — zero coupling to core internals required.

**Reference**: `docs/PRD_plugins_and_packaging.md §2`

### 7.1 — Tests First (`tests/test_events.py`)

- [ ] Test `EventBus.emit()` with no handlers is a no-op (no exception raised)
- [ ] Test a registered handler is called exactly once per `emit()`
- [ ] Test multiple handlers for the same event are all called, in registration order
- [ ] Test handler exception propagates out of `emit()` (not swallowed)
- [ ] Test `on()` is thread-safe: 20 concurrent registrations produce no lost handlers
- [ ] Test `run_debate()` with a recording bus fires all 6 event types in correct sequence
- [ ] Test `DebateSDK.on()` delegates to the internal `EventBus` instance
- [ ] Test plugin registered after `DebateSDK()` but before `run_single()` fires correctly

### 7.2 — Implementation

- [ ] `src/debate/events/types.py` — six event dataclasses: `DebateStartEvent`, `RoundStartEvent`, `AgentReplyEvent`, `RoundEndEvent`, `BeforeEvaluationEvent`, `DebateEndEvent` (≤ 80 lines)
- [ ] `src/debate/events/bus.py` — `EventBus` with `on()` (locked) and `emit()` (lock-free read) (≤ 60 lines)
- [ ] `src/debate/events/__init__.py` — re-exports `EventBus` + all event types with `__all__`
- [ ] `src/debate/engine/pipeline.py` — `run_debate()` accepts `bus: EventBus | None = None`; fires 6 event types at correct lifecycle points; `run_benchmarks()` passes shared bus
- [ ] `src/debate/sdk.py` — add `self._bus = EventBus()`; expose `sdk.on(event, handler)`; pass `self._bus` to `run_debate()` and `run_benchmarks()`

### Phase 7 Gate

```bash
uv run pytest tests/test_events.py -v
uv run ruff check .
find src tests main.py -name "*.py" | xargs wc -l | grep -v total | \
  awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS"}'
```

---

## Phase 8: Official Python Package Structure

**Goal**: Migrate all internal `src.debate.*` absolute imports to relative
imports; populate `__all__` in every `__init__.py`; add a CLI entry point;
configure `pyproject.toml` package discovery so `pip install .` works.

**Reference**: `docs/PRD_plugins_and_packaging.md §3`

### 8.1 — Tests First

All existing tests serve as the regression suite — they must remain green
after every import migration. No new test file is required for this phase.
Run `uv run pytest -v` after each file is migrated.

### 8.2 — Relative Import Migration

Migrate each file from `from src.debate.X import Y` to `from ..X import Y`
(or `from .X import Y` for same-package imports):

- [ ] `src/debate/agents/base.py`
- [ ] `src/debate/agents/pro.py`
- [ ] `src/debate/agents/con.py`
- [ ] `src/debate/engine/pipeline.py`
- [ ] `src/debate/engine/ledger.py`
- [ ] `src/debate/engine/embeddings.py`
- [ ] `src/debate/evaluation/judge.py`
- [ ] `src/debate/evaluation/responsiveness.py`
- [ ] `src/debate/evaluation/semantic_drift.py`
- [ ] `src/debate/gatekeeper/gatekeeper.py`
- [ ] `src/debate/gatekeeper/config.py`
- [ ] `src/debate/benchmarks/reporter.py`
- [ ] `src/debate/cli/menu.py`
- [ ] `src/debate/cli/handlers.py`
- [ ] `src/debate/sdk.py`
- [ ] `src/debate/analysis.py`
- [ ] `src/debate/config.py`

### 8.3 — `__all__` Population

Add `__all__` to every empty `__init__.py` and update the two that already
have it (`gatekeeper`, `logging`) to verify completeness:

- [ ] `src/debate/__init__.py` — `["DebateSDK"]`
- [ ] `src/debate/agents/__init__.py` — `["BaseAgent", "ProAgent", "ConAgent"]`
- [ ] `src/debate/engine/__init__.py` — `["DebateResult", "run_debate", "run_benchmarks"]`
- [ ] `src/debate/evaluation/__init__.py` — `["Judge", "ResponsivenessCalculator", "SemanticDriftEvaluator", "DriftResult"]`
- [ ] `src/debate/schemas/__init__.py` — `["ClaimPayloadSchema", "EvidenceSchema", "LedgerEntry", "RoundSchema", "VerdictSchema"]`
- [ ] `src/debate/benchmarks/__init__.py` — `["BenchmarkReporter"]`
- [ ] `src/debate/cli/__init__.py` — `["run_loop"]`

### 8.4 — Entry Point

- [ ] `src/debate/cli/entry.py` — thin argparse wrapper ≤ 20 lines; mirrors `main.py` but importable
- [ ] `pyproject.toml` — add `[project.scripts] debate = "debate.cli.entry:main"` and `[tool.setuptools.packages.find]`
- [ ] `main.py` — delegate to `debate.cli.entry:main()` (stays ≤ 22 lines)

### Phase 8 Gate

```bash
# All tests still green after import migration
uv run pytest -v

# Zero absolute src.debate imports remain in src/
grep -rn "from src\.debate" src/ && echo "FAIL: absolute imports remain" || echo "PASS"

# Ruff clean
uv run ruff check .

# Package installs correctly in a fresh venv
uv pip install -e . --quiet && python -c "from debate import DebateSDK; print('PASS')"
```

---

## Phase 9: ISO/IEC 25010 & Nielsen's Heuristics Compliance

**Goal**: Add `rich` progress bars to `run_benchmarks()` and the interactive
CLI benchmark handler; add an ISO/IEC 25010 compliance section to `README.md`.

**Reference**: `docs/PRD_plugins_and_packaging.md §4`

### 9.1 — Tests First (`tests/test_progress.py`)

- [ ] Test `run_benchmarks(n=2)` completes without error when `rich` is available
- [ ] Test progress display is suppressed (no output) when running under pytest (no TTY)
- [ ] Test `handle_run_benchmark()` in handlers.py calls `run_benchmark()` and returns results

### 9.2 — Implementation

- [ ] `src/debate/engine/pipeline.py` — wrap `ThreadPoolExecutor` block in `rich.progress.Progress`; guard with `if sys.stdout.isatty()` so CI logs stay clean
- [ ] `src/debate/cli/handlers.py` — `handle_run_benchmark()` shows per-run progress via `rich` Live display
- [ ] `pyproject.toml` — `rich>=13.0.0` already added (Phase 2)
- [ ] `README.md` — add `## Quality Standard Compliance (ISO/IEC 25010)` section with 8-row table (see PRD §4.2)

### Phase 9 Gate

```bash
uv run pytest tests/test_progress.py -v
uv run ruff check .
# Verify rich progress renders (visual check — run manually)
uv run python main.py --runs 2 --rounds 2
# Confirm README section exists
grep -c "ISO/IEC 25010" README.md && echo "PASS" || echo "FAIL"
```

---

## Phase 7–9 Full Gate

```bash
# All tests green (coverage ≥ 85%)
uv run pytest -v --tb=short
uv run pytest --cov=src --cov-report=term-missing | tail -5

# Zero linter errors
uv run ruff check .

# No file ≥ 150 lines
find src tests main.py -name "*.py" | xargs wc -l | grep -v total | \
  awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS: all files under 150 lines"}'

# No absolute src.debate imports
grep -rn "from src\.debate" src/ && echo "FAIL" || echo "PASS: all imports relative"

# Package entry point works
uv run debate --help
```

---

## Phase 6: Advanced Features — SDK/CLI, Multithreading, Data Visualization

**Goal**: Reference-project grade. Clean public SDK surface, interactive terminal UI,
parallel benchmark execution, automated graph generation.

**Reference**: `docs/PRD_advanced_features.md`

### 6a — SDK Layer

#### 6a.1 — Tests First (`tests/test_sdk.py`)

- [ ] Test `DebateSDK()` instantiates without error (no real API call)
- [ ] Test `DebateSDK(topic="custom topic")` stores topic and passes it to agents
- [ ] Test `DebateSDK.run_single()` calls `run_debate()` exactly once (mock pipeline)
- [ ] Test `DebateSDK.run_benchmark(n=2)` calls `run_debate()` exactly 2 times
- [ ] Test `DebateSDK.export(results, path)` delegates to `BenchmarkReporter.export()`
- [ ] Test `DebateSDK.generate_analysis(json_path, out_dir)` calls `analysis.generate_all()`
- [ ] Test SDK raises `ValueError` if `run_single()` is called before a topic is set and no default exists
- [ ] Test SDK exposes no internal module references (only `debate.sdk` needed in imports)

#### 6a.2 — Implementation

- [ ] `src/debate/sdk.py` — `DebateSDK` class (≤ 100 lines)
- [ ] `src/debate/__init__.py` — re-export `DebateSDK` so `from debate import DebateSDK` works
- [ ] `config/topics.json` — list of debate topics + default (already created in Phase 2)

#### 6a Gate

```bash
uv run pytest tests/test_sdk.py -v
uv run ruff check .
wc -l src/debate/sdk.py   # must be ≤ 100
```

---

### 6b — Interactive CLI

#### 6b.1 — Tests First (`tests/test_cli.py`)

- [ ] Test `menu.display_topics(["A", "B"])` prints numbered list without error
- [ ] Test `menu.parse_choice("2", max_val=3)` returns `2`
- [ ] Test `menu.parse_choice("0", max_val=3)` raises `ValueError` (out of range)
- [ ] Test `menu.parse_choice("abc", max_val=3)` raises `ValueError` (non-integer)
- [ ] Test `handlers.handle_topic_selection(sdk, topics, "1")` sets topic to `topics[0]`
- [ ] Test `handlers.handle_run_single(sdk)` calls `sdk.run_single()` and returns result
- [ ] Test `handlers.handle_run_benchmark(sdk, n=2)` calls `sdk.run_benchmark(n=2)`
- [ ] Test `handlers.handle_generate_analysis(sdk)` calls `sdk.generate_analysis()` with correct paths
- [ ] Test `main.py --interactive` flag triggers interactive loop (mock `menu.run_loop`)
- [ ] Test `main.py` without `--interactive` flag retains existing argparse behaviour

#### 6b.2 — Implementation

- [ ] `src/debate/cli/__init__.py`
- [ ] `src/debate/cli/menu.py` — `run_loop()`, `display_menu()`, `display_topics()`, `parse_choice()` (≤ 120 lines)
- [ ] `src/debate/cli/handlers.py` — `handle_*` functions (≤ 100 lines)
- [ ] `main.py` — add `--interactive` flag, dispatch to `menu.run_loop()` (stays ≤ 20 lines)

#### 6b Gate

```bash
uv run pytest tests/test_cli.py -v
uv run ruff check .
wc -l src/debate/cli/menu.py     # ≤ 120
wc -l src/debate/cli/handlers.py # ≤ 100
wc -l main.py                    # ≤ 20
```

---

### 6c — Multithreaded Benchmarks

#### 6c.1 — Tests First (`tests/test_parallel_benchmarks.py`)

- [ ] Test `run_benchmarks(n=3)` returns exactly 3 `DebateResult` objects (mock `run_debate`)
- [ ] Test results are returned even when `run_debate` calls are non-deterministically ordered (futures)
- [ ] Test `run_benchmarks` uses at most `MAX_WORKERS` concurrent threads (patch `ThreadPoolExecutor`)
- [ ] Test `max_workers` is read from `GatekeeperConfig` (not hardcoded)
- [ ] Test a single worker exception causes `run_benchmarks` to re-raise (no silent swallow)
- [ ] Test `ApiGatekeeper` is instantiated exactly once per `run_benchmarks` call (shared across threads)
- [ ] Test thread-safety: 4 concurrent `run_debate` mock calls all complete without deadlock (timeout=5s)

#### 6c.2 — Implementation

- [ ] `src/debate/engine/pipeline.py` — replace list comprehension with `ThreadPoolExecutor` (≤ 150 lines)
- [ ] `src/debate/gatekeeper/config.py` — expose `max_workers: int` loaded from `config/rate_limits.json`
- [ ] `src/debate/config.py` — add `MAX_WORKERS: int = 4` and `ASSETS_DIR: str = "assets/"`

#### 6c Gate

```bash
uv run pytest tests/test_parallel_benchmarks.py -v
uv run ruff check .
wc -l src/debate/engine/pipeline.py  # ≤ 150
# Verify max_workers not hardcoded in Python
grep -n "max_workers\s*=\s*[0-9]" src/debate/engine/pipeline.py && echo "FAIL: hardcoded" || echo "PASS"
```

---

### 6d — Data Visualization

#### 6d.1 — Tests First (`tests/test_analysis.py`)

- [ ] Test `generate_all(json_path, out_dir)` returns a list of 4 `Path` objects
- [ ] Test all 4 returned paths exist on disk after the call (files are written)
- [ ] Test returned filenames match: `latency_per_round.png`, `tokens_per_run.png`, `cache_efficiency.png`, `winner_distribution.png`
- [ ] Test `generate_all` creates `out_dir` if it does not exist
- [ ] Test `generate_all` raises `FileNotFoundError` if `json_path` does not exist
- [ ] Test `generate_all` raises `KeyError` if JSON is missing `runs` key
- [ ] Test DPI is loaded from `config/visualization_config.json` (not hardcoded)
- [ ] Test format is loaded from `config/visualization_config.json` (not hardcoded)
- [ ] Test `generate_all` with a 1-run JSON produces valid graphs (no crash on single-item stats)
- [ ] Test `generate_all` with `n=5` runs produces `latency_per_round.png` with correct data shape

#### 6d.2 — Implementation

- [ ] `src/debate/analysis.py` — `generate_all()` + 4 `_plot_*` helpers (≤ 150 lines)
- [ ] `config/visualization_config.json` — DPI, format, style, figsize, assets_dir (already created in Phase 2)
- [ ] `assets/` — add to `.gitignore` (generated files)
- [ ] `pyproject.toml` — add `matplotlib>=3.8.0` and `seaborn>=0.13.0`
- [ ] `uv sync`

#### 6d Gate

```bash
uv run pytest tests/test_analysis.py -v
uv run ruff check .
wc -l src/debate/analysis.py  # ≤ 150
# Confirm assets/ is gitignored
grep "assets/" .gitignore && echo "PASS" || echo "FAIL: add assets/ to .gitignore"
```

---

### Phase 6 Full Gate

```bash
# All tests green (all phases)
uv run pytest -v --tb=short

# Coverage ≥ 85%
uv run pytest --cov=src --cov-report=term-missing | tail -10

# Zero linter errors
uv run ruff check .

# No file ≥ 150 lines
find src tests main.py -name "*.py" | xargs wc -l | grep -v total | \
  awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS: all files under 150 lines"}'

# main.py stays ≤ 20 lines
wc -l main.py

# No hardcoded max_workers in Python
grep -rn "ThreadPoolExecutor([0-9]" src/ && echo "FAIL: hardcoded workers" || echo "PASS"

# Assets generated by analysis
uv run python -c "
from debate.sdk import DebateSDK
sdk = DebateSDK()
paths = sdk.generate_analysis('debate_systems_research.json', 'assets/')
print('Generated:', [p.name for p in paths])
"
```

---

## Phase 4: Production-Grade Logging (FIFO Rotating Logger)

**Goal**: Replace all `print()` calls with a structured, file-rotating logger. All parameters
loaded from `config/logging_config.json`. Zero hardcoded values in Python.

**Reference**: `docs/PRD_logging.md`

### 4.1 — Tests First (`tests/test_logger.py`)

- [ ] Test `get_logger("x")` returns a `DebateLogger` instance
- [ ] Test `DebateLogger` exposes `.debug()`, `.info()`, `.warning()`, `.error()` methods
- [ ] Test config loads `max_files` and `max_lines` from `config/logging_config.json` (not defaults)
- [ ] Test `log_dir` is created on first use if it does not exist
- [ ] Test a single log file is created after calling `.info("msg")`
- [ ] Test log file contains the logged message string
- [ ] Test line-count rotation: writing `max_lines + 1` lines creates a second log file
- [ ] Test after rotation, the old file contains exactly `max_lines` lines
- [ ] Test FIFO eviction: when `max_files + 1` files exist, oldest file is deleted
- [ ] Test after FIFO eviction, exactly `max_files` files remain in `log_dir`
- [ ] Test `get_logger("a")` and `get_logger("a")` return the same underlying logger (no handler duplication)
- [ ] Test log format includes timestamp, level, name, and message fields
- [ ] Test `emit()` is thread-safe: 10 concurrent threads each writing 50 lines produce no interleaved corruption

### 4.2 — Implementation

- [ ] `src/debate/logging/__init__.py` — exports `get_logger(name: str) -> DebateLogger`
- [ ] `src/debate/logging/logger.py` — `LoggingConfig` dataclass, `FifoRotatingHandler`, `DebateLogger`
- [ ] `logs/` added to `.gitignore`
- [ ] `uv run ruff check .` — 0 errors
- [ ] `find src tests main.py -name "*.py" | xargs wc -l` — no file ≥ 150 lines

### 4.3 — Refactor: Replace `print()` with Logger

- [ ] `main.py` — replace `print(f"Done ...")` with `logger.info(...)`
- [ ] `src/debate/engine/pipeline.py` — add `INFO` logs for debate start, each round, verdict
- [ ] `src/debate/agents/pro.py` — add `DEBUG` log for claim generation and token usage
- [ ] `src/debate/agents/con.py` — add `DEBUG` log for claim generation and token usage
- [ ] Verify: `grep -rn "print(" src/ main.py` returns 0 matches

### Phase 4 Gate

```bash
# All tests green (including new test_logger.py)
uv run pytest -v

# Zero linter errors
uv run ruff check .

# No file ≥ 150 lines
find src tests main.py -name "*.py" | xargs wc -l | grep -v total | awk '$1 >= 150 {print "FAIL:", $0; found=1} END {if (!found) print "PASS: all files under 150 lines"}'

# No print() calls remain
grep -rn "print(" src/ main.py && echo "FAIL: print() found" || echo "PASS: no print() calls"

# No hardcoded logging values in Python
grep -n "500\|\"logs/\"\|max_files\s*=\s*20" src/debate/logging/logger.py && echo "FAIL: hardcoded value" || echo "PASS: config-driven"
```
