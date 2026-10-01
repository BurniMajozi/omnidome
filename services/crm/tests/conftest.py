import importlib.metadata
import sys
from unittest.mock import MagicMock

orig_version = importlib.metadata.version

def mock_version(pkg):
    if pkg == "email-validator":
        return "2.1.0"
    return orig_version(pkg)

importlib.metadata.version = mock_version

if "email_validator" not in sys.modules:
    ev = MagicMock()
    ev.validate_email = lambda email, **kwargs: MagicMock(normalized=email, email=email)
    sys.modules["email_validator"] = ev


# ---------------------------------------------------------------------------
# SQLite-backed harness for route behaviour tests (no Postgres needed)
# ---------------------------------------------------------------------------
import os
import uuid
from contextlib import asynccontextmanager

import pytest

os.environ.setdefault("AUTH_MODE", "header")
os.environ.setdefault("AUTH_ENFORCE_RBAC", "false")  # roles come from the X-Roles header
os.environ.setdefault("AUTH_ENFORCE_MODULES", "false")

TENANT_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
TENANT_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
USER = uuid.UUID("00000000-0000-0000-0000-0000000000f1")


def headers(tenant=TENANT_A, roles="org_admin"):
    return {"X-User-Id": str(USER), "X-Tenant-Id": str(tenant), "X-Roles": roles}


@pytest.fixture()
def crm_env(tmp_path, monkeypatch):
    """(TestClient, session_factory): CRM routers on a throw-away SQLite database."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.pool import NullPool

    @compiles(JSONB, "sqlite")
    def _jsonb(type_, compiler, **kw):  # noqa: ARG001
        return "JSON"

    import asyncio

    from services.lifecycle.models import CustomerLifecycle
    from services.crm import access, database, models
    from services.crm.routes import (companies, customer_360, customers, dashboard, leads, notes_tags, segments)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'crm.db'}", poolclass=NullPool)
    tables = [models.Company.__table__, models.Customer.__table__, models.Lead.__table__,
              models.ActivityEvent.__table__, models.CustomerNote.__table__, models.CustomerTag.__table__,
              models.Segment.__table__, models.RetentionPrediction.__table__,
              CustomerLifecycle.__table__]

    async def _create():
        async with engine.begin() as conn:
            for t in tables:
                await conn.run_sync(lambda c, t=t: t.create(c, checkfirst=True))

    asyncio.run(_create())
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def get_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    for mod in (database, access, companies, customer_360, customers, dashboard, leads, notes_tags, segments):
        if hasattr(mod, "get_session"):
            monkeypatch.setattr(mod, "get_session", get_session)
    monkeypatch.setenv("CRM_ENFORCE_ROLES", "true")

    app = FastAPI()
    for r in (dashboard.router, customers.router, leads.router, companies.router, notes_tags.router,
              segments.router, customer_360.router):
        app.include_router(r)
    yield TestClient(app), factory
    asyncio.run(engine.dispose())
