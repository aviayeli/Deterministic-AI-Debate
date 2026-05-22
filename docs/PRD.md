# PRD: Deterministic Multi-Agent AI Debate System

**Version:** 2.0 (Final — Submission)
**Author:** Avi Ayeli
**Topic:** *"Will AI replace software engineers in the next 5 years?"*
**Classification:** University Thesis — Research Grade
**Date:** 2026-05-22

---

## Abstract

This document specifies the requirements implemented in the Deterministic Multi-Agent AI Debate System (v1.0.0). Three LLM-powered agents (PRO, CON, and a FactChecker subagent) operate under strict Pydantic schemas, a pure-Python Responsiveness Score, a permanent V₁ semantic anchor preventing positional drift, FinOps-grade context truncation, a production-grade API Gatekeeper with token-bucket rate limiting and exponential-backoff retry, and a circuit-breaker Watchdog. All 247 tests pass with zero API calls required.

---

## 1. Problem Statement

Multi-agent LLM debates suffer from three failure modes that undermine research validity:

1. **Non-determinism**: LLM temperature and sampling cause irreproducible outcomes. Without anchoring, semantic positions drift unpredictably across rounds.
2. **Exponential Context Growth**: A 10-round debate passing full history grows O(n²) in tokens. N=5 benchmarks risk uncontrolled API cost explosions.
3. **Positional Capitulation**: Agents under iterative pressure gradually migrate toward the opponent's semantic centroid, invalidating comparative analysis of argument strength.

---

## 2. System Overview

The system orchestrates a structured debate over `MAX_ROUNDS` (default: 10) rounds between:

- **PRO Agent**: Argues AI *will* replace software engineers within 5 years.
- **CON Agent**: Argues AI *will not* replace software engineers within 5 years.
- **FactChecker Subagent**: Verifies opponent claims via web search; prepends objections when contradictions are found.

Each agent generates one `ClaimPayloadSchema` per round. A deterministic **Judge** evaluates all rounds and declares a winner via a four-level pure-Python tiebreaker. A **BenchmarkReporter** exports `debate_systems_research.json` after N runs. A **TopicRouter** selects skill-based prompt enrichments from a static library. A thread-safe **EventBus** exposes six typed lifecycle hook points for plugin registration.

---

## 3. Deterministic IPC Protocol

### 3.1 ClaimPayloadSchema

All inter-agent communication is strictly typed via Pydantic v2. No unvalidated dicts or strings cross module boundaries.

```python
class EvidenceSchema(BaseModel):
    source: str
    quality_score: float = Field(ge=0.0, le=1.0)
    citation: str

class ClaimPayloadSchema(BaseModel):
    claim_id: str                        # UUID4, auto-generated
    agent_id: str                        # "PRO" | "CON"
    round_number: int = Field(ge=1)
    stance: Literal["PRO", "CON"]
    claim_text: str
    addressed_claim_ids: List[str]       # MANDATORY: IDs from opponent's ledger
    evidence: List[EvidenceSchema] = []
    timestamp: datetime
```

The `addressed_claim_ids` field is **mandatory** and must reference `claim_id` values that exist in the opponent's current ledger. Any claim referencing non-existent IDs is penalized proportionally by the Responsiveness Score.

### 3.2 Responsiveness Score (Pure Python — No LLM)

The Responsiveness Score is computed exclusively by pure Python logic. No LLM inference is permitted in this calculation under any circumstances.

```
Responsiveness(agent, round) =
    |valid_addressed_ids| / max(|opponent_ledger|, 1)

where valid_addressed_ids = addressed_claim_ids ∩ {e.claim.claim_id for e in opponent_ledger}
```

This is an O(n) set intersection over UUID strings. The result is a float in [0.0, 1.0].

**Invariant**: The tiebreaker and all scoring logic invoking this formula must be purely algorithmic.

---

## 4. V₁ Anchor & Semantic Drift Prevention

### 4.1 Permanent V₁ Embedding Storage

The Round-1 embedding (V₁) is a frozen semantic fingerprint of the agent's initial position — its *ideological anchor*.

