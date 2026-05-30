# PRD: Watchdog Circuit Breaker

## 1. Purpose and Failure-Isolation Guarantee

The `Watchdog` is a **circuit-breaker** that sits between `ApiGatekeeper` and the
Anthropic SDK. Its single responsibility is to detect a run of consecutive API failures
and stop issuing further calls until an operator explicitly resets the circuit.

**Failure-isolation guarantee:** once `failure_threshold` consecutive failures are
recorded, every subsequent call to `guard()` is rejected immediately —
**no HTTP request is made** — until `reset()` is called. This prevents a sustained
upstream outage from burning retries, accumulating backoff delays, and inflating costs
across all concurrent benchmark threads.

### Expected inputs and outputs

| Caller | Input | Output (normal path) | Output (circuit open) |
|---|---|---|---|
| `ApiGatekeeper.call()` | `fn=client.messages.create`, `**kwargs` | Return value of `fn(**kwargs)` | `WatchdogTrippedError` raised immediately |
| `ApiGatekeeper.call()` retry loop | same | same | same — bypasses retry logic entirely |

### Limitations and constraints

- The Watchdog tracks **raw failure counts**, not failure rates. A single slow but
  eventually-successful sequence of retries does not trip the circuit because
  `record_success()` decrements the counter.
- The circuit does **not auto-recover** on a timer. Recovery requires an explicit
  `reset()` call (designed to be operator- or test-triggered).
- `failure_threshold` defaults to `3` (hardcoded in `Watchdog.__init__`). Future work:
  source this from `config/rate_limits.json` to satisfy Rule 8.
- Thread-safety is guaranteed via `threading.Lock` on all state mutations, but the
  check-then-act in `guard()` is not atomic with the failure-count read. Under extreme
  concurrency a call may slip through while the circuit trips — this is acceptable
  (at-most-once violation, never infinite).

---

## 2. State Machine

```
              failure_threshold consecutive failures
                         │
    ┌────────────────────▼────────────────────┐
    │                                         │
  CLOSED ─────────────────────────────────→ OPEN
  (tripped=False)                        (tripped=True)
    ▲                                         │
    │                 reset()                 │
    └─────────────────────────────────────────┘
```

### Transitions

| From | Event | To | Side-effect |
|---|---|---|---|
| CLOSED | `record_failure()` and `failures < threshold` | CLOSED | `failures += 1` |
| CLOSED | `record_failure()` and `failures >= threshold` | **OPEN** | `failures += 1`; `_tripped = True`; WARNING logged |
| CLOSED | `record_success()` | CLOSED | `failures = max(0, failures - 1)` |
| OPEN | `guard()` called | OPEN | `WatchdogTrippedError` raised; ERROR logged |
| OPEN | `reset()` | **CLOSED** | `failures = 0`; `_tripped = False` |
| OPEN | `record_success()` | OPEN | `failures` decremented (does **not** auto-close) |

### Edge cases

- **Success after partial failures**: if 2 failures occur (threshold=3) and then a
  success arrives, `failures` drops to 1. The circuit stays closed.
- **reset() on closed circuit**: idempotent — resets counter to 0, no state error.
- **Concurrent trip**: two threads may both reach `record_failure()` simultaneously
  when `failures == threshold - 1`. Both increment under the lock; only one sets
  `_tripped = True` (the lock serializes writes). The result is correct.
- **WatchdogTrippedError inside gatekeeper retry loop**: because `WatchdogTrippedError`
  is not an Anthropic SDK exception, `ApiGatekeeper._is_retryable()` returns `False`,
  so it is re-raised immediately — the retry loop does not consume it.

---

## 3. `guard()` Protocol

```python
def guard(fn: Callable[..., Any], *args, **kwargs) -> Any
```

**Pre-condition:** `fn` is a callable (typically `client.messages.create`).

**Step-by-step execution:**

