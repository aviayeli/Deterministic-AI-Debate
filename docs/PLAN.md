# PLAN: Fragmented OOP Architecture

**Constraint**: No Python file may exceed 150 lines. `main.py` ≤ 20 lines.
**Principle**: Every module has one responsibility. `pipeline.py` orchestrates; nothing else does.

---

## Module Tree with Line Budgets

```
deterministic-ai-debate/
│
├── main.py                                    ≤  20 lines  [HARD LIMIT — CLI shim only]
├── .env                                       (config, not Python)
├── pyproject.toml
│
├── src/debate/
│   ├── __init__.py                            ~   5 lines
│   ├── config.py                              ~  30 lines  pydantic-settings, .env loading
│   │
│   ├── schemas/                               ← IPC contracts (data only, no logic)
│   │   ├── __init__.py                        ~   5 lines
│   │   ├── claim.py                           ~  55 lines  EvidenceSchema, ClaimPayloadSchema
│   │   ├── round.py                           ~  45 lines  LedgerEntry, RoundSchema
│   │   └── verdict.py                         ~  45 lines  VerdictSchema
│   │
│   ├── agents/                                ← LLM wrappers (API calls only)
│   │   ├── __init__.py                        ~   5 lines
│   │   ├── base.py                            ~  85 lines  BaseAgent + permanent V₁ state
│   │   ├── pro.py                             ~  80 lines  ProAgent (Anthropic, cached prompt)
│   │   └── con.py                             ~  80 lines  ConAgent (Anthropic, cached prompt)
│   │
│   ├── engine/                                ← orchestration + data management
│   │   ├── __init__.py                        ~   5 lines
│   │   ├── pipeline.py                        ~ 145 lines  MAIN ORCHESTRATOR [≤150 HARD]
│   │   ├── ledger.py                          ~  75 lines  LedgerManager + truncation logic
│   │   └── embeddings.py                      ~  65 lines  EmbeddingService (sentence-transformers)
│   │
│   ├── evaluation/                            ← scoring (pure Python, zero LLM calls)
│   │   ├── __init__.py                        ~   5 lines
│   │   ├── semantic_drift.py                  ~ 100 lines  SemanticDriftEvaluator
│   │   ├── responsiveness.py                  ~  60 lines  ResponsivenessCalculator
│   │   └── judge.py                           ~ 130 lines  Judge + tiebreaker hierarchy
│   │
│   └── benchmarks/
│       ├── __init__.py                        ~   5 lines
│       └── reporter.py                        ~  65 lines  BenchmarkReporter → JSON export
│
└── tests/
    ├── conftest.py                            ~  40 lines  shared fixtures
    ├── test_schemas.py                        ~  80 lines  Phase 1
    ├── test_embeddings.py                     ~  50 lines  Phase 2a
    ├── test_semantic_drift.py                 ~  90 lines  Phase 2a
    ├── test_responsiveness.py                 ~  70 lines  Phase 2a
    ├── test_ledger.py                         ~  60 lines  Phase 2b
    ├── test_judge.py                          ~ 100 lines  Phase 2b
    └── test_pipeline.py                       ~ 120 lines  Phase 3
```

---

## Per-Module Responsibilities

### `main.py` (≤ 20 lines — enforced)

Single responsibility: parse CLI args, delegate entirely to `pipeline`.

```
argparse: --runs N (default 5), --rounds R (default 10), --topic "..."
call: pipeline.run_benchmarks(n=N, rounds=R, topic=topic)
print: winner summary + output file path
```

No business logic. No imports beyond `argparse`, `sys`, `pipeline`.

---

### `src/debate/config.py` (~30 lines)

Single responsibility: load `.env` into a typed `Settings` singleton.

```python
class Settings(BaseSettings):
    RECENCY_DECAY_LAMBDA: float = 0.3
    V1_DISTANCE_THRESHOLD: float = 0.4
    CENTROID_ALIGNMENT_THRESHOLD: float = 0.7
    ANTHROPIC_API_KEY: str
    MAX_ROUNDS: int = 10
    BENCHMARK_RUNS: int = 5
    LEDGER_WINDOW: int = 3
    LLM_MODEL: str = "claude-sonnet-4-6"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

settings = Settings()
```

All modules import `settings` from here. No module reads `.env` directly.

---

### `schemas/claim.py` (~55 lines)

Single responsibility: IPC schema for a single agent claim.

- `EvidenceSchema`: `source: str`, `quality_score: float [0,1]`, `citation: str`
- `ClaimPayloadSchema`: all fields + `addressed_claim_ids: List[str]` (mandatory)
- UUID4 auto-generation for `claim_id`

---

### `schemas/round.py` (~45 lines)

Single responsibility: schema for a single debate round.

- `LedgerEntry`: wraps `ClaimPayloadSchema` + `embedding: Optional[List[float]]`
- `RoundSchema`: `round_number`, `pro_claim`, `con_claim`, per-agent responsiveness scores

---

### `schemas/verdict.py` (~45 lines)

