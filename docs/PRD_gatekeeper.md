# PRD: Centralized API Gatekeeper & Watchdog

## 1. Problem Statement

`ProAgent` and `ConAgent` currently call `anthropic.Anthropic.messages.create()` directly and
independently. There is no rate limiting, no timeout enforcement, and no retry logic. A single
transient 429 or network hiccup aborts an entire debate run. Under concurrent benchmark loads
(N=5 runs), independent agents can collectively burst past Anthropic's RPM ceiling.

---

## 2. Goals

| # | Goal |
|---|---|
| G1 | All LLM calls pass through a single `ApiGatekeeper` — no agent may call Anthropic directly |
| G2 | Enforce a configurable requests-per-minute ceiling across all agents |
| G3 | Automatically retry transient failures with exponential backoff |
| G4 | Abort and surface any request that exceeds a configurable wall-clock timeout |
| G5 | Zero hardcoded values — all limits loaded from `config/rate_limits.json` |

---

## 3. Rate Limiting & Queueing Strategy

### 3.1 Algorithm: Token Bucket

A **token bucket** is used because it handles bursty traffic gracefully while enforcing
a hard ceiling over any sliding 60-second window.

- Bucket capacity = `requests_per_minute` tokens
- Refill rate = 1 token per `60 / requests_per_minute` seconds (continuous)
- Each `gatekeeper.call()` atomically acquires one token before dispatching

**Why token bucket over sliding window?** A sliding window requires storing per-request
timestamps; a token bucket needs only a float and a lock — simpler, thread-safe, and
sufficient for our sequential-within-debate, concurrent-across-benchmarks access pattern.

### 3.2 FIFO Queue (Phase 14-A)

Instead of blocking the calling thread with a busy-wait sleep, `ApiGatekeeper` uses a
`queue.Queue`-based drain loop to enforce **strict FIFO ordering** under concurrent load:

- At construction, a daemon thread (`_drain_loop`) is started. It blocks on
  `self._queue.get()` waiting for work.
- Each `call()` invocation (and each retry attempt within it) creates a
  `threading.Event`, puts it into `self._queue`, then blocks on `event.wait()`.
- The drain loop dequeues events **in arrival order** (FIFO), calls `_acquire_token()`
  to claim a token (sleeping if the bucket is empty), then sets the event to release
  the waiting caller.
- `queue_maxsize` (from `config/rate_limits.json`) bounds the internal queue. Setting
  `0` makes the queue unbounded.

**Ordering guarantee:** `queue.Queue` is FIFO by contract; the first caller to
`queue.put()` will have its event serviced before any later caller's event.

**Backpressure:** callers block on `event.wait()` rather than spinning or failing. The
queue provides natural backpressure — if the drain loop falls behind, callers queue up
and wait rather than piling retries on top of each other.

**Config field added:** `config/rate_limits.json` now includes `"queue_maxsize": 100`.

See `tests/test_gatekeeper_queue.py` for the full contract (7 tests).

---

## 4. Watchdog / Timeout Handling

### 4.1 Per-Request Timeout

Every `gatekeeper.call()` dispatches the Anthropic SDK call in the **current thread**
using `httpx` timeouts (the Anthropic SDK accepts a `timeout` parameter). If the
request exceeds `timeout_seconds`, the SDK raises `anthropic.APITimeoutError`.

The gatekeeper catches `APITimeoutError` and treats it identically to a transient
failure — it is eligible for retry (see §5).

### 4.2 Watchdog Contract

- Timeout is enforced at the HTTP layer by the SDK — no `threading.Timer` overhead.
- `timeout_seconds` is loaded from `config/rate_limits.json`; it applies to every call.
- If all retries are exhausted on a timeout, `GatekeeperTimeoutError` is re-raised,
  propagating to the pipeline and aborting that debate run cleanly.
- Every API call is additionally wrapped by `self._watchdog.guard()`. If the watchdog
  trips (≥ 3 consecutive failures), it raises `WatchdogTrippedError` before the SDK is
  called — see `docs/PRD_watchdog.md` for the full circuit-breaker contract.

---

## 5. Retry Logic for Transient Failures

### 5.1 Retryable Conditions

| Condition | Anthropic Exception | Retryable |
|---|---|---|
| Rate limited (429) | `RateLimitError` | Yes |
| Server overloaded (529) | `InternalServerError` (status 529) | Yes |
| Network timeout | `APITimeoutError` | Yes |
| Network connection error | `APIConnectionError` | Yes |
| Bad request (400) | `BadRequestError` | No |
| Auth failure (401) | `AuthenticationError` | No |
| Not found (404) | `NotFoundError` | No |

### 5.2 Backoff Formula

```
wait = backoff_factor * (2 ** attempt) + jitter
```

- `attempt` is 0-indexed (first retry = attempt 0)
- `jitter` is `random.uniform(0, 0.5)` — prevents thundering herd under concurrent benchmarks
- `backoff_factor` is loaded from config (e.g. `1.0` → waits of 1s, 2s, 4s …)
- Maximum attempts = `max_retries + 1` (initial call + retries)

### 5.3 Failure Escalation

If all retries are exhausted:
- `GatekeeperRateLimitError` is raised for 429 exhaustion
- `GatekeeperTimeoutError` is raised for timeout exhaustion
- `GatekeeperError` (base) is raised for all other retryable failures

---

## 6. Module Layout

```
src/debate/gatekeeper/
├── __init__.py          # exports: ApiGatekeeper, GatekeeperError
├── config.py            # GatekeeperConfig dataclass (loads rate_limits.json)
└── gatekeeper.py        # ApiGatekeeper class (≤ 150 lines)
```

`ApiGatekeeper` is instantiated once per debate run and injected into both agents via
their constructors — agents receive it as a dependency, not a global.

---

## 7. Interface Contract

```python
class ApiGatekeeper:
    def call(self, **kwargs) -> anthropic.types.Message:
        """
        Acquire rate-limit token, then dispatch to Anthropic with timeout and retry.
        kwargs are forwarded verbatim to client.messages.create().
        """
```

Agents replace `self._client.messages.create(...)` with `self._gatekeeper.call(...)`.
No other agent code changes are required.

---

## 8. Out of Scope

- Persistent request logging to disk (handled by `DebateLogger`)
- Adaptive rate limiting based on response headers (future work)

> **Note:** The circuit-breaker pattern is **in scope** and implemented via `Watchdog`
> (see `docs/PRD_watchdog.md`). It is not repeated here to avoid duplication.
