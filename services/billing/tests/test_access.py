"""Billing role tiers, internal-key-only cron endpoints and which routes carry which gate."""
import asyncio
import os
import sys
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from services.common.auth import AuthContext  # noqa: E402
from services.billing import access  # noqa: E402


@pytest.fixture(autouse=True)
def enforce(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCE_ROLES", "true")
    monkeypatch.delenv("BILLING_ADMIN_EXTRA_ROLES", raising=False)


def who(*roles, perms=(), platform=False):
    return AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=list(roles), permissions=list(perms),
                       is_platform_admin=platform, rbac_loaded=True)


def allowed(ctx, tier):
    return asyncio.run(access.has_tier(ctx, tier))


@pytest.mark.parametrize("role", ["billing_admin", "finance", "finance_admin", "admin", "tenant_admin", "owner", "platform_admin"])
def test_admin_roles_have_every_tier(role):
    ctx = who(role)
    assert all(allowed(ctx, t) for t in ("admin", "clerk", "reader"))


def test_org_admin_is_billing_admin_by_default(monkeypatch):
    monkeypatch.delenv("BILLING_ADMIN_EXTRA_ROLES", raising=False)
    assert allowed(who("org_admin"), "admin") and allowed(who("org_admin"), "reader")


def test_clerk_can_record_and_send_but_not_administer():
    clerk = who("billing_clerk")
    assert allowed(clerk, "clerk") and allowed(clerk, "reader") and not allowed(clerk, "admin")
    assert not allowed(who("manager"), "admin") and allowed(who("manager"), "clerk")


def test_viewer_is_read_only_and_a_generic_viewer_is_not_a_billing_role():
    v = who("billing_viewer")
    assert allowed(v, "reader") and not allowed(v, "clerk") and not allowed(v, "admin")
    g = who("viewer", "member")
    assert not any(allowed(g, t) for t in ("admin", "clerk", "reader"))


def test_permissions_grant_tiers():
    assert allowed(who(perms=["billing.admin"]), "admin")
    assert allowed(who(perms=["billing.write"]), "clerk") and not allowed(who(perms=["billing.write"]), "admin")
    assert allowed(who(perms=["billing.read"]), "reader") and not allowed(who(perms=["billing.read"]), "clerk")


def test_platform_admin_and_escape_hatch(monkeypatch):
    assert allowed(who(platform=True), "admin")
    monkeypatch.setenv("BILLING_ENFORCE_ROLES", "false")
    assert allowed(who(), "admin")


def test_rbac_failure_fails_closed(monkeypatch):
    ctx = AuthContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["admin"])   # token claims admin, rbac not loaded
    monkeypatch.setenv("AUTH_ENFORCE_RBAC", "true")

    def boom(*a, **k):
        raise RuntimeError("db down")
    import services.common.db as db
    monkeypatch.setattr(db, "session_scope", boom)
    assert not allowed(ctx, "admin")


def test_require_tier_dependency_raises_403():
    dep = access.require_tier("admin")
    with pytest.raises(HTTPException) as e:
        asyncio.run(dep(who("billing_clerk")))
    assert e.value.status_code == 403
    assert asyncio.run(dep(who("owner"))).roles == ["owner"]
    with pytest.raises(ValueError):
        access.require_tier("nope")


def request_with(headers):
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


def test_internal_key_compare(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "s3cret-key")
    assert access.internal_key_ok(request_with({"x-internal-key": "s3cret-key"}))
    assert not access.internal_key_ok(request_with({"x-internal-key": "wrong"}))
    assert not access.internal_key_ok(request_with({}))
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "")
    assert not access.internal_key_ok(request_with({"x-internal-key": ""}))     # unset key never matches


def test_dunning_process_is_internal_key_only(monkeypatch):
    from services.billing.routes import finance_outbox
    called = []

    async def fake(tenant_id=None, **k):
        called.append(tenant_id)
        return {"processed": 0}
    monkeypatch.setattr(finance_outbox.dunning, "process_pending_dunning", fake)
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k")
    with pytest.raises(HTTPException) as e:                          # an admin identity is NOT enough
        asyncio.run(finance_outbox.run_dunning(request_with({"x-user-id": str(uuid.uuid4())})))
    assert e.value.status_code == 403 and called == []
    assert asyncio.run(finance_outbox.run_dunning(request_with({"x-internal-key": "k"}))) == {"processed": 0}
    assert called == [None]                                          # every tenant, only with the key
    ctx = who("owner")
    asyncio.run(finance_outbox.run_dunning_for_tenant(ctx))
    assert called[-1] == ctx.tenant_id                               # admin variant is tenant-scoped


