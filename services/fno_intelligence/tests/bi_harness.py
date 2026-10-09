"""Test harness for BI Studio / Deck Studio: SQLite with the real analytics + BI tables, hand-made copies of the
cross-service source tables (only the columns the registry reads), a fake LLM and fake Firecrawl. No network."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.common import background_tasks, url_safety  # noqa: E402
from services.fno_intelligence import analytics_common as ac  # noqa: E402
from services.fno_intelligence import bi_semantic, database  # noqa: E402
from services.fno_intelligence.analytics_models import ANALYTICS_TABLES  # noqa: E402
from services.fno_intelligence.bi_models import BI_TABLES  # noqa: E402
from services.fno_intelligence.bi_routes import router  # noqa: E402
from services.fno_intelligence.models import Base  # noqa: E402
from services.fno_intelligence.tests.analytics_harness import FakeFirecrawl, FakeLLM  # noqa: E402,F401

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
USER2 = uuid.UUID("22222222-2222-4222-8222-222222222222")
P = "/api/fno/bi"

SOURCE_DDL = [
    "CREATE TABLE invoices (id CHAR(32), tenant_id CHAR(32), customer_id CHAR(32), subscription_id CHAR(32), number TEXT, "
    "status TEXT, subtotal_zar NUMERIC, vat_zar NUMERIC, total_zar NUMERIC, amount_paid_zar NUMERIC, due_date DATE, "
    "billing_period_start DATE, created_at TIMESTAMP, credit_note_of CHAR(32))",
    "CREATE TABLE subscriptions (id CHAR(32), tenant_id CHAR(32), customer_id CHAR(32), plan TEXT, segment TEXT, status TEXT, "
    "billing_interval TEXT, base_price_zar NUMERIC, quantity INTEGER, created_at TIMESTAMP, cancelled_at TIMESTAMP)",
    "CREATE TABLE payments (id CHAR(32), tenant_id CHAR(32), invoice_id CHAR(32), customer_id CHAR(32), amount_zar NUMERIC, "
    "method TEXT, status TEXT, created_at TIMESTAMP)",
    "CREATE TABLE customers (id CHAR(32), tenant_id CHAR(32), status TEXT, province TEXT, rica_verified BOOLEAN, company_id CHAR(32), "
    "created_at TIMESTAMP)",
    "CREATE TABLE leads (id CHAR(32), tenant_id CHAR(32), status TEXT, source TEXT, converted_at TIMESTAMP, created_at TIMESTAMP)",
    "CREATE TABLE deal_stages (id CHAR(32), pipeline_id CHAR(32), name TEXT, sort_order INTEGER)",
    "CREATE TABLE deals (id CHAR(32), tenant_id CHAR(32), stage_id CHAR(32), name TEXT, value_zar NUMERIC, status TEXT, "
    "close_date DATE, closed_at TIMESTAMP, created_at TIMESTAMP)",
    "CREATE TABLE tickets (id CHAR(32), tenant_id CHAR(32), priority TEXT, status TEXT, category TEXT, is_fcr BOOLEAN, "
    "resolved_at TIMESTAMP, created_at TIMESTAMP)",
    "CREATE TABLE network_services (id CHAR(32), tenant_id CHAR(32), status TEXT, technology TEXT, fno_provider TEXT, province TEXT, "
    "speed_profile_name TEXT, download_speed_mbps INTEGER, upload_speed_mbps INTEGER, created_at TIMESTAMP, activated_at TIMESTAMP)",
    "CREATE TABLE network_sla_breaches (id CHAR(32), tenant_id CHAR(32), severity TEXT, metric_type TEXT, started_at TIMESTAMP, "
    "resolved_at TIMESTAMP, duration_seconds INTEGER)",
    "CREATE TABLE marketing_campaigns (id CHAR(32), tenant_id CHAR(32), name TEXT, channel TEXT, status TEXT, description TEXT, "
    "budget_zar NUMERIC, total_sent INTEGER, total_delivered INTEGER, total_opened INTEGER, total_clicked INTEGER, "
    "total_conversions INTEGER, start_date TIMESTAMP, created_at TIMESTAMP)",
    "CREATE TABLE marketing_daily_metrics (id CHAR(32), tenant_id CHAR(32), metric_date DATE, attribution TEXT, platform TEXT, "
    "post_count INTEGER, impressions INTEGER, reach INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER, "
    "clicks INTEGER, views INTEGER)",
    "CREATE TABLE marketing_post_analytics (id CHAR(32), tenant_id CHAR(32), platform TEXT, published_at TIMESTAMP, likes INTEGER, "
    "comments INTEGER, impressions INTEGER, reach INTEGER, shares INTEGER, saves INTEGER, clicks INTEGER, views INTEGER)",
]


def hexid(u=None) -> str:
    return (u or uuid.uuid4()).hex


class Env:
    def __init__(self, client, fc, llm, engine):
        self.client, self.fc, self.llm, self.engine = client, fc, llm, engine

    @staticmethod
    def h(tenant=TENANT_A, roles="analyst", user=USER):
        return {"X-User-Id": str(user), "X-Tenant-Id": str(tenant), "X-Roles": roles}

    async def req(self, method, path, *, tenant=TENANT_A, roles="analyst", user=USER, headers=None, **kw):
        return await self.client.request(method, P + path, headers={**self.h(tenant, roles, user), **(headers or {})}, **kw)

    async def sql(self, stmt: str, **params):
        async with self.engine.begin() as conn:
            await conn.execute(text(stmt), params)

    async def insert(self, table: str, **cols):
        names = ", ".join(cols)
        marks = ", ".join(f":{c}" for c in cols)
        vals = {k: (v.hex if isinstance(v, uuid.UUID) else v) for k, v in cols.items()}
        await self.sql(f"INSERT INTO {table} ({names}) VALUES ({marks})", **vals)


@asynccontextmanager
async def env(tmp_path, monkeypatch, *, llm_responder=None):
    monkeypatch.setenv("AUTH_MODE", "header")
    monkeypatch.setenv("AUTH_DB_ENFORCE", "false")
    monkeypatch.delenv("ANALYTICS_ENFORCE_ROLES", raising=False)
    monkeypatch.setenv("FIRECRAWL_TENANT_MONTHLY_CREDITS", "2000")
    monkeypatch.setenv("FIRECRAWL_TENANT_DAILY_CREDITS", "2000")
    monkeypatch.setenv("BI_QUERY_RATE_PER_MIN", "10000")
    monkeypatch.setattr(url_safety, "_default_resolver", lambda host, port: ["93.184.216.34"])
    bi_semantic.reset_rate_limits()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bi.db'}", connect_args={"timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=ANALYTICS_TABLES + BI_TABLES))
        for ddl in SOURCE_DDL:
            await conn.execute(text(ddl))
    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(database, "_session_factory", sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    fc, llm = FakeFirecrawl(), FakeLLM(llm_responder)
    monkeypatch.setattr(ac, "get_firecrawl", lambda: fc)
    monkeypatch.setattr(ac, "llm_complete", llm)
    app = FastAPI()
    app.include_router(router, prefix="/api/fno")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        yield Env(client, fc, llm, engine)
    await engine.dispose()


async def seed_billing(e: Env):
    """Tenant A: 3 months of invoices; tenant B: one big invoice that must never leak into A's numbers."""
    cust = [uuid.uuid4() for _ in range(3)]
    sub = uuid.uuid4()
    await e.insert("subscriptions", id=sub, tenant_id=TENANT_A, customer_id=cust[0], plan="Fibre 100", segment="Residential",
                   status="active", billing_interval="monthly", base_price_zar=500, quantity=1,
                   created_at="2026-01-05 10:00:00", cancelled_at=None)
    rows = [  # (status, total, paid, due, created, customer)
        ("paid", 1000, 1000, "2026-01-31", "2026-01-10 08:00:00", cust[0]),
        ("paid", 1100, 1100, "2026-02-28", "2026-02-10 08:00:00", cust[1]),
        ("sent", 1300, 0, "2099-03-31", "2026-03-10 08:00:00", cust[2]),
        ("overdue", 500, 100, "2026-01-15", "2026-03-11 08:00:00", cust[0]),
        ("draft", 9999, 0, "2026-03-31", "2026-03-12 08:00:00", cust[0]),   # excluded
        ("voided", 8888, 0, "2026-03-31", "2026-03-13 08:00:00", cust[0]),  # excluded
    ]
    for i, (st, tot, paid, due, created, c) in enumerate(rows):
        await e.insert("invoices", id=uuid.uuid4(), tenant_id=TENANT_A, customer_id=c, subscription_id=sub if i == 0 else None,
                       number=f"INV-{i}", status=st, subtotal_zar=tot / 1.15, vat_zar=tot - tot / 1.15, total_zar=tot,
                       amount_paid_zar=paid, due_date=due, billing_period_start=created[:10], created_at=created)
    await e.insert("invoices", id=uuid.uuid4(), tenant_id=TENANT_B, customer_id=uuid.uuid4(), subscription_id=None, number="B-1",
                   status="paid", subtotal_zar=1, vat_zar=0, total_zar=777777, amount_paid_zar=777777, due_date="2026-02-01",
                   billing_period_start="2026-02-01", created_at="2026-02-01 08:00:00")


def run(coro):
    return asyncio.run(coro)


def resp_json(r, status=200):
    assert r.status_code == status, f"{r.status_code}: {r.text[:500]}"
    return r.json() if r.content else None
