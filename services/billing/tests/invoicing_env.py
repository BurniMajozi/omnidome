"""Shared fixture plumbing for the invoicing-suite tests: bare FastAPI app on the in-memory SQLite harness,
header-selected roles, no CRM / mail / finance network calls."""
from __future__ import annotations

import importlib
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

from services.billing import models_invoicing  # noqa: E402,F401  (register tables before create_all)
from services.billing.tests.sqlite_harness import make_session_factory, patch_sessions  # noqa: E402
from services.common.auth import AuthContext, get_auth_context  # noqa: E402

TENANT = uuid.uuid4()
OTHER_TENANT = uuid.uuid4()
CUSTOMER = uuid.uuid4()
WHO = {
    "reader": (uuid.uuid4(), ["billing_viewer"]),
    "clerk": (uuid.uuid4(), ["billing_clerk"]),
    "admin": (uuid.uuid4(), ["billing_admin"]),
}
MODULES = ("services.billing.routes.invoice_documents", "services.billing.routes.quotes",
           "services.billing.routes.public_invoices", "services.billing.routes.movements",
           "services.billing.routes.customer_app", "services.billing.routes.delivery", "services.billing.delivery",
           "services.billing.routes.invoices")


def make_env(monkeypatch):
    get_session = make_session_factory()
    patch_sessions(monkeypatch, get_session)
    for name in MODULES:
        mod = importlib.import_module(name)
        if hasattr(mod, "get_session"):
            monkeypatch.setattr(mod, "get_session", get_session)

    from services.billing import doc_service as ds
    from services.billing.routes import public_invoices as pub

    async def no_snapshot(*_a, **_k):
        return {}
    monkeypatch.setattr(ds, "customer_snapshot", no_snapshot)
    monkeypatch.setattr(pub, "view_limiter", pub.RateLimiter(max_requests=1000, window_seconds=60))
    monkeypatch.setattr(pub, "action_limiter", pub.RateLimiter(max_requests=1000, window_seconds=60))
    monkeypatch.setattr(pub, "bad_tokens", pub.BadTokenThrottle())
    monkeypatch.setenv("BILLING_ENFORCE_ROLES", "true")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://app.example.test")

    from services.billing.routes.customer_app import router as customer_app
    from services.billing.routes.delivery import router as delivery_router
    from services.billing.routes.invoice_documents import router as docs
    from services.billing.routes.invoices import router as invoices
    from services.billing.routes.movements import router as movements
    from services.billing.routes.payments import router as payments
    from services.billing.routes.public_invoices import router as public
    from services.billing.routes.quotes import router as quotes

    app = FastAPI()
    for r in (invoices, payments, docs, quotes, public, delivery_router, movements, customer_app):
        app.include_router(r)

    async def fake_ctx(request: Request):
        uid, roles = WHO[request.headers.get("x-who", "admin")]
        tenant = uuid.UUID(request.headers["x-tenant"]) if "x-tenant" in request.headers else TENANT
        return AuthContext(user_id=uid, tenant_id=tenant, roles=roles, rbac_loaded=True)

    app.dependency_overrides[get_auth_context] = fake_ctx
    client = TestClient(app)
    client.get_session = get_session
    return client


def H(who="admin", tenant=None):
    h = {"x-who": who}
    if tenant:
        h["x-tenant"] = str(tenant)
    return h


def line(desc="Install", qty="1", price="100.00", **kw):
    return {"description": desc, "quantity": qty, "unit_price": price, **kw}


def new_invoice(client, who="clerk", lines=None, **kw):
    body = {"customer_id": str(CUSTOMER), "lines": lines or [line()], **kw}
    r = client.post("/invoices/manual", json=body, headers=H(who))
    assert r.status_code == 201, r.text
    return r.json()


def issue(client, invoice_id, who="clerk"):
    r = client.post(f"/invoices/{invoice_id}/send", json={"channel": "email"}, headers=H(who))
    assert r.status_code == 200, r.text
    return r.json()
