import random
import threading
import time
from typing import Any

import anthropic

from .config import GatekeeperConfig


class GatekeeperError(Exception):
    pass


class GatekeeperTimeoutError(GatekeeperError):
    pass


class GatekeeperRateLimitError(GatekeeperError):
    pass


class ApiGatekeeper:
    def __init__(self, client: anthropic.Anthropic, config: GatekeeperConfig) -> None:
        self._client = client
        self._config = config
        self._lock = threading.Lock()
        self._tokens: float = float(config.requests_per_minute)
        self._last_refill: float = time.monotonic()
        self._refill_interval: float = 60.0 / config.requests_per_minute

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
            self._acquire_token()
            try:
                return self._client.messages.create(**kwargs)
            except Exception as exc:
                if not self._is_retryable(exc):
                    raise
                last_exc = exc
                if attempt < self._config.max_retries:
                    wait = self._config.backoff_factor * (2**attempt) + random.uniform(0, 0.5)
                    time.sleep(wait)
        if isinstance(last_exc, anthropic.APITimeoutError):
            raise GatekeeperTimeoutError(str(last_exc)) from last_exc
        if isinstance(last_exc, anthropic.RateLimitError):
            raise GatekeeperRateLimitError(str(last_exc)) from last_exc
        raise GatekeeperError(str(last_exc)) from last_exc
