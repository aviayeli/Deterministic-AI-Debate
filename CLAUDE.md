# CLAUDE.md — 12-Rule Agentic Behavioral Contract

This file governs how Claude (and any AI assistant) must behave when working in this repository. All 12 rules below are enforced during every session. Non-compliance invalidates the architectural guarantees described in `docs/PRD.md`.

---

## Part I: Karpathy's 4 Core Rules

### 1. Think Before Coding
Before writing or modifying any code, state the problem, identify the affected modules, and verify there is a failing test that justifies the change. Never start an implementation without first understanding why it is needed.

### 2. Simplicity First
Prefer the simplest solution that satisfies the failing test. Do not introduce abstractions, generics, or helper utilities that are not immediately required. Three similar lines are better than a premature abstraction.

### 3. Surgical Changes
Edits must be minimal and targeted. Do not refactor surrounding code while fixing a bug. Do not rename symbols, reorganize imports, or clean up unrelated logic in the same commit as a functional change.

### 4. Goal-Driven Execution
Every action must trace back to a specific task in `docs/TODO.md` or an explicit user instruction. Do not add features, logging, or error handling for hypothetical future scenarios that are not part of the current goal.

---

## Part II: Project-Specific Constraints (8 Rules)

### 5. All API Calls Must Route Through `ApiGatekeeper`
No agent or module may call `client.messages.create()` directly. Every Anthropic API call must go through `gatekeeper.call()` as implemented in `src/debate/agents/base.py`. This enforces rate limiting, retry with exponential backoff, and circuit-breaker protection.

**Violation pattern to avoid:**
```python
# FORBIDDEN — direct SDK call
response = client.messages.create(model=..., messages=...)
```

**Required pattern:**
```python
# CORRECT — routed through gatekeeper
msg = gatekeeper.call(model=..., messages=...)
```

### 6. Hard 150-Line Limit Per File
No Python source file in `src/` may exceed 150 lines. If an implementation requires more, it must be split into focused submodules. Verify with `wc -l <file>` before committing. This limit enforces single-responsibility and keeps the codebase auditable.

### 7. Strict TDD-First Mandate
No implementation code may be written before a failing test exists for it. The workflow is always:

1. Write a test in `tests/` that fails (`pytest` exits non-zero).
2. Write the minimum implementation to make the test pass.
3. Refactor only under green.

Committing implementation code without a corresponding test is a contract violation.

### 8. No Hardcoded Hyperparameters in Python Files
All tuneable values (token budgets, round counts, cost coefficients, rate limits, model IDs) must be sourced from `.env` via `src/debate/config.py` (pydantic-settings `Settings` class) or from JSON config files under `config/`. Embedding a magic number directly in a `.py` file is forbidden.

**Violation pattern to avoid:**
```python
# FORBIDDEN — hardcoded hyperparameter
MAX_ROUNDS = 10
COST_PER_TOKEN = 3e-6
```

**Required pattern:**
```python
# CORRECT — loaded from settings or config/
from debate.config import settings
max_rounds = settings.MAX_ROUNDS
```

### 9. LEDGER_WINDOW Context Truncation Protocol
Agents must never pass full conversation history to the LLM. Context sent per round is strictly bounded to the last `settings.LEDGER_WINDOW` entries from the opponent's ledger, retrieved via `agent.get_windowed_ledger(settings.LEDGER_WINDOW)` as implemented in `src/debate/engine/pipeline.py`. This prevents O(n²) token growth across rounds and keeps costs deterministic. Do not increase or bypass this window without updating `docs/PRD.md` and adding a sensitivity test.

### 10. Explicit Failure Over Silent Failure
Every error path must raise a named exception or return a typed error value. Functions must never swallow exceptions or use `None` as a silent sentinel for failure.

**Violation patterns to avoid:**
```python
# FORBIDDEN — bare swallow
try:
    result = risky_call()
except Exception:
    pass  # silent failure

# FORBIDDEN — None-as-failure
def get_data() -> dict | None:
    try:
        return fetch()
    except Exception:
        return None  # caller cannot distinguish "not found" from "error"
```

**Required pattern:**
```python
# CORRECT — named exception propagates to the caller
try:
    result = risky_call()
except NetworkError as exc:
    raise GatekeeperError("upstream unavailable") from exc
```

Enforcement: `ruff` rule `BLE001` (blind exception catch) must report 0 violations. All `except Exception` blocks in `src/` must either re-raise or raise a named domain exception.

### 11. Checkpoint Summaries for Long-Running Tasks
Any automated operation spanning more than 3 sequential steps must emit a one-line structured progress checkpoint via `logger.info()` after each logical sub-step. This ensures that long benchmark runs and sensitivity sweeps remain observable without requiring interactive inspection.

**Required checkpoint format:**
```python
logger.info("[PHASE %d/%d] %s — done", current, total, description)
```

This rule applies to: `src/debate/engine/pipeline.py` (each debate round), `run_benchmarks()` (each completed run), and `src/debate/sensitivity_runner.py` (each config combination). Suppressing or removing checkpoints to reduce log volume is a contract violation — use log-level filtering instead.

### 12. Hard Token Budgets on Every Agent Call
Every call routed through `ApiGatekeeper` must supply an explicit `max_tokens` ceiling. Omitting `max_tokens` and relying on Anthropic API defaults is forbidden: defaults change across model versions and can silently inflate costs.

**Violation pattern to avoid:**
```python
# FORBIDDEN — relies on API default
gatekeeper.call(model=settings.MODEL, messages=messages)
```

**Required pattern:**
```python
# CORRECT — explicit ceiling from settings
gatekeeper.call(
    model=settings.MODEL,
    max_tokens=settings.MAX_TOKENS_PER_CALL,
    messages=messages,
)
```

Pre-commit enforcement:
```bash
grep -rn "gatekeeper.call" src/ | grep -v "max_tokens" && echo "FAIL: missing max_tokens" || echo "PASS"
```

---

## Enforcement

Before any commit:
```bash
uv run ruff check .          # must exit 0 (includes BLE001 for Rule 10)
uv run pytest --cov=src      # must exit 0, coverage must not decrease
wc -l src/debate/**/*.py     # no file may exceed 150 lines (Rule 6)

# Rule 12: every gatekeeper.call() must declare max_tokens
grep -rn "gatekeeper.call" src/ | grep -v "max_tokens" && echo "FAIL" || echo "PASS"

# Verify 12 rules present
grep -c "^### [0-9]" CLAUDE.md  # must output 12
```

These gates are also enforced by GitHub Actions CI on every push.
