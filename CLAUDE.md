# CLAUDE.md — Behavioral Contract for AI-Assisted Development

This file governs how Claude (and any AI assistant) must behave when working in this repository. All rules below are enforced during every session. Non-compliance invalidates the architectural guarantees described in `docs/PRD.md`.

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

## Part II: Project-Specific Constraints

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

---

## Enforcement

Before any commit:
```bash
uv run ruff check .          # must exit 0
uv run pytest --cov=src      # must exit 0, coverage must not decrease
wc -l src/debate/**/*.py     # no file may exceed 150 lines
```

These gates are also enforced by GitHub Actions CI on every push.
