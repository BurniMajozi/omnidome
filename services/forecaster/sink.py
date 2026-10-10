"""Writes forecast facts through tenant_memory's deterministic metric-facts API (the only write path)."""
from __future__ import annotations

import os
import uuid
from typing import Protocol

import httpx

from services.common import internal_auth

internal_auth.install_httpx_signing()      # signs the identity headers below when INTERNAL_AUTH_SECRET is set
SYSTEM_USER_DEFAULT = "00000000-0000-4000-8000-0000000000f2"


class SinkError(RuntimeError):
    pass


class Sink(Protocol):
    def write(self, tenant: str, fact: dict) -> dict: ...


class HttpSink:
    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None):
        self._base = (base_url if base_url is not None else os.getenv("TENANT_MEMORY_SERVICE_URL", "")).rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)

    def configured(self) -> bool:
        return bool(self._base)

    def write(self, tenant: str, fact: dict) -> dict:
        if not self._base:
            raise SinkError("TENANT_MEMORY_SERVICE_URL is not set")
        headers = {"X-Tenant-Id": str(uuid.UUID(str(tenant))), "X-User-Id": os.getenv("METRICS_SYSTEM_USER_ID", SYSTEM_USER_DEFAULT),
                   "X-Roles": "service", "X-Permissions": "metrics.write"}
        try:
            r = self._client.post(f"{self._base}/api/v1/metrics/facts", json=fact, headers=headers)
        except httpx.HTTPError as exc:
            raise SinkError(f"metric-facts API unreachable: {exc.__class__.__name__}") from exc
        if r.status_code >= 300:
            raise SinkError(f"metric-facts API {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}
