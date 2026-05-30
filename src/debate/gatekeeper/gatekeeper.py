"""FIFO-queue-backed API Gatekeeper with token-bucket rate limiting, retry, and circuit-breaker protection."""
import queue
import random
import threading
import time
from typing import Any

import anthropic

from ..shared.logger import get_logger
from .config import GatekeeperConfig
from .watchdog import Watchdog

_logger = get_logger("gatekeeper")


class GatekeeperError(Exception):
    """Base exception for all ApiGatekeeper failures."""


class GatekeeperTimeoutError(GatekeeperError):
    """Raised when all retry attempts are exhausted due to API timeout."""


class GatekeeperRateLimitError(GatekeeperError):
    """Raised when all retry attempts are exhausted due to upstream rate limiting (HTTP 429)."""


class ApiGatekeeper:
    """Rate-limiting proxy for Anthropic API calls.

    Enforces a configurable requests-per-minute ceiling via a token-bucket
    algorithm, serialises concurrent callers through a FIFO queue, retries
    transient failures with exponential backoff, and trips a Watchdog
    circuit-breaker after repeated consecutive failures.
    """
    def __init__(self, client: anthropic.Anthropic, config: GatekeeperConfig) -> None:
        self._client = client
        self._config = config
        self._lock = threading.Lock()
        self._tokens: float = float(config.requests_per_minute)
        self._last_refill: float = time.monotonic()
        self._refill_interval: float = 60.0 / config.requests_per_minute
        self._watchdog = Watchdog()
        self._queue: queue.Queue[threading.Event] = queue.Queue(maxsize=config.queue_maxsize)
        threading.Thread(target=self._drain_loop, daemon=True).start()

    def _acquire_token(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    float(self._config.requests_per_minute),
                    self._tokens + elapsed / self._refill_interval,
                )
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                sleep_time = (1.0 - self._tokens) * self._refill_interval
            time.sleep(sleep_time)

    def _drain_loop(self) -> None:
        while True:
            event = self._queue.get()
            self._acquire_token()
            event.set()

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
            return True
        if isinstance(exc, anthropic.RateLimitError):
            return True
        if isinstance(exc, anthropic.InternalServerError):
            return exc.status_code in self._config.retryable_status_codes
        return False

    def call(self, **kwargs: Any) -> anthropic.types.Message:
        kwargs.setdefault("timeout", self._config.timeout_seconds)
        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            grant = threading.Event()
            self._queue.put(grant)
            grant.wait()
            try:
                return self._watchdog.guard(self._client.messages.create, **kwargs)
            except Exception as exc:
                if not self._is_retryable(exc):
                    raise
                last_exc = exc
                if attempt < self._config.max_retries:
                    wait = self._config.backoff_factor * (2**attempt) + random.uniform(0, 0.5)
                    _logger.warning("Retry %d/%d: %s -- waiting %.2fs", attempt + 1, self._config.max_retries, type(exc).__name__, wait)
                    time.sleep(wait)
        if isinstance(last_exc, anthropic.APITimeoutError):
            _logger.error("All retries exhausted (timeout): %s", last_exc)
            raise GatekeeperTimeoutError(str(last_exc)) from last_exc
        if isinstance(last_exc, anthropic.RateLimitError):
            _logger.error("All retries exhausted (rate limit): %s", last_exc)
            raise GatekeeperRateLimitError(str(last_exc)) from last_exc
        _logger.error("All retries exhausted: %s", last_exc)
        raise GatekeeperError(str(last_exc)) from last_exc