Single responsibility: schema for the final judgment.

- `VerdictSchema`: `winner: Literal["PRO","CON"]` (never null), `tiebreaker_used`, full scoring breakdown per agent

---

### `agents/base.py` (~85 lines)

Single responsibility: shared agent state with **permanent V₁ isolation**.

```
BaseAgent(ABC):
    agent_id: str
    stance: Literal["PRO", "CON"]
    v1_embedding: Optional[List[float]] = None   ← NEVER truncated, immutable after set
    ledger: List[LedgerEntry] = []

    set_v1_embedding(embedding) → None
        raises RuntimeError if called twice

    get_windowed_ledger(window: int) → List[LedgerEntry]
        returns ledger[-window:]  ← for LLM context only

    add_to_ledger(entry: LedgerEntry) → None

    @abstractmethod
    generate_claim(round_number, opponent_windowed_ledger) → ClaimPayloadSchema
```

**Key invariant**: `v1_embedding` is not a ledger entry. It is agent state. The windowed ledger returned for LLM prompting never includes V₁.

---

### `agents/pro.py` / `agents/con.py` (~80 lines each)

Single responsibility: LLM call + response parsing for one stance.

```
ProAgent(BaseAgent):
    _system_prompt: str          ← cached, built once at init
    generate_claim(...):
        build prompt from windowed_ledger (compact JSON)
        call Anthropic API (temperature=0, prompt caching on system_prompt)
        parse JSON response → ClaimPayloadSchema
        validate addressed_claim_ids exist in opponent ledger
```

ConAgent is structurally identical with opposite stance and persona.

---

### `engine/ledger.py` (~75 lines)

Single responsibility: ledger append/query with truncation for LLM context.

```
LedgerManager:
    entries: List[LedgerEntry]
    append(entry) → None
    get_window(n: int) → List[LedgerEntry]   ← last n entries for LLM context
    get_all() → List[LedgerEntry]            ← for judge scoring (full history)
    serialize_for_llm(entries) → str         ← compact JSON, not prose
    get_claim_ids() → Set[str]               ← for responsiveness validation
```

---

### `engine/embeddings.py` (~65 lines)

Single responsibility: local, deterministic text embeddings.

```
EmbeddingService (singleton):
    _model: SentenceTransformer("all-MiniLM-L6-v2")

    embed(text: str) → List[float]
    cosine_distance(a, b: List[float]) → float
    cosine_similarity(a, b: List[float]) → float
    weighted_centroid(embeddings, weights) → List[float]
```

Singleton pattern prevents re-loading the model on every call. No network calls.

---

### `evaluation/responsiveness.py` (~60 lines)

Single responsibility: pure Python Responsiveness Score.

```
ResponsivenessCalculator:
    calculate(claim: ClaimPayloadSchema, opponent_ledger: LedgerManager) → float
        valid = set(claim.addressed_claim_ids) & opponent_ledger.get_claim_ids()
        return len(valid) / max(len(opponent_ledger.entries), 1)
```

No LLM. No embeddings. O(n) set intersection only.

---

### `evaluation/semantic_drift.py` (~100 lines)

Single responsibility: detect and quantify semantic drift from V₁.

```
DriftResult(BaseModel):
    v1_distance: float
    centroid_alignment: float
    drift_penalty: float

SemanticDriftEvaluator:
    __init__(embeddings: EmbeddingService, settings: Settings)
    evaluate(agent: BaseAgent, current_embedding: List[float],
             opponent_embeddings: List[List[float]]) → DriftResult
        v1_distance = embeddings.cosine_distance(current_embedding, agent.v1_embedding)
        centroid = embeddings.weighted_centroid(opponent_embeddings, decay_weights)
        centroid_sim = embeddings.cosine_similarity(current_embedding, centroid)
        compute and return penalty
```

Reads `agent.v1_embedding` directly from agent state — never from the ledger window.

---

### `evaluation/judge.py` (~130 lines)

Single responsibility: produce a singular, deterministic `VerdictSchema`.

```
RoundScores(BaseModel):
    evidence_quality: float
    drift_penalty: float
    responsiveness: float

Judge:
    score_round(round: RoundSchema, pro_agent, con_agent) → Tuple[RoundScores, RoundScores]
    evaluate_debate(rounds, pro_agent, con_agent) → VerdictSchema
        aggregate RoundScores → total_score per agent
        if |pro_total - con_total| < TIE_EPSILON:
            return _resolve_tiebreaker(...)
        return VerdictSchema(winner=argmax)

    _resolve_tiebreaker(pro_agg, con_agg, pro_agent, con_agent, debate_id) → VerdictSchema
        Level 1: evidence_quality
        Level 2: v1_distance (lower = better)
        Level 3: responsiveness
        Level 4: random.Random(seed=hash).choice(["PRO","CON"])
```

---

### `engine/pipeline.py` (~145 lines — LINE BUDGET ENFORCED)

Single responsibility: orchestrate one debate run and N benchmark runs.

#### Annotated Line Budget

