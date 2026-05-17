# PRD: Hooks & Plugin Architecture + Official Package Structure

**Status**: Approved for implementation  
**Phase**: 7 (Hooks), 8 (Packaging), 9 (Compliance)  
**Author**: Avi Ayeli  
**Date**: 2026-05-17

---

## 1. Motivation

The system is now feature-complete as a research prototype. Elevating it to a
production-ready open-source Python package requires three orthogonal upgrades:

1. **Extensibility** — external developers must be able to hook into the debate
   lifecycle without forking the core.
2. **Packaging correctness** — the source tree must conform to Python packaging
   standards (PEP 517/518) so `pip install deterministic-ai-debate` works out
   of the box and all submodules are importable without `src.` prefixes.
3. **Quality-standard compliance** — ISO/IEC 25010 characteristics and
   Nielsen's Heuristics must be documented and demonstrated.

---

## 2. Phase 7 — Hooks & Plugin Architecture

### 2.1 Design Goals

| Goal | Rationale |
|---|---|
| Zero coupling to core | Plugins must not require access to internal modules |
| Thread-safe | Hooks fire from within `ThreadPoolExecutor` workers |
| Synchronous-only | No async complexity; hooks are short-lived side-effects |
| Typed payloads | Dataclass events give plugins auto-complete and static analysis |
| No performance tax | Firing an empty event list must cost < 1 µs |

### 2.2 New Module: `src/debate/events/`

```
src/debate/events/
├── __init__.py     # re-exports EventBus + all event types
├── bus.py          # EventBus class (≤ 60 lines)
└── types.py        # typed event dataclasses (≤ 80 lines)
```

#### `src/debate/events/types.py`

Six event dataclasses covering the full debate lifecycle:

```python
@dataclass
class DebateStartEvent:
    topic: str
    max_rounds: int

@dataclass
class RoundStartEvent:
    round_number: int
    max_rounds: int

@dataclass
class AgentReplyEvent:
    agent_id: str        # "PRO" or "CON"
    round_number: int
    claim: ClaimPayloadSchema

@dataclass
class RoundEndEvent:
    round_number: int
    round_schema: RoundSchema
    latency: float

@dataclass
class BeforeEvaluationEvent:
    rounds: list[RoundSchema]

@dataclass
class DebateEndEvent:
    result: DebateResult
```

#### `src/debate/events/bus.py`

```python
import threading
from typing import Any, Callable

class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        """Register a handler for a named lifecycle event."""
        with self._lock:
            self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: Any) -> None:
        """Fire all handlers registered for event (no-op if none)."""
        for handler in self._handlers.get(event, []):
            handler(payload)
```

Key invariants:
- `emit()` acquires **no lock** (read-only after setup) — safe for hot paths.
- `on()` acquires the lock — registration is expected before debate start.
- Handlers are called in registration order, synchronously.
- Exceptions in handlers propagate to the caller (no swallowing).

### 2.3 Modifications to Existing Files

#### `src/debate/engine/pipeline.py`

`run_debate()` gains an optional `bus: EventBus | None = None` parameter:

```python
def run_debate(
    pro_agent: BaseAgent,
    con_agent: BaseAgent,
    max_rounds: int = 10,
    bus: EventBus | None = None,
) -> DebateResult:
    _bus = bus or EventBus()
    _bus.emit("on_debate_start", DebateStartEvent(topic=..., max_rounds=max_rounds))

    for rn in range(1, max_rounds + 1):
        _bus.emit("on_round_start", RoundStartEvent(rn, max_rounds))
        # ... existing round logic ...
        _bus.emit("on_agent_reply", AgentReplyEvent("PRO", rn, pro_claim))
        _bus.emit("on_agent_reply", AgentReplyEvent("CON", rn, con_claim))
        _bus.emit("on_round_end", RoundEndEvent(rn, round_schema, latency))

    _bus.emit("before_evaluation", BeforeEvaluationEvent(rounds))
    # ... verdict logic ...
    _bus.emit("on_debate_end", DebateEndEvent(result))
    return result
```

Default (`bus=None`) creates a private throwaway bus — zero overhead when
hooks are not used. The existing `run_benchmarks()` passes its own shared bus
so plugins registered on `DebateSDK` fire for every benchmark run.

#### `src/debate/sdk.py`

```python
from .events.bus import EventBus

class DebateSDK:
    def __init__(self, topic: str | None = None) -> None:
        ...
        self._bus = EventBus()

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        """Register a plugin hook for a debate lifecycle event."""
        self._bus.on(event, handler)

    def run_single(self, max_rounds: int = 10) -> DebateResult:
        ...
        return run_debate(pro, con, max_rounds, bus=self._bus)
```

