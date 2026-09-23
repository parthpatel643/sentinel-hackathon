"""Resilience primitives shared by every ExternalRegistry provider — the
retry/circuit-breaker policy and rate limits docs/01-ARCHITECTURE.md §6.4
calls for. Deliberately generic (no gov_registry-specific knowledge) so
the same three pieces wrap VAHAN, SARTHI, eGujCop and AFIS identically.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "RateLimitExceededError",
    "RateLimiter",
    "with_retry",
]


class RateLimitExceededError(Exception):
    """Raised immediately (never blocks) when a caller exceeds a provider's
    configured request rate — mirrors a real government gateway returning
    HTTP 429 rather than queuing requests indefinitely."""


class RateLimiter:
    """A simple token bucket. Real integrator guides for these systems
    quote a modest per-minute quota per registered application; this
    enforces one locally instead of trusting every call site to behave."""

    def __init__(self, *, capacity: int, refill_period_s: float = 60.0):
        self._capacity = capacity
        self._refill_period_s = refill_period_s
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        refilled = elapsed * (self._capacity / self._refill_period_s)
        self._tokens = min(self._capacity, self._tokens + refilled)
        self._last_refill = now

    def acquire(self) -> None:
        self._refill()
        if self._tokens < 1:
            raise RateLimitExceededError(
                f"Rate limit exceeded ({self._capacity}/{self._refill_period_s:.0f}s) — "
                "back off before retrying."
            )
        self._tokens -= 1


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the breaker is open — the provider has failed enough
    consecutive times that we stop hammering it and let it recover."""


@dataclass
class CircuitBreaker:
    """Classic three-state breaker: CLOSED (normal) -> OPEN (failing, calls
    rejected) -> HALF_OPEN (one probe call allowed) -> CLOSED or OPEN
    again depending on that probe's outcome."""

    failure_threshold: int = 3
    recovery_timeout_s: float = 30.0
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> CircuitState:
        elapsed_since_open = self._opened_at is not None and (
            time.monotonic() - self._opened_at >= self.recovery_timeout_s
        )
        if self._state is CircuitState.OPEN and elapsed_since_open:
            return CircuitState.HALF_OPEN
        return self._state

    def before_call(self) -> None:
        if self.state is CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit open after {self._consecutive_failures} consecutive failures — "
                f"retry after the {self.recovery_timeout_s:.0f}s cooldown."
            )

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()


async def with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    circuit_breaker: CircuitBreaker,
    max_attempts: int = 3,
    backoff_base_s: float = 0.1,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Runs `fn`, retrying on `retry_on` exceptions with exponential
    backoff, gated by `circuit_breaker` (checked before every attempt,
    updated after every outcome)."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        circuit_breaker.before_call()
        try:
            result = await fn()
        except retry_on as exc:
            circuit_breaker.record_failure()
            last_exc = exc
            if attempt < max_attempts - 1:
                await asyncio.sleep(backoff_base_s * (2**attempt))
            continue
        else:
            circuit_breaker.record_success()
            return result
    assert last_exc is not None
    raise last_exc