```
1. Acquire self._lock; read self._tripped; release lock.
2. If tripped:
       log ERROR "Guard rejected: circuit open."
       raise WatchdogTrippedError("Circuit breaker open — too many failures.")
3. Call fn(*args, **kwargs).
4a. If fn returns normally:
       call record_success()        # decrements failure counter under lock
       return result
4b. If fn raises any exception:
       call record_failure()        # increments counter, trips if at threshold
       re-raise the original exception unchanged
```

**Contract guarantees:**
- Exceptions from `fn` are **always re-raised** — the watchdog never swallows them.
- `record_success()` is called **only** on a clean return, never on exception.
- The logged error message in step 2 uses `_logger` from `src.debate.shared.logger`.

---

## 4. Integration with `ApiGatekeeper`

`ApiGatekeeper` owns a `Watchdog` instance created at construction time:

```python
# src/debate/gatekeeper/gatekeeper.py — __init__
self._watchdog = Watchdog()          # failure_threshold defaults to 3
```

Every Anthropic API call is wrapped by the watchdog **inside** the retry loop:

```python
# call() — per-attempt path
return self._watchdog.guard(self._client.messages.create, **kwargs)
```

**Consequence for retry interaction:**

With `max_retries=3` and `failure_threshold=3`:

| Attempt | Outcome | `failures` after | Circuit |
|---|---|---|---|
| 0 | RateLimitError | 1 | CLOSED |
| 1 | RateLimitError | 2 | CLOSED |
| 2 | RateLimitError | 3 = threshold | **OPEN** |
| 3 | `WatchdogTrippedError` (no HTTP call) | 3 | OPEN |

On attempt 3, `_is_retryable(WatchdogTrippedError)` returns `False`, so the error
propagates immediately — **before** `GatekeeperRateLimitError` would normally be raised.
Callers should treat `WatchdogTrippedError` as a signal to halt the debate run and
wait for operator intervention.

**Shared instance across threads:** all agents within one `DebateSDK` session share the
same `ApiGatekeeper` (and therefore the same `Watchdog`). A failure in one benchmark
thread contributes to the shared failure count. This is intentional: if the upstream API
is down, all threads should stop, not compete for a finite retry budget.

---

## 5. Hyperparameters

| Parameter | Source | Current value | Governs |
|---|---|---|---|
| `failure_threshold` | `Watchdog.__init__` default (⚠ hardcoded) | `3` | Consecutive failures before OPEN |

> **Rule 8 violation (tracked):** `failure_threshold=3` is a hardcoded default in
> `watchdog.py`. Phase 14-D or a follow-up task should add `"failure_threshold": 3` to
> `config/rate_limits.json` and load it via `GatekeeperConfig`, then pass it to
> `Watchdog(failure_threshold=config.failure_threshold)` in `gatekeeper.py`.

---

## 6. Module Layout

```
src/debate/gatekeeper/
├── __init__.py       # exports: Watchdog, WatchdogTrippedError
└── watchdog.py       # Watchdog class (≤ 150 lines)
```

---

## 7. Test Contract

All behaviour above is covered by **`tests/test_watchdog.py`** (7 tests):

| Test | Verifies |
|---|---|
| `test_watchdog_not_tripped_initially` | Fresh instance is CLOSED |
| `test_watchdog_trips_exactly_at_threshold` | Trips on the Nth failure, not the (N-1)th |
| `test_watchdog_guard_raises_when_circuit_open` | `guard()` raises `WatchdogTrippedError` when OPEN |
| `test_watchdog_guard_records_success_and_decrements` | Success decrements `_failures` |
| `test_watchdog_guard_propagates_exception_and_records_failure` | Exceptions from `fn` are re-raised; failure is recorded |
| `test_watchdog_reset_clears_all_state` | `reset()` → CLOSED, `_failures == 0` |
| `test_watchdog_success_decrements_failure_count` | `record_success()` floor-clamps at 0 |

Run with:

```bash
uv run pytest tests/test_watchdog.py -v
```
