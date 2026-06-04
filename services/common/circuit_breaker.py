"""Shared circuit breaker and retry utilities for OmniDome cross-service calls.

Usage in any service making cross-service HTTP calls:

    from services.common.circuit_breaker import circuit_breaker

    @circuit_breaker("crm", failure_threshold=3, recovery_timeout=30)
    async def call_crm(payload):
        async with httpx.AsyncClient(timeout=5) as client:
            return await client.post(CRM_URL, json=payload)

The circuit breaker tracks failures per service name. After `failure_threshold`
consecutive failures, the circuit opens and calls fail fast for `recovery_timeout`
seconds. After timeout, one probe call is allowed (half-open state). If it
succeeds, the circuit closes again.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open"  # Allowing one probe


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and the call is rejected."""
    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Circuit breaker OPEN for service: {service_name}")


class _CircuitBreaker:
    def __init__(self, service_name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker %s → HALF_OPEN (recovery timeout elapsed)", self.service_name)
        return self._state

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            current_state = self.state
            if current_state == CircuitState.OPEN:
                logger.warning("Circuit breaker OPEN for %s — rejecting call", self.service_name)
                raise CircuitBreakerError(self.service_name)

        try:
            result = await fn(*args, **kwargs)
            async with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    logger.info("Circuit breaker %s → CLOSED (probe succeeded)", self.service_name)
                self._failure_count = 0
                self._state = CircuitState.CLOSED
            return result
        except Exception as exc:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.monotonic()
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(
                        "Circuit breaker %s → OPEN (%d consecutive failures)",
                        self.service_name, self._failure_count,
                    )
                else:
                    logger.warning(
                        "Circuit breaker %s failure %d/%d: %s",
                        self.service_name, self._failure_count, self.failure_threshold, exc,
                    )
            raise


# Registry of circuit breakers per service name
_breakers: dict[str, _CircuitBreaker] = {}


def circuit_breaker(
    service_name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> Callable:
    """Decorator that wraps an async function with circuit breaker protection.

    Args:
        service_name: Logical name of the downstream service (e.g. "crm", "billing").
        failure_threshold: Number of consecutive failures before the circuit opens.
        recovery_timeout: Seconds to wait before allowing a probe call (half-open).
    """
    if service_name not in _breakers:
        _breakers[service_name] = _CircuitBreaker(
            service_name, failure_threshold, recovery_timeout,
        )

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await _breakers[service_name].call(fn, *args, **kwargs)
        return wrapper
    return decorator


def get_breaker_state(service_name: str) -> Optional[dict]:
    """Return the current state of a circuit breaker (for health/monitoring)."""
    b = _breakers.get(service_name)
    if not b:
        return None
    return {
        "service": service_name,
        "state": b.state.value,
        "failure_count": b._failure_count,
        "failure_threshold": b.failure_threshold,
        "recovery_timeout": b.recovery_timeout,
    }


def get_all_breaker_states() -> list[dict]:
    """Return states of all circuit breakers."""
    return [s for name in sorted(_breakers.keys()) if (s := get_breaker_state(name)) is not None]