### 2.4 Supported Lifecycle Events

| Event name | Payload type | Fires when |
|---|---|---|
| `on_debate_start` | `DebateStartEvent` | Before round 1 |
| `on_round_start` | `RoundStartEvent` | Before each round's LLM calls |
| `on_agent_reply` | `AgentReplyEvent` | After each agent claim (×2/round) |
| `on_round_end` | `RoundEndEvent` | After both claims and ledger update |
| `before_evaluation` | `BeforeEvaluationEvent` | Before Judge runs |
| `on_debate_end` | `DebateEndEvent` | After verdict is produced |

### 2.5 Plugin Example

```python
from debate import DebateSDK

sdk = DebateSDK()

def progress_hook(event):
    print(f"  Round {event.round_number}/{event.max_rounds} starting…")

sdk.on("on_round_start", progress_hook)

result = sdk.run_single(max_rounds=5)
```

External packages can ship plugins as plain Python functions or classes with
a `__call__` method — no special base class or registration decorator needed.

### 2.6 Test Surface (`tests/test_events.py`)

- `EventBus.emit()` with no handlers is a no-op (no exception)
- A registered handler is called exactly once per `emit()`
- Multiple handlers for the same event are all called, in order
- Handler exceptions propagate out of `emit()`
- `on()` is thread-safe: 20 concurrent registrations produce no lost handlers
- `run_debate()` with a mock bus fires all 6 event types in correct order
- `DebateSDK.on()` delegates to the internal `EventBus`
- Plugin registered after `DebateSDK()` but before `run_single()` fires correctly

---

## 3. Phase 8 — Official Python Package Structure

### 3.1 Relative Imports

All internal `src.debate.*` absolute imports must become relative. This is
required for the package to work after installation via `pip install`.

**Rule**: every file within `src/debate/` must use `from .module import X`
or `from ..subpkg.module import X`. The only allowed absolute imports are
third-party packages (`anthropic`, `pydantic`, etc.).

**Audit target** — files with `from src.debate.` that must be migrated:

| File | Current pattern | New pattern |
|---|---|---|
| `agents/base.py` | `from src.debate.schemas.*` | `from ..schemas.*` |
| `agents/pro.py` | `from src.debate.*` | `from ..*` |
| `agents/con.py` | `from src.debate.*` | `from ..*` |
| `engine/pipeline.py` | `from src.debate.*` | `from ..*` |
| `engine/ledger.py` | `from src.debate.*` | `from ..*` |
| `engine/embeddings.py` | `from src.debate.*` | `from ..*` |
| `evaluation/judge.py` | `from src.debate.*` | `from ..*` |
| `evaluation/responsiveness.py` | `from src.debate.*` | `from ..*` |
| `evaluation/semantic_drift.py` | `from src.debate.*` | `from ..*` |
| `gatekeeper/gatekeeper.py` | `from src.debate.*` | `from ..*` |
| `benchmarks/reporter.py` | `from src.debate.*` | `from ..*` |
| `cli/menu.py` | `from src.debate.*` | `from ..*` |
| `cli/handlers.py` | `from src.debate.*` | `from ..*` |
| `sdk.py` | `from src.debate.*` | `from .*` |
| `analysis.py` | `from src.debate.*` | `from .*` |

`main.py` remains at the project root and uses absolute `from debate.*` imports
(it is an entry-point script, not part of the installable package).

### 3.2 `__all__` Definitions

Every `__init__.py` must define `__all__` to control the public API surface.

| Module | `__all__` contents |
|---|---|
| `debate` | `["DebateSDK"]` |
| `debate.agents` | `["BaseAgent", "ProAgent", "ConAgent"]` |
| `debate.engine` | `["DebateResult", "run_debate", "run_benchmarks"]` |
| `debate.evaluation` | `["Judge", "ResponsivenessCalculator", "SemanticDriftEvaluator", "DriftResult"]` |
| `debate.schemas` | `["ClaimPayloadSchema", "EvidenceSchema", "LedgerEntry", "RoundSchema", "VerdictSchema"]` |
| `debate.benchmarks` | `["BenchmarkReporter"]` |
| `debate.cli` | `["run_loop"]` |
| `debate.events` | `["EventBus", "DebateStartEvent", "RoundStartEvent", "AgentReplyEvent", "RoundEndEvent", "BeforeEvaluationEvent", "DebateEndEvent"]` |
| `debate.logging` | `["DebateLogger", "get_logger"]` (already done) |
| `debate.gatekeeper` | `["ApiGatekeeper", "GatekeeperError", "GatekeeperRateLimitError", "GatekeeperTimeoutError"]` (already done) |

