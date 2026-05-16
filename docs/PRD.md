# PRD: Deterministic Multi-Agent AI Debate System

**Version:** 1.0
**Author:** Avi Ayeli
**Topic:** *"Will AI replace software engineers in the next 5 years?"*
**Classification:** University Thesis — Research Grade
**Date:** 2026-05-16

---

## Abstract

This document specifies requirements for a research-grade, deterministic Multi-Agent AI Debate System producing reproducible, academically rigorous debate outcomes. Two LLM-powered agents (PRO, CON) operate under strict Pydantic schemas, a pure-Python Responsiveness Score, a permanent V₁ semantic anchor preventing positional drift, and FinOps-grade context truncation eliminating exponential token burn across N=5 benchmark runs of 10-round debates.

---

## 1. Problem Statement

Multi-agent LLM debates suffer from three failure modes that undermine research validity:

1. **Non-determinism**: LLM temperature and sampling cause irreproducible outcomes. Without anchoring, semantic positions drift unpredictably across rounds.
2. **Exponential Context Growth**: A 10-round debate passing full history grows O(n²) in tokens. N=5 benchmarks risk uncontrolled API cost explosions (~$4.50 unoptimized vs ~$0.45 optimized).
3. **Positional Capitulation**: Agents under iterative pressure gradually migrate toward the opponent's semantic centroid, invalidating comparative analysis of argument strength.

---

## 2. System Overview

The system orchestrates a structured debate over `MAX_ROUNDS` (default: 10) rounds between:

- **PRO Agent**: Argues AI *will* replace software engineers within 5 years.
- **CON Agent**: Argues AI *will not* replace software engineers within 5 years.

Each agent generates one `ClaimPayloadSchema` per round. A deterministic **Judge** evaluates all rounds and declares a singular winner via a pure-Python hierarchical tiebreaker. A **BenchmarkReporter** exports `debate_systems_research.json` after N=5 runs.

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

The Round-1 embedding (V₁) is a frozen semantic fingerprint of the agent's initial position — its *ideological anchor*. This is the single most critical state invariant in the system.

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

Embeddings are computed locally via `sentence-transformers` (model: `all-MiniLM-L6-v2`). Local inference guarantees determinism given fixed model weights and eliminates an additional API cost surface.

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

All drift thresholds are loaded at startup from `.env` via `pydantic-settings`. Hardcoding these values anywhere in the source is a constraint violation.

| Parameter | Default | Type | Description |
|---|---|---|---|
| `RECENCY_DECAY_LAMBDA` | `0.3` | `float` | Exponential decay weight for centroid averaging |
| `V1_DISTANCE_THRESHOLD` | `0.4` | `float` | Max cosine distance from V₁ before drift penalty |
| `CENTROID_ALIGNMENT_THRESHOLD` | `0.7` | `float` | Cosine similarity to opponent centroid triggering penalty |
| `ANTHROPIC_API_KEY` | — | `str` | Required for LLM agent calls |
| `MAX_ROUNDS` | `10` | `int` | Rounds per debate |
| `BENCHMARK_RUNS` | `5` | `int` | N for benchmark loop |
| `LEDGER_WINDOW` | `3` | `int` | Rolling window size for LLM context (rounds 4+) |

---

## 5. FinOps & Context Economy

### 5.1 Ledger Truncation Strategy

To prevent O(n²) token growth across N=5 × 10-round benchmarks, a strict truncation protocol applies:

| Round Range | Context Passed to LLM |
|---|---|
| Rounds 1–3 | Full claim history (compact JSON, not prose) |
| Rounds 4+ | Last `LEDGER_WINDOW` (default: 3) rounds only |

Claims are serialized as structured JSON via `LedgerManager.serialize_for_llm()`. V₁ is **excluded from all LLM prompts** — it lives in `BaseAgent.v1_embedding` only.

### 5.2 Prompt Caching

The static system prompt (debate topic + rules + agent persona) is sent as a **cached prefix** using Anthropic's `cache_control` prompt caching API. This amortizes the cost of the static portion across all rounds.

Caching applies to:
- System prompt (debate rules, agent role definition, output schema instructions)
- Topic statement

Not cached (dynamic per round):
- Opponent's windowed ledger JSON
- Current round number

### 5.3 Token Budget Projection

| Configuration | Est. Tokens/Debate | Est. Cost (sonnet-4-6) |
|---|---|---|
| Baseline (no optimizations) | ~180,000 | ~$0.90 |
| Ledger truncation only | ~45,000 | ~$0.23 |
| Truncation + prompt caching | ~18,000 | ~$0.09 |
| **N=5 optimized total** | **~90,000** | **~$0.45** |

---

## 6. Judge: Scoring & Tiebreaker Hierarchy

### 6.1 Base Scoring Model

The Judge aggregates per-round component scores into a total for each agent:

