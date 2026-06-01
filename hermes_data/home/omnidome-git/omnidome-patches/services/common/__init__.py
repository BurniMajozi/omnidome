"""
Shared utilities for OmniDome services.

Exports:
  - CircuitBreaker        : Per-service async circuit breaker
  - CircuitBreakerOpen    : Exception raised when breaker is OPEN
  - CircuitBreakerRegistry: Global registry singleton (.get() returns or creates breakers)
  - registry             : Module-level convenience instance of CircuitBreakerRegistry
  - service_call         : Resilient HTTP call (circuit breaker + retry + logging)
  - service_get          : Convenience wrapper for GET requests
  - service_post         : Convenience wrapper for POST requests
"""

from services.common.circuit_breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitBreakerRegistry,
    registry,
)
from services.common.http_client import (
    service_call,
    service_get,
    service_post,
)

__all__ = [
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerOpen",
    "CircuitBreakerRegistry",
    "BreakerState",
    "registry",
    # HTTP client
    "service_call",
    "service_get",
    "service_post",
]