**Storage rules (ABSOLUTE, non-negotiable):**

| Rule | Description |
|---|---|
| **Computed once** | From the agent's Round 1 `ClaimPayloadSchema.claim_text` |
| **Stored permanently** | As `BaseAgent.v1_embedding: List[float]` in agent RAM |
| **Never truncated** | Survives Ledger windowing; is never part of the rolling window |
| **Never sent to LLM** | Excluded from all prompt context; used only by the evaluator |
| **Immutable after set** | `set_v1_embedding()` raises `RuntimeError` if called a second time |

Separation is critical: the Ledger window is truncated for FinOps at round 4+, but V₁ persists in agent state for the full debate lifetime and is accessed directly by `SemanticDriftEvaluator`.

### 4.2 SemanticDriftEvaluator

Embeddings are computed locally via `sentence-transformers` (model: `all-MiniLM-L6-v2`, dimension: 384). Local inference guarantees determinism given fixed model weights and eliminates an additional API cost surface.

Two penalty conditions are evaluated per round:

**Condition 1 — V₁ Distance Penalty:**
```
if cosine_distance(current_embedding, agent.v1_embedding) > V1_DISTANCE_THRESHOLD:
    apply drift_penalty
```

**Condition 2 — Centroid Alignment Penalty:**
```
if cosine_similarity(current_embedding, opponent_rolling_centroid) > CENTROID_ALIGNMENT_THRESHOLD:
    apply alignment_penalty
```

The opponent's rolling centroid is computed as a decay-weighted mean:

```
centroid(t) = Σᵢ [ λ^(t−i) · eᵢ ] / Σᵢ [ λ^(t−i) ]

where:  λ = RECENCY_DECAY_LAMBDA (loaded from .env)
        i iterates over available round indices
        eᵢ = opponent's embedding at round i
```

### 4.3 Configurable Hyperparameters (.env)

All drift thresholds are loaded at startup from `.env` via `pydantic-settings`.

| Parameter | Default | Type | Description |
|---|---|---|---|
| `RECENCY_DECAY_LAMBDA` | `0.3` | `float` | Exponential decay weight for centroid averaging |
| `V1_DISTANCE_THRESHOLD` | `0.4` | `float` | Max cosine distance from V₁ before drift penalty |
| `CENTROID_ALIGNMENT_THRESHOLD` | `0.7` | `float` | Cosine similarity to opponent centroid triggering penalty |
| `ANTHROPIC_API_KEY` | — | `str` | Required for LLM agent calls |
| `MAX_ROUNDS` | `10` | `int` | Rounds per debate |
| `BENCHMARK_RUNS` | `5` | `int` | N for benchmark loop |
| `LEDGER_WINDOW` | `3` | `int` | Rolling window size for LLM context (rounds 4+) |
| `LLM_MODEL` | `claude-sonnet-4-6` | `str` | Anthropic model identifier |
| `MAX_WORKERS` | `4` | `int` | Thread pool size for parallel benchmarks |

---

## 5. FinOps & Context Economy

### 5.1 Ledger Truncation Strategy

To prevent O(n²) token growth across N×10-round benchmarks, a strict truncation protocol applies:

| Round Range | Context Passed to LLM |
|---|---|
| Rounds 1–3 | Full claim history (compact JSON, not prose) |
| Rounds 4+ | Last `LEDGER_WINDOW` (default: 3) rounds only |

Claims are serialized as structured JSON via `LedgerManager.serialize_for_llm()`. V₁ is **excluded from all LLM prompts** — it lives in `BaseAgent.v1_embedding` only.

### 5.2 Token Budget Projection

| Configuration | Est. Tokens/Debate | Est. Cost (sonnet-4-6) |
|---|---|---|
| Baseline (no optimizations) | ~180,000 | ~$0.90 |
| Ledger truncation only | ~45,000 | ~$0.23 |
| Truncation + prompt caching | ~18,000 | ~$0.09 |
| **N=5 optimized total** | **~90,000** | **~$0.45** |

---

## 6. API Gatekeeper & Watchdog

### 6.1 ApiGatekeeper

