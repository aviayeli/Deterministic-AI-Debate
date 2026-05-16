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

## Hard Constraints (never skip)

| Check | Command |
|---|---|
| All tests pass | `uv run pytest -v` |
| Linter clean | `uv run ruff check .` |
| No file ≥ 150 lines | `find src tests main.py -name "*.py" \| xargs wc -l` |
| `main.py` ≤ 20 lines | `wc -l main.py` |
| `pipeline.py` ≤ 150 lines | `wc -l src/debate/engine/pipeline.py` |
| No hardcoded hyperparameters | `grep -r "0\.3\|0\.4" src/ --include="*.py"` (should hit only defaults in config.py) |
