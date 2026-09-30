"""Verifier tests for signed internal identity (services/common/internal_auth.py).

TEST_VECTOR is duplicated in apps/web/lib/internal-identity.test.mjs - keep in sync.
"""
import pytest

from services.common import internal_auth as ia

SECRET = "test-secret-0123456789abcdef0123456789abcdef"
NOW = 1760000000
FIELDS = dict(
    method="POST",
    path="/customers/list",
    ts=NOW,
    user_id="11111111-2222-3333-4444-555555555555",
    tenant_id="AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
    roles="org_admin, crm_user,org_admin",
    permissions="crm.write,crm.read",
    modules="crm,billing",
    org_id="",
)
VECTOR_SIG = "3cd5503774bc86f8754ac1d8aa1bac567b65573495c787cda266c38bd36f6a9e"
VECTOR_CANONICAL = (
    "v1\nPOST\n/customers/list\n1760000000\n11111111-2222-3333-4444-555555555555\n"
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\ncrm_user,org_admin\ncrm.read,crm.write\nbilling,crm\n"
)


def _headers(**over):
    h = {
        "x-user-id": FIELDS["user_id"],
        "x-tenant-id": FIELDS["tenant_id"],
        "x-roles": FIELDS["roles"],
        "x-permissions": FIELDS["permissions"],
        "x-modules": FIELDS["modules"],
    }
    h.update(ia.sign_headers(h, "POST", "/customers/list", SECRET, now=NOW))
    h.update(over)
    return h


def verify(h, method="POST", path="/customers/list", now=NOW, secret=SECRET):
    ia.verify_request(h, method, path, secret, now=now)


def reason(h, **kw):
    with pytest.raises(ia.IdentityError) as ei:
        verify(h, **kw)
    return ei.value.reason


def test_vector_canonical_and_signature():
    assert ia.canonical_string(**FIELDS) == VECTOR_CANONICAL
    assert ia.compute_signature(SECRET, **FIELDS) == VECTOR_SIG


def test_valid():
    verify(_headers())


def test_valid_case_insensitive_mapping():
    from starlette.datastructures import Headers
    verify(Headers({k.title(): v for k, v in _headers().items()}))


@pytest.mark.parametrize("hdr,val", [
    ("x-user-id", "99999999-2222-3333-4444-555555555555"),
    ("x-tenant-id", "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"),
    ("x-roles", "platform_admin"),
    ("x-permissions", "platform.admin"),
    ("x-modules", "crm,billing,hr"),
    ("x-org-id", "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"),
])
def test_tampered_field(hdr, val):
    assert reason(_headers(**{hdr: val})) == "bad_signature"


def test_removed_field_is_tampering():
    h = _headers()
    del h["x-roles"]
    assert reason(h) == "bad_signature"


def test_wrong_path_and_method():
    assert reason(_headers(), path="/customers/delete") == "bad_signature"
    assert reason(_headers(), method="GET") == "bad_signature"


def test_replay_same_request_within_window_allowed():
    h = _headers()
    verify(h, now=NOW + 5)
    verify(h, now=NOW + 5)


def test_cross_path_replay_rejected():
    assert reason(_headers(), path="/admin/users", now=NOW + 5) == "bad_signature"


@pytest.mark.parametrize("now", [NOW + 61, NOW - 61, NOW + 10_000])
def test_stale_or_future_timestamp(now):
    assert reason(_headers(), now=now) == "timestamp_out_of_window"


def test_window_edges_ok():
    verify(_headers(), now=NOW + 60)
    verify(_headers(), now=NOW - 60)


def test_missing_headers():
    h = _headers()
    del h["x-identity-sig"]
    assert reason(h) == "missing_signature"
    h = _headers()
    del h["x-identity-ts"]
    assert reason(h) == "missing_signature"
    assert reason({"x-user-id": FIELDS["user_id"], "x-tenant-id": FIELDS["tenant_id"]}) == "missing_signature"


def test_malformed():
    assert reason(_headers(**{"x-identity-sig": "zz"})) == "malformed_signature"
    assert reason(_headers(**{"x-identity-ts": "abc"})) == "malformed_signature"


def test_ts_tampered():
    assert reason(_headers(**{"x-identity-ts": str(NOW + 1)})) == "bad_signature"


def test_wrong_secret():
    assert reason(_headers(), secret="x" * 40) == "bad_signature"


@pytest.mark.parametrize("secret", ["", "short"])
def test_empty_or_short_secret_fails_closed(secret):
    assert reason(_headers(), secret=secret) == "secret_unset"


def test_get_secret_fail_closed(monkeypatch):
    monkeypatch.delenv("INTERNAL_AUTH_SECRET", raising=False)
    with pytest.raises(ia.IdentityConfigError):
        ia.get_secret()
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "short")
    with pytest.raises(ia.IdentityConfigError):
        ia.get_secret()
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", SECRET)
    assert ia.get_secret() == SECRET


def test_get_auth_context_signed_mode(monkeypatch):
    """End-to-end through the FastAPI dependency: 401 unsigned, 503 without secret, 200 signed."""
    pytest.importorskip("jwt")
    pytest.importorskip("fastapi")
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    from services.common.auth import AuthContext, get_auth_context

    app = FastAPI()

    @app.get("/who")
    async def who(ctx: AuthContext = Depends(get_auth_context)):
        return {"tenant": str(ctx.tenant_id), "roles": ctx.roles}

    monkeypatch.setenv("AUTH_MODE", "signed")
    monkeypatch.setenv("AUTH_ALLOW_ANONYMOUS", "true")
    monkeypatch.setenv("DEFAULT_USER_ID", FIELDS["user_id"])
    monkeypatch.setenv("DEFAULT_TENANT_ID", FIELDS["tenant_id"])
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", SECRET)
    c = TestClient(app)
    forged = {"x-user-id": FIELDS["user_id"], "x-tenant-id": FIELDS["tenant_id"], "x-roles": "platform_admin"}
    # (httpx, which TestClient uses, is patched to sign identity headers when no signature is
    # present, so "unsigned" here means a bogus signature; the live tests use curl for truly unsigned.)
    bogus = dict(forged, **{"x-identity-ts": str(int(__import__("time").time())), "x-identity-sig": "0" * 64})
    assert c.get("/who", headers=bogus).status_code == 401
    assert c.get("/who").status_code == 401  # anonymous shortcut is ignored in signed mode
    signed = dict(forged, **ia.sign_headers(forged, "GET", "/who", SECRET))
    assert c.get("/who", headers=signed).status_code == 200
    assert c.get("/who", headers=dict(signed, **{"x-roles": "x"})).status_code == 401
    monkeypatch.delenv("INTERNAL_AUTH_SECRET")
    assert c.get("/who", headers=signed).status_code == 503
