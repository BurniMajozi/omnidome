"""Test harness for the Analytics & AI features: in-memory-ish SQLite (real queries), fake Firecrawl,
fake LLM, no network. Tests are plain sync functions that run `asyncio.run(scenario())`.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager

import httpx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.common import background_tasks, url_safety  # noqa: E402
from services.fno_intelligence import analytics_common as ac  # noqa: E402
from services.fno_intelligence import database  # noqa: E402
from services.fno_intelligence.analytics_models import ANALYTICS_TABLES  # noqa: E402
from services.fno_intelligence.analytics_routes import router  # noqa: E402
from services.fno_intelligence.models import Base  # noqa: E402

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
P = "/api/fno/analytics"


class FakeFirecrawl:
    """search_data: callable(query, kw) -> dict | dict. pages: {url: {"markdown": str, "json": dict|None}}."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.search_data = {"data": {"web": []}}
        self.pages: dict[str, dict] = {}
        self.map_links: list[dict] = []
        self.fail_urls: set[str] = set()

    def count(self, kind):
        return sum(1 for c in self.calls if c[0] == kind)

    async def search(self, query, **kw):
        self.calls.append(("search", query, kw))
        d = self.search_data
        return d(query, kw) if callable(d) else d

    async def scrape(self, url, formats=None, **kw):
        self.calls.append(("scrape", url, formats))
        if url in self.fail_urls or url not in self.pages:
            raise RuntimeError(f"scrape failed for {url}")
        pg = self.pages[url]
        data = {"markdown": pg.get("markdown", "")}
        if any(isinstance(f, dict) for f in (formats or [])) and pg.get("json") is not None:
            data["json"] = pg["json"]
        return {"data": data}

    async def map_site(self, url, **kw):
        self.calls.append(("map", url, kw))
        return {"links": self.map_links}


class FakeLLM:
    def __init__(self, responder=None):
        self.responder = responder  # callable(system, user) -> str | None
        self.prompts: list[tuple[str, str]] = []

    async def __call__(self, system, user, **kw):
        self.prompts.append((system, user))
        out = self.responder(system, user) if self.responder else None
        return None if out is None else (out, "fake/model")


class Env:
    def __init__(self, client, fc, llm):
        self.client, self.fc, self.llm = client, fc, llm

    @staticmethod
    def h(tenant=TENANT_A, roles="analyst", user=USER):
        return {"X-User-Id": str(user), "X-Tenant-Id": str(tenant), "X-Roles": roles}

    async def req(self, method, path, *, tenant=TENANT_A, roles="analyst", **kw):
        return await self.client.request(method, P + path, headers=self.h(tenant, roles), **kw)

    async def drain(self):
        while background_tasks._BACKGROUND_TASKS:
            await asyncio.gather(*list(background_tasks._BACKGROUND_TASKS), return_exceptions=True)


@asynccontextmanager
async def env(tmp_path, monkeypatch, *, llm_responder=None):
    monkeypatch.setenv("AUTH_MODE", "header")
    monkeypatch.setenv("AUTH_DB_ENFORCE", "false")
    monkeypatch.delenv("ANALYTICS_ENFORCE_ROLES", raising=False)
    monkeypatch.setenv("FIRECRAWL_TENANT_MONTHLY_CREDITS", "2000")
    monkeypatch.setenv("FIRECRAWL_TENANT_DAILY_CREDITS", "2000")
    monkeypatch.setattr(url_safety, "_default_resolver", lambda host, port: ["93.184.216.34"])
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analytics.db'}", connect_args={"timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=ANALYTICS_TABLES))
        await conn.execute(text("CREATE TABLE marketing_campaigns (id CHAR(32), tenant_id CHAR(32), name TEXT, "
                                "channel TEXT, description TEXT)"))
    monkeypatch.setattr(database, "_engine", engine)
    monkeypatch.setattr(database, "_session_factory", sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    fc, llm = FakeFirecrawl(), FakeLLM(llm_responder)
    monkeypatch.setattr(ac, "get_firecrawl", lambda: fc)
    monkeypatch.setattr(ac, "llm_complete", llm)
    app = FastAPI()
    app.include_router(router, prefix="/api/fno")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        e = Env(client, fc, llm)
        try:
            yield e
        finally:
            await e.drain()
    await engine.dispose()


def web(*items):
    return {"data": {"web": list(items)}}


def hit(url, text_, title="T", description=None):
    return {"url": url, "title": title, "description": description or text_[:80], "markdown": text_}


LONG = " lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor" * 4
