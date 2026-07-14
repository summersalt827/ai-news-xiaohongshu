#!/usr/bin/env python3
"""Circuit breaker pattern for external API calls.

Tracks consecutive failures per named service. After threshold failures,
opens the circuit for a cooldown period. In half-open state, allows one
probe call — closes on success, re-opens on failure.

Usage:
    cb = get_breaker("claude-api")  # global singleton per service
    if not cb.allow_call():
        return fail_fast()
    try:
        result = call_api()
        cb.on_success()
    except Exception:
        cb.on_failure()
        raise
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class CircuitBreaker:
    """Track failures for one named service and decide whether to allow calls."""

    name: str
    failure_threshold: int = 3       # consecutive failures to open circuit
    cooldown_seconds: float = 30.0   # wait before half-open probe
    max_cooldown: float = 300.0      # cap exponential backoff at 5 min

    _failures: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _state: str = field(default="closed", init=False)  # closed | open | half-open
    _total_failures: int = field(default=0, init=False)
    _total_successes: int = field(default=0, init=False)

    # ── Global registry ──────────────────────────────────────

    _instances: ClassVar[dict[str, CircuitBreaker]] = {}

    @classmethod
    def get(cls, name: str, **kwargs) -> CircuitBreaker:
        """Get or create a named circuit breaker (singleton per service name)."""
        if name not in cls._instances:
            cls._instances[name] = cls(name=name, **kwargs)
        return cls._instances[name]

    # ── Public API ───────────────────────────────────────────

    def allow_call(self) -> bool:
        """Check if a call should be attempted. Returns False if circuit is open."""
        if self._state == "closed":
            return True

        if self._state == "open":
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._current_cooldown():
                self._state = "half-open"
                return True
            return False

        # half-open: allow one probe
        return True

    def on_success(self) -> None:
        """Report a successful call — reset circuit."""
        if self._failures > 0:
            pass  # reset was needed
        self._failures = 0
        self._state = "closed"
        self._total_successes += 1

    def on_failure(self) -> None:
        """Report a failed call — increment failure count."""
        self._failures += 1
        self._total_failures += 1
        self._last_failure_time = time.monotonic()

        if self._failures >= self.failure_threshold:
            self._state = "open"

    # ── Diagnostics ──────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self._state == "open"

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self._state,
            "consecutive_failures": self._failures,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "cooldown": self._current_cooldown(),
        }

    # ── Internal ─────────────────────────────────────────────

    def _current_cooldown(self) -> float:
        """Exponential backoff capped at max_cooldown."""
        exp = min(self.cooldown_seconds * (2 ** (self._failures - self.failure_threshold)),
                  self.max_cooldown)
        return max(self.cooldown_seconds, exp)


# ── Convenience ──────────────────────────────────────────────

def get_breaker(service: str, **kwargs) -> CircuitBreaker:
    """Shorthand for CircuitBreaker.get()."""
    return CircuitBreaker.get(service, **kwargs)


def all_breakers() -> dict[str, CircuitBreaker]:
    """Return all registered circuit breakers for diagnostics."""
    return dict(CircuitBreaker._instances)


def reset_all() -> None:
    """Reset all circuit breakers (for testing)."""
    CircuitBreaker._instances.clear()
