"""
Circuit Breaker for cross-service HTTP calls.

States:
  CLOSED   — Normal operation, requests pass through
  OPEN     — Failure threshold exceeded, requests fail fast
  HALF_OPEN — Testing recovery, limited requests allowed
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when a call is blocked by the circuit breaker."""
    def __init__(self, service: str):
        self.service = service
        super().__init__(f"Circuit breaker OPEN for {service} — call blocked")


class CircuitBreaker:
    """Async circuit breaker for a single service."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        service: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def success_count(self) -> int:
        return self._success_count

    async def __aenter__(self):
        async with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    logger.info("Circuit breaker %s: OPEN → HALF_OPEN (recovery timeout elapsed)", self.service)
                    self._state = self.HALF_OPEN
                    self._success_count = 0
                else:
                    raise CircuitBreakerOpen(self.service)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type is not None:
                self._record_failure()
            else:
                self._record_success()
        return False  # Don't suppress exceptions

    def _record_failure(self):
        self._failure_count += 1
        if self._state == self.HALF_OPEN:
            logger.warning("Circuit breaker %s: HALF_OPEN → OPEN (failure in test)", self.service)
            self._state = self.OPEN
            self._opened_at = time.monotonic()
        elif self._failure_count >= self.failure_threshold:
            if self._state == self.CLOSED:
                logger.warning("Circuit breaker %s: CLOSED → OPEN (%d failures)", self.service, self._failure_count)
                self._state = self.OPEN
                self._opened_at = time.monotonic()

    def _record_success(self):
        if self._state == self.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                logger.info("Circuit breaker %s: HALF_OPEN → CLOSED (recovered)", self.service)
                self._state = self.CLOSED
                self._failure_count = 0
                self._success_count = 0
        elif self._state == self.CLOSED:
            self._failure_count = max(0, self._failure_count - 1)


class CircuitBreakerRegistry:
    """Global registry of circuit breakers, one per service."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, service: str, **kwargs) -> CircuitBreaker:
        if service not in self._breakers:
            self._breakers[service] = CircuitBreaker(service, **kwargs)
        return self._breakers[service]

    def status(self) -> dict:
        return {name: {"state": cb.state, "failures": cb.failure_count} for name, cb in self._breakers.items()}


# Singleton
cb_registry = CircuitBreakerRegistry()
