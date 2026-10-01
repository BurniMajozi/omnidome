"""Support hardening: finance bridge, broadcast, role tiers, startup wiring."""
import asyncio
import os
import sys
import uuid
from datetime import date
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from services.common import internal_auth  # noqa: E402
from services.support import access, finance_bridge  # noqa: E402

TID, UID = uuid.uuid4(), uuid.uuid4()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "unit-test-secret-unit-test-secret")
    monkeypatch.setenv("SUPPORT_EXPENSE_ACCOUNT_CODE", "5100")
    monkeypatch.setenv("SUPPORT_OFFSET_ACCOUNT_CODE", "2100")
    monkeypatch.setenv("SUPPORT_LABOUR_RATE_PER_HOUR", "300")
    monkeypatch.setenv("SUPPORT_ENFORCE_ROLES", "true")


# ------------------------------------------------------------------ finance bridge

def test_no_real_cost_posts_nothing(monkeypatch):
    assert finance_bridge.build_entry(TID, "x", date.today(), [], None) is None
    assert finance_bridge.build_entry(TID, "x", date.today(), [], 0) is None
    monkeypatch.delenv("SUPPORT_LABOUR_RATE_PER_HOUR")           # no configured rate => labour is not costed
    assert finance_bridge.build_entry(TID, "x", date.today(), [], 90) is None
    assert finance_bridge.build_entry(TID, "x", date.today(), [{"unit_cost": -5, "quantity": 2}, {"unit_cost": "nan"}], None) is None


def test_unconfigured_accounts_post_nothing(monkeypatch):
    monkeypatch.delenv("SUPPORT_EXPENSE_ACCOUNT_CODE")
    assert finance_bridge.build_entry(TID, "x", date.today(), [{"unit_cost": 10, "quantity": 1}], 30) is None


def test_entry_from_recorded_costs_only():
    e = finance_bridge.build_entry(TID, "Router swap", date(2026, 10, 1),
                                   [{"unit_cost": 100.5, "quantity": 2}], 90)
    # parts 201.00 + 90 min x R300/h = 450.00 -> 651.00 (never a flat R150)
    assert e["lines"] == [
        {"account_code": "5100", "debit": "651.00", "credit": "0.00"},
        {"account_code": "2100", "debit": "0.00", "credit": "651.00"},
    ]
    assert e["source"] == "support.job" and e["source_id"] == str(TID) and e["auto_post"] is True
    assert e["date"] == "2026-10-01"


def test_post_is_signed_with_tenant_and_user_and_handles_status():
    seen = {}

    def handler(request: httpx.Request):
        seen["h"], seen["path"] = dict(request.headers), request.url.path
        return httpx.Response(seen.get("code", 200), json={})

    async def run(code):
        seen["code"] = code
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await finance_bridge.post_entry(TID, UID, {"x": 1}, client=c)

    assert asyncio.run(run(201)) == ("posted", None)
    h = seen["h"]
    assert seen["path"] == "/journal-entries"
    assert h["x-tenant-id"] == str(TID) and h["x-user-id"] == str(UID)
    assert "x-identity-sig" in h and "x-identity-ts" in h
    expect = internal_auth.sign_headers({"x-user-id": str(UID), "x-tenant-id": str(TID)}, "POST", "/journal-entries",
                                        now=int(h["x-identity-ts"]))
    assert h["x-identity-sig"] == expect["x-identity-sig"]
    assert asyncio.run(run(401)) == ("failed", "finance HTTP 401")
    assert asyncio.run(run(500))[0] == "failed"


