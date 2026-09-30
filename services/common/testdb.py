"""Shared harness for service tests that run against a real Postgres.

    TEST_DATABASE_URL=postgresql://user:pass@host:5432/omnidome_test

Import `use_test_database()` before importing the service under test: it
points DATABASE_URL at the test database, or skips the module when no test
database is configured (CI sets REQUIRE_DB_TESTS=1 so a missing database
fails instead of silently skipping). It refuses any database whose name does
not end in "_test", so a mis-set variable can never touch dev or production
data. Build the schema once with scripts/setup_test_db.py.

Tests isolate themselves by working in a fresh tenant (new_tenant()), so no
table is truncated and suites can share one database.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

TEST_URL_ENV = "TEST_DATABASE_URL"


class UnsafeTestDatabase(RuntimeError):
    pass


def test_database_url() -> Optional[str]:
    url = os.getenv(TEST_URL_ENV, "").strip()
    if not url:
        if os.getenv("REQUIRE_DB_TESTS") == "1":
            raise RuntimeError(f"{TEST_URL_ENV} is not set but REQUIRE_DB_TESTS=1")
        return None
    from sqlalchemy.engine import make_url

    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise UnsafeTestDatabase(f"refusing to run tests against database '{name}': its name must end in _test")
    return url


def use_test_database(pytest_module=None) -> str:
    """Point the services at the test database (call before importing them).
    Skips the calling test module when none is configured."""
    url = test_database_url()
    if url is None:
        import pytest

        pytest.skip(f"{TEST_URL_ENV} not set (DB-backed tests)", allow_module_level=True)
    os.environ["DATABASE_URL"] = url
    os.environ["AUTH_MODE"] = "header"
    os.environ["AUTH_ENFORCE_MODULES"] = "false"   # module entitlements have their own tests
    os.environ.setdefault("AUTO_CREATE_TABLES", "false")
    reset_engines()
    return url


def reset_engines() -> None:
    """Drop cached engines/session factories (they bind to an event loop; each
    TestClient runs its own)."""
    from services.common import db

    for fn in (db.get_engine, db.get_async_engine, db._get_async_session_factory):
        fn.cache_clear()


def sync_engine():
    from services.common.db import get_engine

    return get_engine()


def new_tenant(name: str = "Test tenant") -> uuid.UUID:
    """A fresh tenant (and nothing else) for one test's data."""
    from sqlalchemy import text

    tenant_id = uuid.uuid4()
    with sync_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO tenants (id, name, subdomain, tier, status, active) "
                 "VALUES (:id, :name, :sub, 'ENTERPRISE', 'ACTIVE', true)"),
            {"id": tenant_id, "name": name, "sub": f"t-{tenant_id.hex[:12]}"},
        )
    return tenant_id


def new_user(tenant_id: uuid.UUID) -> uuid.UUID:
    from sqlalchemy import text

    user_id = uuid.uuid4()
    with sync_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, tenant_id, email, full_name, hashed_password, is_active) "
                 "VALUES (:id, :t, :email, 'Test User', 'not-used', true)"),
            {"id": user_id, "t": tenant_id, "email": f"user-{user_id.hex[:12]}@example.com"},
        )
    return user_id


def headers(tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> dict:
    return {"X-Tenant-Id": str(tenant_id), "X-User-Id": str(user_id or tenant_id)}
