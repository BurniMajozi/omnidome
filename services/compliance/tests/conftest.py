"""Shared setup: repo root on sys.path, asyncio-only anyio backend, no role/RBAC surprises."""
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    # Roles come from the identity (no RBAC tables in the SQLite test DB); gates stay ON.
    monkeypatch.setenv("AUTH_ENFORCE_RBAC", "false")
    monkeypatch.delenv("COMPLIANCE_ENFORCE_ROLES", raising=False)
    monkeypatch.delenv("COMPLIANCE_ALLOW_HTTP", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