def test_transport_error_and_missing_secret_are_recorded(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("connection refused to finance:8015")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as c:
            return await finance_bridge.post_entry(TID, UID, {}, client=c)

    status, err = asyncio.run(run())
    assert status == "failed" and err == "transport: ConnectError" and "8015" not in err
    monkeypatch.delenv("INTERNAL_AUTH_SECRET")
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    status, err = asyncio.run(finance_bridge.post_entry(TID, UID, {}))
    assert status == "failed" and err.startswith("signing")


# ------------------------------------------------------------------ roles

def _ctx(roles=(), user=UID, platform=False):
    return SimpleNamespace(roles=list(roles), permissions=[], is_platform_admin=platform, rbac_loaded=True,
                           user_id=user, tenant_id=TID)


def _ok(ctx, tier):
    return asyncio.run(access.has_tier(ctx, None, tier))


def test_tiers():
    assert _ok(_ctx(), "viewer")
    assert not _ok(_ctx(["viewer"]), "technician")
    assert _ok(_ctx(["technician"]), "technician") and not _ok(_ctx(["technician"]), "manager")
    assert _ok(_ctx(["manager"]), "manager") and not _ok(_ctx(["manager"]), "admin")
    assert _ok(_ctx(["owner"]), "admin")
    assert _ok(_ctx(platform=True), "admin")


def test_job_access_own_unassigned_or_manager():
    other = uuid.uuid4()
    tech = _ctx(["technician"])
    asyncio.run(access.require_job_access(tech, None, None))
    asyncio.run(access.require_job_access(tech, None, UID))
    with pytest.raises(HTTPException) as e:
        asyncio.run(access.require_job_access(tech, None, other))
    assert e.value.status_code == 403
    asyncio.run(access.require_job_access(_ctx(["manager"]), None, other))


def test_every_mutating_route_is_gated():
    from services.support.main import app
    gated = {"POST", "PUT", "DELETE", "PATCH"}
    want = {"/tickets": "manager", "/tickets/{ticket_id}": None, "/network/broadcast": "admin",
            "/tickets/{ticket_id}/escalate-fno": "manager"}
    for r in app.routes:
        if getattr(r, "methods", None) and gated & r.methods and r.path not in ("/",):
            names = [d.call.__name__ for d in r.dependant.dependencies]
            assert any(n.startswith("require_support_") for n in names), (r.path, r.methods)
            if r.path in want and want[r.path]:
                assert f"require_support_{want[r.path]}" in names, r.path
            if "DELETE" in r.methods:
                assert "require_support_admin" in names


# ------------------------------------------------------------------ broadcast, startup

def test_broadcast_requires_auth_and_is_501():
    from fastapi.testclient import TestClient
    from services.support.database import get_session
    from services.support.main import app

    async def fake_db():
        yield None

    client = TestClient(app)
    app.dependency_overrides[get_session] = fake_db
    try:
        r = client.post("/network/broadcast", params={"title": "t", "message": "m"})
        assert r.status_code in (401, 403, 422)            # no identity: never "SENT"
        # authorised callers: the tier dependency and the handler, called directly
        from services.support.main import broadcast_alert
        with pytest.raises(HTTPException) as e:
            asyncio.run(access.require(_ctx(["technician"]), None, "admin"))
        assert e.value.status_code == 403
        with pytest.raises(HTTPException) as e:
            asyncio.run(broadcast_alert("t", "m", auth=_ctx(["admin"])))
        assert e.value.status_code == 501 and "SENT" not in str(e.value.detail)
    finally:
        app.dependency_overrides.clear()


def test_startup_uses_retry_lifespan(monkeypatch):
    from services.support import main
    calls = []

    async def fake_retry(fn, **kw):
        calls.append(fn)

    monkeypatch.setattr(main, "run_with_db_retry", fake_retry)
    monkeypatch.setattr(main.guard, "ensure_startup", lambda: calls.append("guard"))

    async def run():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run())
    assert calls == ["guard", main.init_tables]
    assert main.app.router.lifespan_context is main.lifespan


def test_compose_local_runs_support_single_worker():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    text = open(os.path.join(root, "docker-compose.local.yml"), encoding="utf-8").read()
    block = text.split("  support:")[1].split("\n  retention:")[0]
    assert "--workers 1" in block
