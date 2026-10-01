"""Shared helpers: in-memory SQLite for the communication ORM (no containers) and a TestClient factory.

Not a conftest.py on purpose: tests import it explicitly (`from services.communication.tests.conftest_db import ...`).
The users table is faked as a plain table so validate_tenant_users works; ANY(:ids) is not valid SQLite
so that function is replaced with a set-membership fake via `known_users`.
"""

import asyncio
import os
import sys
import uuid
from contextlib import asynccontextmanager

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from services.common.auth import AuthContext, get_auth_context  # noqa: E402
from services.communication import access  # noqa: E402
from services.communication.models import Base  # noqa: E402
from services.communication.routes import (  # noqa: E402
    approvals, channel_preferences, channels, escalations, events, messages, messages_state, schedule, sessions, tasks, ws,
)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(_t, _c, **_k):
    return "JSON"


TENANT = uuid.UUID("a0000000-0000-0000-0000-000000000001")  # must contain a hex letter: SQLite NUMERIC affinity mangles all-digit UUIDs
OTHER_TENANT = uuid.UUID("a0000000-0000-0000-0000-000000000002")
ALICE = uuid.UUID("aaaaaaaa-0000-0000-0000-00000000000a")
BOB = uuid.UUID("bbbbbbbb-0000-0000-0000-00000000000b")
CAROL = uuid.UUID("cccccccc-0000-0000-0000-00000000000c")
ADMIN = uuid.UUID("dddddddd-0000-0000-0000-00000000000d")
EVE = uuid.UUID("eeeeeeee-0000-0000-0000-00000000000e")  # other tenant


def ctx_for(user, tenant=TENANT, roles=()):
    return AuthContext(user_id=user, tenant_id=tenant, roles=list(roles), rbac_loaded=True)


class Env:
    def __init__(self, monkeypatch):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        self.maker = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self._create())
        self.current = ctx_for(ALICE)
        self.known_users = {ALICE, BOB, CAROL, ADMIN}

        @asynccontextmanager
        async def scope(*_a, **_k):
            async with self.maker() as s:
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise

        for mod, name in (
            (channels, "session_scope"), (messages, "session_scope"), (messages_state, "session_scope"),
            (tasks, "session_scope"), (approvals, "session_scope"), (escalations, "session_scope"),
            (events, "session_scope"), (sessions, "session_scope"), (channel_preferences, "session_scope"),
            (schedule, "get_session"), (ws, "session_scope"),
        ):
            monkeypatch.setattr(mod, name, scope)

        async def fake_unknown(_session, _tenant, user_ids):
            return [u for u in user_ids if u not in self.known_users]

        for mod in (channels, tasks, escalations, schedule):
            monkeypatch.setattr(mod, "validate_tenant_users", fake_unknown)
        monkeypatch.setattr(access, "validate_tenant_users", fake_unknown)
        # keep broadcasts from touching the event loop of the TestClient thread
        monkeypatch.setattr(messages, "spawn_broadcast", lambda *a, **k: self.broadcasts.append(a))
        self.broadcasts = []

        app = FastAPI()
        for r in (channels.router, messages.router, messages_state.router, tasks.router, approvals.router,
                  escalations.router, events.router, schedule.router, sessions.router, channel_preferences.router):
            app.include_router(r, prefix="/api/v1")
        app.dependency_overrides[get_auth_context] = lambda: self.current
        self.client = TestClient(app)

    async def _create(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def as_user(self, user, tenant=TENANT, roles=()):
        self.current = ctx_for(user, tenant, roles)
        return self.client

    def close(self):
        self.client.close()
        self.run(self.engine.dispose())
        self.loop.close()
