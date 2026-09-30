"""WebSocket auth: signed identity from the web tier is the only accepted source in
AUTH_MODE=signed. Run with cwd = services/communication:  python -m pytest tests -q
"""

import os
import sys
import time
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import internal_auth  # noqa: E402
from services.communication.routes.ws import authenticate_ws  # noqa: E402

SECRET = "s" * 48
PATH = "/api/v1/ws"


def _signed(user, tenant, path=PATH, method="GET", secret=SECRET):
    ts = int(time.time())
    sig = internal_auth.compute_signature(
        secret, method=method, path=path, ts=ts, user_id=user, tenant_id=tenant,
        roles="", permissions="", modules="", org_id="",
    )
    return {
        "x-user-id": user,
        "x-tenant-id": tenant,
        internal_auth.TS_HEADER.lower(): str(ts),
        internal_auth.SIG_HEADER.lower(): sig,
    }


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "signed")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", SECRET)


def test_signed_identity_accepted():
    u, t = str(uuid.uuid4()), str(uuid.uuid4())
    assert authenticate_ws(_signed(u, t), PATH, None) == (uuid.UUID(t), uuid.UUID(u))


def test_forged_tenant_rejected():
    u, t = str(uuid.uuid4()), str(uuid.uuid4())
    h = _signed(u, t)
    h["x-tenant-id"] = str(uuid.uuid4())
    with pytest.raises(ValueError):
        authenticate_ws(h, PATH, None)


def test_unsigned_headers_and_token_rejected():
    with pytest.raises(ValueError):
        authenticate_ws({"x-user-id": str(uuid.uuid4()), "x-tenant-id": str(uuid.uuid4())}, PATH, "anything")


def test_wrong_path_rejected():
    u, t = str(uuid.uuid4()), str(uuid.uuid4())
    with pytest.raises(ValueError):
        authenticate_ws(_signed(u, t, path="/api/v1/other"), PATH, None)
