"""Portal builder tests run on a throwaway SQLite file (no Postgres needed).

Role gates stay ON; the RBAC table lookup is replaced by the roles carried in X-Roles.
"""
import os
import sys
import tempfile
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

_DB = os.path.join(tempfile.mkdtemp(prefix="portal_test_"), "portal.sqlite")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ["AUTH_MODE"] = "header"
os.environ["AUTH_ENFORCE_MODULES"] = "false"
os.environ["PORTAL_RUN_MIGRATIONS"] = "false"
os.environ["PORTAL_ENFORCE_ROLES"] = "true"
os.environ.pop("SEO_PROVIDER_API_KEY", None)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _uuid(type_, compiler, **kw):  # noqa: ANN001
    return "CHAR(36)"


from fastapi.testclient import TestClient  # noqa: E402

from services.common.db import Base  # noqa: E402
from services.portal_builder import access, fetcher, main  # noqa: E402

_engine = create_engine(f"sqlite:///{_DB}")
Base.metadata.create_all(_engine)

LIMITERS = ("_public_limiter", "_submit_limiter", "_shared_limiter", "_share_create_limiter", "_fetch_limiter")


@pytest.fixture(scope="session")
def client():
    main.guard.is_licensed = lambda: True
    main.guard.ensure_startup = lambda: None
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    async def roles_from_header(auth):
        return {str(r).strip().lower() for r in auth.roles}, set()

    monkeypatch.setattr(access, "effective_access", roles_from_header)

    async def allow_all(session, tenant_id, emails):
        return list(emails), []

    monkeypatch.setattr(main.suppression, "filter_suppressed", allow_all)
    for name in LIMITERS:
        getattr(main, name)._requests.clear()
    monkeypatch.setattr(fetcher, "_transport", None)
    monkeypatch.setattr(fetcher, "_resolver", lambda host, port: ["93.184.216.34"])
    yield


class Tenant:
    def __init__(self, role="admin"):
        self.id = uuid.uuid4()
        self.user = uuid.uuid4()
        self.role = role

    def h(self, role=None):
        return {"X-User-Id": str(self.user), "X-Tenant-Id": str(self.id), "X-Roles": role or self.role}


@pytest.fixture
def tenant():
    return Tenant()


def make_page(client, tenant, slug=None, **fields):
    body = {"slug": slug or f"pg-{uuid.uuid4().hex[:10]}", "title": "Fibre Promo", **fields}
    r = client.post("/api/v1/portal/pages", json=body, headers=tenant.h())
    assert r.status_code == 201, r.text
    return r.json()