```
total_score(agent) = Σ_rounds [
    mean(evidence.quality_score)        # EvidenceSchema quality aggregate
  − semantic_drift_penalty              # from SemanticDriftEvaluator
  + responsiveness_score                # pure Python Responsiveness Calculator
]
```

### 6.2 Hierarchical Tiebreaker (Pure Python, No LLM)

When `|total_score(PRO) − total_score(CON)| < TIE_EPSILON (0.001)`, the following hierarchy resolves the winner in strict sequential order. Each level is attempted only if the previous level also ties.

**Level 1 — Evidence Quality:**
Agent with higher mean `EvidenceSchema.quality_score` across all rounds wins.

**Level 2 — Lowest Contradictions (V₁ Faithfulness):**
Agent with smaller `cosine_distance(final_round_embedding, agent.v1_embedding)` wins. Measures which agent stayed most faithful to its founding position.

**Level 3 — Highest Responsiveness:**
Agent with higher mean Responsiveness Score across all rounds wins.

**Level 4 — Seeded PRNG Coin Flip:**
```python
random.Random(seed=int(debate_id_hash, 16) % (2**32)).choice(["PRO", "CON"])
```
Seeded by `debate_id` hash for reproducibility across identical runs.

**Critical invariant**: All four tiebreaker levels use pure Python arithmetic only. No LLM inference. The `VerdictSchema` records which level was used in `tiebreaker_used`.

### 6.3 Verdict Output

The Judge always produces a `VerdictSchema`. The `winner` field is **never null**.

```python
class VerdictSchema(BaseModel):
    winner: Literal["PRO", "CON"]      # singular, never null
    pro_score: float
    con_score: float
    tiebreaker_used: Optional[str]     # "evidence" | "contradiction" | "responsiveness" | "prng"
    evidence_quality_pro: float
    evidence_quality_con: float
    v1_distance_pro: float
    v1_distance_con: float
    responsiveness_pro: float
    responsiveness_con: float
    reasoning: str
```

---

## 7. Benchmark Output Specification

After N=5 runs, `BenchmarkReporter` writes `debate_systems_research.json` to the project root.

```json
{
  "benchmark_metadata": {
    "n_runs": 5,
    "max_rounds": 10,
    "topic": "Will AI replace software engineers in the next 5 years?",
    "model": "claude-sonnet-4-6",
    "embedding_model": "all-MiniLM-L6-v2",
    "generated_at": "2026-05-16T12:00:00Z"
  },
  "runs": [
    {
      "run_id": 1,
      "latency_per_round": [2.1, 1.8, 2.3, 1.9, 2.0, 1.7, 2.1, 1.8, 2.2, 1.9],
      "tokens_per_debate": 17843,
      "cost_per_debate": 0.089,
      "context_cache_efficiency": 0.87,
      "winner": "CON",
      "tiebreaker_used": null
    }
  ],
  "aggregates": {
    "mean_tokens_per_debate": 18200,
    "mean_cost_per_debate": 0.091,
    "mean_latency_per_round": 2.1,
    "mean_cache_efficiency": 0.85
  }
}
```

All four top-level fields under each run — `latency_per_round`, `tokens_per_debate`, `cost_per_debate`, `context_cache_efficiency` — are **mandatory**. Absent fields constitute a benchmark failure.

---

## 8. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `anthropic` | `>=0.40.0` | LLM inference for PRO/CON agents; prompt caching API |
| `sentence-transformers` | `>=3.0.0` | Local deterministic embeddings for V₁ and drift |
| `numpy` | `>=1.26.0` | Cosine distance, weighted centroid arithmetic |
| `pydantic` | `>=2.13.4` | Schema enforcement, IPC validation |
| `pydantic-settings` | `>=2.0.0` | `.env` hyperparameter loading |
| `python-dotenv` | `>=1.2.2` | `.env` file discovery |
| `pytest` | `>=9.0.3` | TDD test runner |
| `ruff` | `>=0.15.13` | Linter — zero-error mandate |

---

## 9. Non-Functional Requirements

| Requirement | Rule | Enforcement |
|---|---|---|
| File size hard limit | **No Python file may exceed 150 lines** | `wc -l` gate in Phase 3 |
| CLI thinness | `main.py` must be ≤ 20 lines | Automated gate |
| Orchestration locality | All execution logic lives in `pipeline.py` | Code review |
| TDD mandate | Tests written **before** implementation each phase | Phase gates |
| Linter | `uv run ruff check .` exits with **0 errors** | Phase gates |
| Package manager | `uv` exclusively | No `pip` calls |
| LLM determinism | `temperature=0` for all Anthropic API calls | Agent implementation |
| PRNG reproducibility | All coin flips seeded by `debate_id` hash | Judge implementation |
| Embedding determinism | Local `sentence-transformers` only | No embedding API calls |
