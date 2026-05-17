# PRD: Production-Grade Logging System

**Version:** 1.0
**Author:** Avi Ayeli
**Feature:** Structured FIFO-Rotating Logger
**Classification:** University Thesis — Research Grade
**Date:** 2026-05-17

---

## 1. Problem Statement

All runtime events (round progress, LLM calls, verdict, benchmark export) are currently emitted
via `print()`. This has three research-grade deficiencies:

1. **No persistence** — console output is lost between runs; post-hoc analysis of N=5 benchmark
   runs is impossible without redirecting stdout manually.
2. **No severity levels** — errors, warnings, and informational events are indistinguishable.
3. **Unbounded growth** — a naive single log file accumulates indefinitely across repeated runs,
   consuming disk space without any rotation policy.

---

## 2. Goals

| Goal | Acceptance Criterion |
|---|---|
| Replace all `print()` calls | `grep -r "print(" src/ main.py` returns 0 matches |
| Structured, levelled output | Log lines include timestamp, level, module name, message |
| FIFO file rotation | At most `max_files` log files exist; oldest deleted when limit exceeded |
| Line-count rotation | New file opened when current file reaches `max_lines` lines |
| Zero hardcoded values | All parameters read exclusively from `config/logging_config.json` |
| 150-line file limit | No Python file in `src/` or `tests/` exceeds 150 lines |

---

## 3. Logger Architecture

### 3.1 Module Layout

```
src/debate/logging/
    __init__.py          # re-exports get_logger()
    logger.py            # DebateLogger (OOP), FifoRotatingHandler
config/
    logging_config.json  # all tunable parameters (authoritative source)
logs/                    # runtime output directory (git-ignored)
tests/
    test_logger.py       # TDD test suite (written before implementation)
```

### 3.2 DebateLogger Class

`DebateLogger` is a thin OOP wrapper around Python's built-in `logging` module. It:

- Accepts a `name` parameter (e.g. `"pipeline"`, `"pro_agent"`, `"con_agent"`).
- Loads all configuration from `config/logging_config.json` on first instantiation (singleton
  config object shared across all loggers in the process).
- Attaches a `FifoRotatingHandler` (custom `logging.Handler` subclass) and a `StreamHandler`
  for console output at WARNING level and above.
- Exposes `.debug()`, `.info()`, `.warning()`, `.error()` — delegating to the internal
  `logging.Logger`.

```
DebateLogger
├── __init__(name: str)
├── debug(msg: str, **kwargs) -> None
├── info(msg: str, **kwargs) -> None
├── warning(msg: str, **kwargs) -> None
└── error(msg: str, **kwargs) -> None

FifoRotatingHandler(logging.Handler)
├── __init__(config: LoggingConfig)
├── emit(record: logging.LogRecord) -> None
├── _rotate_if_needed() -> None       # opens new file when line limit hit
└── _enforce_fifo() -> None           # deletes oldest file when file count > max_files
```

### 3.3 Factory Function

A module-level `get_logger(name: str) -> DebateLogger` factory is exported from
`src/debate/logging/__init__.py`. Every module that needs logging calls this function — no
direct instantiation of `DebateLogger` outside the factory.

---

## 4. FIFO Log Rotation Strategy

### 4.1 Line-Count Rotation

- The handler tracks the number of lines written to the **current** log file.
- When `lines_written >= max_lines` (default: **500**), the current file handle is closed and
  a new file is opened with a fresh timestamp-based name.
- File naming convention: `debate_YYYYMMDD_HHMMSS_NNN.log` where `NNN` is a zero-padded
  sequence counter that resets to `000` each day (prevents collisions in rapid tests).

### 4.2 FIFO File-Count Enforcement

- After opening a new file, the handler lists all `*.log` files in `log_dir` sorted by
  creation time (ascending = oldest first).
- While `len(log_files) > max_files` (default: **20**), delete the oldest file (FIFO eviction).
- This guarantees the log directory never exceeds `max_files × max_lines` lines of history
  (~10,000 lines by default).

### 4.3 Rotation Invariants

| Invariant | Description |
|---|---|
| Atomicity | File close and new-file open happen within a single `emit()` call; no log line is lost |
| Idempotency | Calling `_enforce_fifo()` with fewer than `max_files` files is a no-op |
| Thread safety | `emit()` is protected by a `threading.Lock`; safe for multi-threaded benchmarks |
| Determinism | Rotation triggers on line count, not wall-clock time — deterministic for identical workloads |

---

## 5. Configuration Strategy

### 5.1 Authoritative Source

All logging parameters live exclusively in `config/logging_config.json`. No Python file may
contain numeric literals or string constants for any of these values.

### 5.2 Config Schema

```json
{
  "log_dir":    "logs/",
  "max_files":  20,
  "max_lines":  500,
  "log_level":  "INFO",
  "log_format": "%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s",
  "date_format": "%Y-%m-%dT%H:%M:%S"
}
```

| Field | Type | Description |
|---|---|---|
| `log_dir` | `str` | Directory for log files (created if absent) |
| `max_files` | `int` | Maximum number of log files before FIFO eviction |
| `max_lines` | `int` | Maximum lines per log file before rotation |
| `log_level` | `str` | Root log level (`"DEBUG"` \| `"INFO"` \| `"WARNING"` \| `"ERROR"`) |
| `log_format` | `str` | `logging.Formatter` format string |
| `date_format` | `str` | `logging.Formatter` date format string |

### 5.3 Config Loading

A `LoggingConfig` dataclass is populated at import time from `logging_config.json` via
`json.load()`. The path to the config file is resolved relative to the project root using
`pathlib.Path(__file__).parents[N]` — no `os.getcwd()` calls that depend on invocation
directory.

---

## 6. Integration Points

| Module | Logger Name | Key Events Logged |
|---|---|---|
| `pipeline.py` | `"pipeline"` | Debate start/end, round number, verdict, benchmark totals |
| `pro.py` | `"pro_agent"` | Claim generated (round, token usage, cache hit) |
| `con.py` | `"con_agent"` | Claim generated (round, token usage, cache hit) |
| `main.py` | `"main"` | CLI args, benchmark export path |

Log level guidelines:

| Level | Use |
|---|---|
| `DEBUG` | Per-round claim text, raw LLM response |
| `INFO` | Round start/end, verdict, file export path |
| `WARNING` | JSON parse fallback triggered, cache miss |
| `ERROR` | LLM call failure, file I/O error |

---

## 7. Non-Functional Requirements

| Requirement | Rule |
|---|---|
| File size limit | `src/debate/logging/logger.py` must be < 150 lines |
| Linter | `uv run ruff check .` exits 0 after implementation |
| Test coverage | `uv run pytest --cov` reports ≥ 85% overall |
| No hardcoded values | `grep -n "500\|20\|logs/" src/debate/logging/logger.py` must return 0 matches |
| git-ignored logs | `logs/` directory must be listed in `.gitignore` |