All Anthropic API calls are routed exclusively through the `ApiGatekeeper`. It is instantiated **once per benchmark run** and shared across all parallel threads. No agent calls `anthropic.messages.create()` directly.

**Responsibilities:**
- **Token-bucket rate limiter**: Refills at `requests_per_minute / 60` tokens per second. Blocks (sleeps) if the bucket is empty.
- **Timeout enforcement**: `timeout_seconds` is passed directly to the Anthropic SDK on every call.
- **Retry with exponential backoff**: Retries on `RateLimitError` (429), `APITimeoutError`, `APIConnectionError`, and `InternalServerError` with status codes in `retryable_status_codes`. Wait formula: `backoff_factor × 2^attempt + U(0, 0.5)`.
- **Fast-fail on non-retryable errors**: `AuthenticationError` (401) and `BadRequestError` (400) are raised immediately.

All configuration is loaded from `config/rate_limits.json` — no values are hardcoded in Python.

**Error hierarchy:**
```
GatekeeperError
├── GatekeeperTimeoutError   (all retries exhausted on timeout)
└── GatekeeperRateLimitError (all retries exhausted on 429)
```

### 6.2 Watchdog (Circuit Breaker)

The `Watchdog` class implements a thread-safe circuit-breaker pattern that monitors failure rates and trips when consecutive failures exceed `failure_threshold` (default: 3).

**State machine:**
- **Closed** (normal): `guard(fn)` calls `fn`, records success/failure
- **Open** (tripped): `guard(fn)` raises `WatchdogTrippedError` immediately — no calls attempted
- **Reset**: `watchdog.reset()` clears all state and closes the circuit

`record_success()` decrements the failure count (healing behaviour). All state mutations are protected by `threading.Lock`.

Both `ApiGatekeeper` and `Watchdog` write to the shared enterprise logger (`src/debate/shared/logger.py`) — retries logged at `WARNING`, terminal failures at `ERROR`, circuit trips at `WARNING`.

---

## 7. FactChecker Subagent

The `FactCheckerSubagent` is a bonus subagent that performs real-time web fact-checking against opponent claims. It is injected into `ProAgent` and `ConAgent` at construction time (optional).

**Workflow:**
1. Before generating a claim, the agent passes the opponent's most recent claim text to `FactCheckerSubagent.check()`.
2. `check()` queries the DuckDuckGo instant-answer API (no API key required; silent fallback on network failure).
3. If the result contains a contradiction marker (`"debunked"`, `"incorrect"`, `"misleading"`, etc.), the snippet is returned as a `proof` string.
4. The agent prepends `**OBJECTION! Fake News!** {proof}` to its generated claim via `format_objection()`.

This is **deterministic**: the objection is triggered by regex pattern matching on the search result, not by LLM judgement.

---

## 8. TopicRouter & Skill Library

The `TopicRouter` runs **once per debate** at agent construction time. It keyword-matches the debate topic against six skill categories and injects concise skill instructions into both agents' system prompts as `extra_instructions`.

**Skill categories:**
| Skill | Trigger Keywords | Instruction |
|---|---|---|
| `technical` | engineer, software, code, program | Emphasize technical depth and domain knowledge |
| `economic` | replace, job, employ, labor, automat | Frame in cost, efficiency, labor markets |
| `statistical` | data, statistic, percent, study | Prioritize empirical data and peer-reviewed studies |
| `ethical` | ethic, fair, moral, society, bias | Address fairness, autonomy, societal impact |
| `historical` | history, past, industri, revolution | Draw upon historical precedents |
| `causal` | cause, lead to, result, because | Explain causal chains; avoid correlation-as-causation |

Default (no keyword match): `economic` + `technical`.

This avoids passing the full skill library in every round, keeping prompt tokens bounded.

---

## 9. Judge: Scoring & Tiebreaker Hierarchy

### 9.1 Discourse Civility Policy

Before scoring, the `DiscourseChecker` applies a deterministic penalty to each agent's effective score. It scans all claims in the agent's ledger for 11 defined violation patterns (insults, profanity, personal attacks). Each distinct match deducts `0.05`, capped at `0.25` total.