```
Lines   1– 12  imports (config, agents, engine, evaluation, benchmarks, dataclasses)
Lines  13– 30  DebateResult dataclass definition
Lines  31– 35  run_debate() signature + agent/judge init
Lines  36– 40  timing setup, empty round list
Lines  41–100  for round_num in range(1, max_rounds+1):        [10 rounds × ~6 lines]
                 pro_claim  = pro_agent.generate_claim(...)     [2 lines]
                 con_claim  = con_agent.generate_claim(...)     [2 lines]
                 embed + set V₁ if round_num == 1              [5 lines]
                 responsiveness calc (pro + con)                [4 lines]
                 drift eval (pro + con)                         [4 lines]
                 build RoundSchema, append to rounds list       [4 lines]
                 record round latency                           [1 line]
Lines 101–120  judge.evaluate_debate(rounds, pro, con) → verdict
Lines 121–135  build DebateResult with timing/token/cost data
Lines 136–145  run_benchmarks(n, rounds, topic) → List[DebateResult]
                 loop n times, call run_debate(), collect
                 call reporter.export(results)
                 return results
```

**Safety margin: 5 lines. Absolute maximum: 150.**

---

## ASCII Data Flow

```
main.py  ──────────────────────────────────────────────────────────
  │  (CLI args only)                                               │
  ▼                                                                │
pipeline.run_benchmarks(n=5)                                       │
  │                                                                │
  ├─► for each run: run_debate()                                   │
  │       │                                                        │
  │       ├─► ProAgent.generate_claim(round, windowed_ledger)      │
  │       │         └── Anthropic API  temperature=0              │
  │       │             cached system prompt prefix               │
  │       │                                                        │
  │       ├─► ConAgent.generate_claim(round, windowed_ledger)      │
  │       │         └── Anthropic API  temperature=0              │
  │       │                                                        │
  │       ├─► EmbeddingService.embed()                            │
  │       │         └── round==1: BaseAgent.set_v1_embedding()    │
  │       │             (immutable after this call)               │
  │       │                                                        │
  │       ├─► ResponsivenessCalculator.calculate()  [pure Python] │
  │       │                                                        │
  │       ├─► SemanticDriftEvaluator.evaluate()                   │
  │       │         └── reads agent.v1_embedding directly         │
  │       │             (NOT from ledger window)                  │
  │       │                                                        │
  │       ├─► LedgerManager.append()                              │
  │       │         rounds>3: window truncated for LLM context    │
  │       │         V₁ remains in agent state, untouched          │
  │       │                                                        │
  │       └─► Judge.evaluate_debate()                             │
  │                 └── _resolve_tiebreaker() if needed           │
  │                     [pure Python, no LLM]                     │
  │                     tiebreaker: evidence→contradiction         │
  │                                →responsiveness→prng           │
  │                                                                │
  └─► BenchmarkReporter.export() ──► debate_systems_research.json │
```

---

## Dependency Graph (acyclic — verified)

```
config
  └── (imported by all modules — no reverse deps)

schemas/claim  ←── schemas/round  ←── schemas/verdict
     ↑                  ↑
  agents/base        evaluation/*
     ↑
  agents/pro, agents/con

engine/embeddings  ←── evaluation/semantic_drift
engine/ledger      ←── agents/base, engine/pipeline
evaluation/responsiveness  ←── evaluation/judge
evaluation/semantic_drift  ←── evaluation/judge
evaluation/judge   ←── engine/pipeline
agents/*           ←── engine/pipeline
benchmarks/reporter ←── engine/pipeline
```

**No circular imports.** `config` and `schemas` are pure leaves.

---

## CI/CD: GitHub Actions Automation

GitHub Actions enforces the project's quality gates on every `push` and
`pull_request` to `master` / `main`. The workflow mirrors local development
exactly — `uv` is the single task runner throughout:

```
ubuntu-latest
  ├── actions/checkout@v4
  ├── astral-sh/setup-uv@v5       (install uv)
  ├── uv sync                     (install all deps from uv.lock)
  ├── uv run ruff check .         (zero-error lint gate)
  └── uv run pytest               (all tests must pass)
```

No direct `pip` or `python -m` calls. The workflow file lives at
`.github/workflows/ci.yml` and is the canonical source for what "passing"
means in this project.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `sentence-transformers` (local) | Deterministic; no API dependency; free; no latency variance |
| `temperature=0` on all LLM calls | Eliminates sampling non-determinism entirely |
| V₁ in `BaseAgent` state, not ledger | Survives truncation; never accidentally included in LLM prompt |
| Compact JSON for truncated context | 3–5× token reduction vs. prose history passthrough |
| Seeded PRNG with `debate_id` hash | Coin-flip tiebreaker is reproducible for identical debates |
| `pipeline.py` only orchestrates | All logic is independently testable; `main.py` is a pure shim |
| One module per concern | Files stay under 150 lines without forced truncation |
| `pydantic-settings` for config | `.env` is the single source of truth; no hardcoded hyperparameters |