def test_outbox_retry_needs_internal_key_or_admin(monkeypatch):
    from services.billing.routes import finance_outbox
    monkeypatch.setenv("INTERNAL_SERVICE_KEY", "k")
    seen = []

    async def fake_deliver(tenant_id=None, **k):
        seen.append(tenant_id)
        return {"attempted": 0, "sent": 0, "failed": 0}
    monkeypatch.setattr(finance_outbox.fp, "deliver", fake_deliver)
    assert asyncio.run(finance_outbox.retry_finance_outbox(request_with({"x-internal-key": "k"}))) and seen == [None]

    ctx_admin, ctx_clerk = who("billing_admin"), who("billing_clerk")

    async def get_ctx_factory(ctx):
        async def g(request):
            return ctx
        return g
    for ctx, ok in ((ctx_admin, True), (ctx_clerk, False)):
        async def g(request, ctx=ctx):
            return ctx
        monkeypatch.setattr(finance_outbox, "get_auth_context", g)
        if ok:
            asyncio.run(finance_outbox.retry_finance_outbox(request_with({})))
            assert seen[-1] == ctx.tenant_id
        else:
            with pytest.raises(HTTPException) as e:
                asyncio.run(finance_outbox.retry_finance_outbox(request_with({})))
            assert e.value.status_code == 403


# ── which routes carry which gate ───────────────────────────────────────────

EXPECTED = {
    ("POST", "/invoices/generate"): "admin", ("POST", "/invoices/{invoice_id}/credit-note"): "admin",
    ("POST", "/invoices/{invoice_id}/void"): "admin", ("POST", "/invoices/{invoice_id}/send"): "clerk",
    ("GET", "/invoices"): "reader", ("GET", "/invoices/{invoice_id}"): "reader",
    ("POST", "/payments"): "clerk", ("GET", "/payments"): "reader",
    ("POST", "/payments/paystack/initialize"): "admin", ("POST", "/payments/paystack/plans/{plan_id}/sync"): "admin",
    ("POST", "/payments/paystack/subscriptions"): "admin",
    ("POST", "/collections/{customer_id}/suspend"): "admin", ("POST", "/collections/{customer_id}/reinstate"): "admin",
    ("POST", "/collections/{customer_id}/arrange"): "admin", ("GET", "/collections/queue"): "reader",
    ("POST", "/plans"): "admin", ("POST", "/bundles"): "admin", ("GET", "/plans"): "reader",
    ("POST", "/subscriptions"): "admin", ("POST", "/subscriptions/{subscription_id}/cancel"): "admin",
    ("POST", "/subscriptions/{subscription_id}/generate-invoice"): "admin",
    ("GET", "/reports/revenue"): "reader", ("GET", "/reports/aging"): "reader", ("GET", "/reports/collections"): "reader",
    ("POST", "/dunning/process-tenant"): "admin", ("GET", "/billing/finance-outbox"): "admin",
}


def all_routes(app):
    out = []
    for r in app.routes:
        inner = getattr(getattr(r, "original_router", None), "routes", None)
        out.extend(inner if inner is not None else [r])
    return out


def test_routes_carry_the_expected_gates():
    from services.billing.main import app
    found = {}
    for route in all_routes(app):
        for method in getattr(route, "methods", None) or ():
            names = [getattr(d.dependency, "__name__", "") for d in getattr(route, "dependencies", [])]
            tiers = [n.replace("require_billing_", "") for n in names if n.startswith("require_billing_")]
            found[(method, route.path)] = tiers[0] if tiers else None
    missing = {k: (v, found.get(k)) for k, v in EXPECTED.items() if found.get(k) != v}
    assert not missing


def test_every_post_is_gated_or_deliberately_public():
    from services.billing.main import app
    # "/delivery/webhook-event" checks the internal key itself; "/public/" routes are share-token + per-IP rate limited
    public = {"/payments/paystack/webhook", "/dunning/process", "/billing/finance-outbox/retry", "/delivery/webhook-event"}
    seats = "/billing/seats"          # seats.py keeps its own operator / billing-reader checks
    ungated = []
    for route in all_routes(app):
        if "POST" in (getattr(route, "methods", None) or ()) and route.path not in public and not route.path.startswith(seats) \
                and not route.path.startswith("/public/"):
            if not any(getattr(d.dependency, "__name__", "").startswith("require_billing_") for d in route.dependencies):
                ungated.append(route.path)
    assert ungated == []