This policy is applied post-debate to preserve benchmark reproducibility — the debate runs without interruption.

### 9.2 Primary Scoring Model

```
effective_score(agent) =
    max(0, mean_responsiveness_across_rounds − discourse_penalty)
```

### 9.3 Hierarchical Tiebreaker (Pure Python, No LLM)

When `|effective_score(PRO) − effective_score(CON)| < 1e-9`, the following hierarchy resolves the winner in strict sequential order:

| Level | Criterion | `tiebreaker_used` |
|---|---|---|
| 1 | Higher mean `EvidenceSchema.quality_score` across all rounds | `"evidence_quality"` |
| 2 | Lower `cosine_distance(final_embedding, v1_embedding)` — V₁ faithfulness | `"v1_faithfulness"` |
| 3 | `random.Random(seed).random() < 0.5` — seeded by `SHA-256(debate_id) % 2³²` | `"prng"` |

**Critical invariant**: All tiebreaker levels use pure Python arithmetic only. No LLM inference. `VerdictSchema.winner` is **never null**.

### 9.4 Verdict Output

```python
class VerdictSchema(BaseModel):
    winner: Literal["PRO", "CON"]       # singular, never null
    pro_score: float
    con_score: float
    tiebreaker_used: str | None         # "evidence_quality" | "v1_faithfulness" | "prng"
    evidence_quality_pro: float
    evidence_quality_con: float
    v1_distance_pro: float
    v1_distance_con: float
    responsiveness_pro: float
    responsiveness_con: float
    reasoning: str
```

---

## 10. Plugin & Event System

The `EventBus` provides a thread-safe publish-subscribe architecture. External plugins register `Callable` handlers via `DebateSDK.on(event_name, handler)` before calling `run_single()` or `run_benchmark()`. `pipeline.run_debate()` emits events at fixed hook points with no knowledge of registered consumers (Open-Closed Principle).

**Six typed lifecycle events:**

| Event | Emitted when |
|---|---|
| `DebateStartEvent` | Before round 1 begins |
| `RoundStartEvent` | At the start of each round |
| `AgentReplyEvent` | After each agent generates a claim |
| `RoundEndEvent` | After both agents reply and round metrics are computed |
| `BeforeEvaluationEvent` | After the final round, before the Judge runs |
| `DebateEndEvent` | After the `VerdictSchema` is produced |

Handler exceptions propagate out of `emit()` by design — loudness is the correct default for an academic system.

---

## 11. Benchmark Output Specification

After N runs, `BenchmarkReporter` writes `debate_systems_research.json`.

```json
{
  "benchmark_metadata": {
    "n_runs": 5,
    "max_rounds": 10,
    "topic": "Will AI replace software engineers in the next 5 years?",
    "model": "claude-sonnet-4-6",
    "embedding_model": "all-MiniLM-L6-v2",
    "generated_at": "2026-05-22T12:00:00Z"
  },
  "runs": [
    {
      "run_id": 1,
      "latency_per_round": [2.1, 1.8, 2.3, 1.9, 2.0, 1.7, 2.1, 1.8, 2.2, 1.9],
      "tokens_per_debate": 17843,
      "cost_per_debate": 0.054,
      "context_cache_efficiency": 0.87,
      "winner": "CON",
      "tiebreaker_used": null
    }
  ],
  "aggregates": {
    "mean_tokens_per_debate": 18200,
    "mean_cost_per_debate": 0.055,
    "mean_latency_per_round": 2.1,
    "mean_cache_efficiency": 0.85
  }
}
```

All four per-run fields — `latency_per_round`, `tokens_per_debate`, `cost_per_debate`, `context_cache_efficiency` — are **mandatory**.

---

## 12. Parallel Benchmark Execution

`run_benchmarks(n)` uses `ThreadPoolExecutor(max_workers=gk_config.max_workers)`. Each debate session runs in its own thread. A single `ApiGatekeeper` instance is shared across all threads; its internal `threading.Lock` serialises token-bucket access.

Results are collected via `concurrent.futures.as_completed()` and displayed with `rich.progress` when running in a TTY. Progress is suppressed in CI (non-TTY) to keep logs clean.