### 3.3 `pyproject.toml` Entry Point

```toml
[project.scripts]
debate = "debate.cli.entry:main"
```

A thin `src/debate/cli/entry.py` (≤ 20 lines) replicates the argparse logic
from `main.py` so the package exposes a `debate` CLI command post-install.
`main.py` is retained for uv-run compatibility but delegates to `entry.main()`.

### 3.4 `pyproject.toml` Package Discovery

```toml
[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"
```

This ensures `pip install .` installs the `debate` package (not `src.debate`).

---

## 4. Phase 9 — ISO/IEC 25010 & Nielsen's Heuristics Compliance

### 4.1 Nielsen's Heuristic 1 — Visibility of System Status

**Problem**: `run_benchmarks(n=5)` is silent for 3–5 minutes in a terminal.
Users have no feedback that the process is alive.

**Solution**: integrate `rich.progress` into `run_benchmarks()` and the
interactive CLI benchmark handler.

```python
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress,
    SpinnerColumn, TaskProgressColumn, TimeElapsedColumn,
)

with Progress(
    SpinnerColumn(),
    "[progress.description]{task.description}",
    BarColumn(),
    MofNCompleteColumn(),
    TaskProgressColumn(),
    TimeElapsedColumn(),
) as progress:
    task = progress.add_task(f"Benchmarking ({n} runs)…", total=n)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_single) for _ in range(n)]
        results = []
        for f in as_completed(futures):
            results.append(f.result())
            progress.advance(task)
```

`rich` is a zero-config dependency (MIT license, < 1 MB).

### 4.2 README Section: ISO/IEC 25010 Compliance

A new `## Quality Standard Compliance (ISO/IEC 25010)` section in `README.md`
must cover the eight product quality characteristics:

| Characteristic | Implementation Evidence |
|---|---|
| **Functional Suitability** | All 125 tests green; end-to-end pipeline from claim generation to JSON export with zero manual steps |
| **Performance Efficiency** | `ThreadPoolExecutor` for parallel benchmark runs; ledger window bounds tokens to `O(LEDGER_WINDOW × claim_length)`; Anthropic prompt caching reduces repeated system-prompt tokens |
| **Compatibility** | `pyproject.toml` / PEP 517; `uv` lockfile pins all dependencies; Python ≥ 3.12 declared; no OS-specific syscalls |
| **Usability** | Interactive CLI menu; `rich` progress bars for long-running benchmarks (Nielsen Heuristic 1: Visibility of System Status); all hyperparameters documented in `.env.example` |
| **Reliability** | `temperature=0` on all LLM calls; immutable V₁ anchor enforced at the object level (`RuntimeError` on second write); 4-level deterministic tiebreaker — every debate produces the same verdict given the same inputs |
| **Security** | `ANTHROPIC_API_KEY` loaded exclusively from `.env` (never hardcoded); `.gitignore` blocks `.env` and `logs/` from version control |
| **Maintainability** | Hard 150-line file limit enforced at CI; TDD (tests precede implementation per phase); `ruff` linter with zero-error gate; modular subpackage structure with `__all__`-gated public surfaces |
| **Portability** | `uv sync` reproduces the exact environment on any POSIX or Windows system; no compiled extensions; `sentence-transformers` model cached locally |

---

## 5. Dependency Additions

| Package | Version | Reason |
|---|---|---|
| `rich` | `>=13.0.0` | Progress bars (Nielsen Heuristic 1); already used by many Python CLIs |

No other new runtime dependencies. `rich` is MIT-licensed and has zero
mandatory sub-dependencies not already present via `anthropic`.

---

## 6. File Budget (150-line constraint)

| New / Modified File | Estimated Lines | Status |
|---|---|---|
| `src/debate/events/types.py` | ~70 | New |
| `src/debate/events/bus.py` | ~55 | New |
| `src/debate/events/__init__.py` | ~15 | New |
| `src/debate/cli/entry.py` | ~20 | New |
| `src/debate/engine/pipeline.py` | ~125 | Modified (+15 for bus calls) |
| `src/debate/sdk.py` | ~65 | Modified (+10 for `on()` + bus) |
| `tests/test_events.py` | ~100 | New |
| `README.md` | +40 lines | Modified (ISO section) |

All existing files remain under 150 lines after modification.

---

## 7. Implementation Order

```
Phase 7 → Phase 8 → Phase 9
```

Phase 8 (relative imports) touches the most files and risks regressions.
Run the full test suite after each file migrated. Phase 7 must complete
first because `pipeline.py`'s signature change is a prerequisite for both
the events tests and the packaging refactor.
