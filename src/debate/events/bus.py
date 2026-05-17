"""Thread-safe publish-subscribe event bus for debate lifecycle hooks."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class EventBus:
    """Register and fire typed debate lifecycle hooks.

    on() acquires a lock — safe for concurrent plugin registration.
    emit() reads without a lock — registrations complete before debate start.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        """Register handler for the named lifecycle event."""
        with self._lock:
            self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: Any) -> None:
        """Call all handlers registered for event. No-op if none registered."""
        for handler in self._handlers.get(event, []):
            handler(payload)