---

## 13. Hyperparameter Sensitivity Analysis

The `SensitivityRunner` sweeps the Cartesian product of temperature values and `max_rounds` values, running `runs_per_config` independent debates per configuration cell and collecting aggregate metrics for the thesis's empirical analysis.

### 13.1 SensitivityConfig

```python
@dataclass
class SensitivityConfig:
    temperatures: List[float]       # default: [0.0, 0.5, 1.0]
    max_rounds_values: List[int]    # default: [2, 5, 10]
    runs_per_config: int = 1
```

### 13.2 SensitivityResult

For each grid cell the runner produces:

| Field | Description |
|---|---|
| `temperature` | LLM temperature used for this configuration |
| `max_rounds` | Debate length for this configuration |
| `tiebreaker_count` | Number of runs that required tiebreaker resolution |
| `context_truncation_count` | Total rounds where opponent context was windowed (`max(0, rounds − LEDGER_WINDOW)`) |
| `mean_tokens` | Mean token consumption across runs in this cell |
| `run_count` | Number of runs completed in this cell |

**Truncation counting invariant**: `context_truncation_count = max(0, max_rounds − LEDGER_WINDOW)`. This quantifies how many rounds in each configuration cell experienced FinOps context windowing — the primary tool for isolating the cost of the truncation decision.

### 13.3 Design Constraints

The `SensitivityRunner` creates fresh `ProAgent` / `ConAgent` instances per configuration cell to prevent cross-contamination of V₁ anchors. It is injected with an `ApiGatekeeper` instance and runs the full Cartesian product sequentially; parallelism is left to the caller. The runner lives in `src/debate/sensitivity_runner.py` and is covered by 13 tests in `tests/test_sensitivity.py`.

---

## 14. Cost Forecasting

Before any benchmark run the CLI estimates token consumption and dollar cost, prints a one-line summary, and requires explicit confirmation (Y/N). Declining returns `[]` without making any API calls.

Formula: `n_runs × max_rounds × 2 agents × 500 avg_tokens/call × $0.01/1000 tokens`.

---

## 15. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `anthropic` | `>=0.40.0` | LLM inference for PRO/CON agents |
| `sentence-transformers` | `>=3.0.0` | Local deterministic embeddings (all-MiniLM-L6-v2) |
| `numpy` | `>=1.26.0` | Cosine distance, weighted centroid arithmetic |
| `pydantic` | `>=2.13.4` | Schema enforcement, IPC validation |
| `pydantic-settings` | `>=2.0.0` | `.env` hyperparameter loading |
| `python-dotenv` | `>=1.2.2` | `.env` file discovery |
| `rich` | `>=13.0.0` | Terminal progress bars, formatted output |
| `matplotlib` | `>=3.8.0` | Benchmark graph generation |
| `seaborn` | `>=0.13.0` | Statistical plot styling |
| `pytest` | `>=9.0.3` | TDD test runner |
| `ruff` | `>=0.15.13` | Linter — zero-error mandate |

---

## 16. Non-Functional Requirements

| Requirement | Rule | Status |
|---|---|---|
| File size hard limit | No Python file may exceed 150 lines | ✅ Max: 146 lines (`pipeline.py`) |
| CLI thinness | `main.py` must be ≤ 20 lines | ✅ 20 lines |
| Orchestration locality | All execution logic lives in `pipeline.py` | ✅ Enforced |
| TDD mandate | Tests written before implementation each phase | ✅ 247 tests |
| Linter | `uv run ruff check .` exits with 0 errors | ✅ Clean |
| Package manager | `uv` exclusively | ✅ No pip calls |
| LLM determinism | `temperature=0` for all Anthropic API calls | ✅ Enforced in agents |
| PRNG reproducibility | All coin flips seeded by `debate_id` hash | ✅ SHA-256 seed |
| Embedding determinism | Local `sentence-transformers` only | ✅ No embedding API |
| Gatekeeper | All LLM calls through `ApiGatekeeper` | ✅ Enforced |
| Watchdog | Circuit breaker kills/protects on repeated failure | ✅ Implemented |
