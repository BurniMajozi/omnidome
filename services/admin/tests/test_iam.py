"""Admin IAM against a real Postgres (TEST_DATABASE_URL, database name must end in _test).

Seat limits, pending invites, revoke/expiry, last-owner and rank guardrails, tenant scope,
audit-in-transaction, the accept race and Supabase reconcile. Supabase is replaced by an
in-memory fake; nothing here talks to the network.

    TEST_DATABASE_URL=postgresql://…/coreconnect_test  (schema: config/master_schema.sql)
    python -m pytest services/admin/tests -q
"""
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common import testdb  # noqa: E402

testdb.use_test_database()
os.environ["ADMIN_SYNC_RETRY"] = "false"
os.environ["LICENSE_ENFORCEMENT"] = "warn"
os.environ["INTERNAL_SERVICE_KEY"] = "test-internal-key"
os.environ["APP_PUBLIC_URL"] = "http://app.test"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from services.admin import iam, supabase_sync  # noqa: E402
from services.admin import main as admin_main  # noqa: E402

PLATFORM_USER = uuid.uuid4()  # not a row in users: platform admins need not exist there


# --------------------------------------------------------------------------- fakes


class FakeSupabase:
    def __init__(self):
        self.users = {}  # id -> {"id","email","app_metadata"}
        self.deleted = []
        self.invited = []

    def add(self, email, app_metadata=None, uid=None):
        uid = str(uid or uuid.uuid4())
        self.users[uid] = {"id": uid, "email": email, "app_metadata": dict(app_metadata or {})}
        return uid

    async def list_users(self):
        return [dict(u) for u in self.users.values()]

    async def find_by_email(self, email):
        return next((dict(u) for u in self.users.values() if u["email"].lower() == email.lower()), None)

    async def get_user(self, uid):
        if uid not in self.users:
            raise supabase_sync.SupabaseError(404, "not found")
        return dict(self.users[uid])

    async def set_app_metadata(self, uid, meta, banned=None):
        if uid not in self.users:
            raise supabase_sync.SupabaseError(404, "not found")
        self.users[uid]["banned"] = banned
        merged = {**self.users[uid]["app_metadata"], **meta}
        self.users[uid]["app_metadata"] = {k: v for k, v in merged.items() if v is not None}
        return dict(self.users[uid])

    async def revoke_sessions(self, uid):
        return False  # real GoTrue has no admin session revocation

    async def set_email(self, uid, email):
        if uid not in self.users:
            raise supabase_sync.SupabaseError(404, "not found")
        self.users[uid]["email"] = email
        return dict(self.users[uid])

    async def invite(self, email, redirect_to):
        self.invited.append((email, redirect_to))
        return {"id": self.add(email)}

    async def delete_user(self, uid):
        self.deleted.append(uid)
        self.users.pop(uid, None)


@pytest.fixture(scope="module")
def sb():
    fake = FakeSupabase()
    mp = pytest.MonkeyPatch()
    mp.setattr(supabase_sync, "get_client", lambda: fake)

    async def verify(token):  # token format: "tok|<supabase-id>|<email>"
        _, uid, email = token.split("|", 2)
        return {"id": uid, "email": email, "name": None}

    mp.setattr(iam, "verify_bearer", verify)
    yield fake
    mp.undo()


@pytest.fixture(scope="module")
def client(sb):
    for limiter in (admin_main._global_rate_limiter, admin_main._auth_rate_limiter, iam.invite_limiter, iam.accept_limiter):
        limiter.max_requests = 10**9
    with TestClient(app=admin_main.app, raise_server_exceptions=False) as c:
        yield c
    testdb.reset_engines()


# --------------------------------------------------------------------------- helpers


def q(sql, **p):
    with testdb.sync_engine().begin() as conn:
        res = conn.execute(text(sql), p)
        return res.fetchall() if res.returns_rows else []


def platform(tenant=None):
    return {"X-Tenant-Id": str(tenant or uuid.uuid4()), "X-User-Id": str(PLATFORM_USER), "X-Roles": "platform_admin"}


def as_user(tenant, user):
    return {"X-Tenant-Id": str(tenant), "X-User-Id": str(user)}


def make_tenant(client, seat_limit=3):
    name = f"t-{uuid.uuid4().hex[:8]}"
    r = client.post("/tenants", json={"name": name, "domain": f"{name}.test", "seat_limit": seat_limit}, headers=platform())
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


def add_user(tenant, roles=(), active=True, email=None):
    uid = uuid.uuid4()
    email = email or f"u-{uid.hex[:10]}@example.test"
    q(
        "INSERT INTO users (id, tenant_id, email, hashed_password, is_active, is_owner) VALUES (:i,:t,:e,'x',:a,:o)",
        i=uid, t=tenant, e=email, a=active, o="owner" in roles,
    )
    for r in roles:
        q(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) SELECT :u, id, :t FROM roles WHERE tenant_id=:t AND name=:n",
            u=uid, t=tenant, n=r,
        )
    if active:
        q("INSERT INTO seat_events (tenant_id, user_id, delta, reason) VALUES (:t,:u,1,'test_setup')", t=tenant, u=uid)
    return uid, email


def seats(client, tenant):
    r = client.get(f"/tenants/{tenant}/seats", headers=platform(tenant))
    assert r.status_code == 200, r.text
    return r.json()


def invite(client, tenant, email, roles=None, headers=None):
    return client.post(
        f"/tenants/{tenant}/invites",
        json={"email": email, "roles": roles or ["org_user"], "send_email": False},
        headers=headers or platform(tenant),
    )


def token_of(resp):
    return resp.json()["accept_link"].split("token=")[1]


def bearer(uid, email):
    return {"Authorization": f"Bearer tok|{uid}|{email}"}


def fresh_email():
    return f"inv-{uuid.uuid4().hex[:10]}@example.test"


# --------------------------------------------------------------------------- seats


def test_seat_limit_returns_409_with_counts(client):
    t = make_tenant(client, seat_limit=2)
    for i in range(2):
        r = client.post("/users", json={"email": fresh_email(), "password": "Passw0rd!x"}, headers=platform(t))
        assert r.status_code == 201, r.text
    r = client.post("/users", json={"email": fresh_email(), "password": "Passw0rd!x"}, headers=platform(t))
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["error"] == "seat_limit_reached" and d["seats_used"] == 2 and d["seat_limit"] == 2


def test_pending_invites_count_and_revoke_frees(client):
    t = make_tenant(client, seat_limit=2)
    add_user(t)
    a = invite(client, t, fresh_email())
    assert a.status_code == 201, a.text
    assert seats(client, t)["seats_used"] == 2 and seats(client, t)["pending_invites"] == 1
    assert invite(client, t, fresh_email()).status_code == 409  # pending invite holds the last seat
    assert client.delete(f"/invites/{a.json()['invite_id']}", headers=platform(t)).status_code == 200
    assert seats(client, t)["seats_used"] == 1
    assert invite(client, t, fresh_email()).status_code == 201
    ledger = [(e["delta"], e["reason"]) for e in seats(client, t)["events"]]
    assert (1, "invite_created") in ledger and (-1, "invite_revoked") in ledger


def test_expired_invite_frees_seat_and_records_event(client):
    t = make_tenant(client, seat_limit=1)
    r = invite(client, t, fresh_email())
    assert r.status_code == 201
    q("UPDATE invites SET expires_at = now() - interval '1 minute' WHERE id = :i", i=r.json()["invite_id"])
    s = seats(client, t)
    assert s["pending_invites"] == 0 and s["seats_used"] == 0
    assert [e["reason"] for e in s["events"] if e["delta"] == -1] == ["invite_expired"]
    assert sum(e["delta"] for e in s["events"]) == s["current_seats"]  # ledger == seats_used
    assert invite(client, t, fresh_email()).status_code == 201


def test_seat_endpoints_permissions_and_internal_key(client):
    t = make_tenant(client, seat_limit=5)
    admin, _ = add_user(t, ["org_admin"])
    other = make_tenant(client)
    assert client.put(f"/tenants/{t}/seats", json={"seat_limit": 9}, headers=as_user(t, admin)).status_code == 403
    assert client.put(f"/tenants/{t}/seats", json={"seat_limit": 9, "seat_price": "99.50"}, headers=platform(t)).status_code == 200
    assert client.get(f"/tenants/{t}/seats", headers=as_user(t, admin)).json()["seat_limit"] == 9
    assert client.get(f"/tenants/{other}/seats", headers=as_user(t, admin)).status_code == 403
    usage = client.get("/platform/seat-usage", headers=platform())
    assert usage.status_code == 200 and any(x["tenant_id"] == str(t) for x in usage.json()["tenants"])
    assert client.get("/platform/seat-usage", headers=as_user(t, admin)).status_code == 403
    # billing reads with only the shared key
    k = {"x-internal-key": "test-internal-key"}
    snap = client.get(f"/tenants/{t}/seats", headers=k)
    assert snap.status_code == 200 and "current_seats" in snap.json() and "events" in snap.json()
    assert client.get(f"/tenants/{t}/seats", headers={"x-internal-key": "wrong"}).status_code == 401
    # cannot shrink below use
    add_user(t)
    add_user(t)
    assert client.put(f"/tenants/{t}/seats", json={"seat_limit": 1}, headers=platform(t)).status_code == 409


# --------------------------------------------------------------------------- guardrails


def test_last_owner_and_last_admin_refused(client):
    t = make_tenant(client)
    owner, _ = add_user(t, ["owner", "org_admin"])
    admin, _ = add_user(t, ["org_admin"])
    p = platform(t)
    r = client.post(f"/tenants/{t}/members/{owner}/deactivate", headers=p)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "last_owner"
    r = client.put(f"/tenants/{t}/members/{owner}/roles", json={"roles": ["org_admin"]}, headers=p)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "last_owner"
    # legacy endpoints share the same guard
    r = client.delete(f"/users/{owner}", headers=p)
    assert r.status_code == 409
    # transfer ownership, then the old owner can go
    assert client.post(f"/tenants/{t}/transfer-ownership", json={"new_owner_user_id": str(admin)}, headers=p).status_code == 200
    assert client.post(f"/tenants/{t}/members/{owner}/deactivate", headers=p).status_code == 200
    # admin is now the only owner AND admin: cannot deactivate themselves
    r = client.post(f"/tenants/{t}/members/{admin}/deactivate", headers=as_user(t, admin))
    assert r.status_code == 409 and r.json()["detail"]["error"] in ("last_owner", "last_admin")


def test_last_admin_self_removal_refused(client):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    r = client.post(f"/tenants/{t}/members/{admin}/deactivate", headers=as_user(t, admin))
    assert r.status_code == 409 and r.json()["detail"]["error"] == "last_admin"
    r = client.put(f"/tenants/{t}/members/{admin}/roles", json={"roles": ["org_user"]}, headers=as_user(t, admin))
    assert r.status_code == 409


def test_role_rank_guardrails(client):
    t = make_tenant(client)
    owner, _ = add_user(t, ["owner"])
    admin, _ = add_user(t, ["org_admin"])
    member, _ = add_user(t, ["org_user"])
    a = as_user(t, admin)
    # org_admin may grant up to its own rank ...
    assert client.put(f"/tenants/{t}/members/{member}/roles", json={"roles": ["manager"]}, headers=a).status_code == 200
    # ... but not owner, and never platform_admin
    assert client.put(f"/tenants/{t}/members/{member}/roles", json={"roles": ["owner"]}, headers=a).status_code == 403
    assert client.put(f"/tenants/{t}/members/{member}/roles", json={"roles": ["platform_admin"]}, headers=a).status_code == 403
    # cannot touch a higher-ranked user
    assert client.post(f"/tenants/{t}/members/{owner}/deactivate", headers=a).status_code == 403
    assert client.put(f"/tenants/{t}/members/{owner}/roles", json={"roles": ["org_user"]}, headers=a).status_code == 403
    # the owner can grant owner
    assert client.put(f"/tenants/{t}/members/{member}/roles", json={"roles": ["owner"]}, headers=as_user(t, owner)).status_code == 200
    # tenant admins cannot mint platform permissions through a custom role
    r = client.post("/roles", json={"name": "sneaky", "permissions": ["platform.admin"]}, headers=a)
    assert r.status_code == 403
    assert client.post("/roles", json={"name": "owner"}, headers=a).status_code == 409


def test_tenant_scope_refusal(client):
    t1, t2 = make_tenant(client), make_tenant(client)
    a1, _ = add_user(t1, ["org_admin"])
    h = as_user(t1, a1)
    for method, path, body in [
        ("get", f"/tenants/{t2}/members", None),
        ("get", f"/tenants/{t2}/invites", None),
        ("post", f"/tenants/{t2}/invites", {"email": fresh_email(), "roles": ["org_user"]}),
        ("post", f"/tenants/{t2}/transfer-ownership", {"new_owner_user_id": str(uuid.uuid4())}),
    ]:
        r = getattr(client, method)(path, headers=h, **({"json": body} if body else {}))
        assert r.status_code == 403, (path, r.status_code)
    inv = invite(client, t2, fresh_email())
    assert client.delete(f"/invites/{inv.json()['invite_id']}", headers=h).status_code == 403
    assert invite(client, t1, fresh_email(), headers=h).status_code == 201  # own tenant is fine
    # a non-admin cannot use the tenant endpoints at all
    member, _ = add_user(t1, ["org_user"])
    assert client.get(f"/tenants/{t1}/members", headers=as_user(t1, member)).status_code == 403


# --------------------------------------------------------------------------- audit


def test_audit_written_in_same_transaction(client, monkeypatch):
    t = make_tenant(client, seat_limit=5)
    email = fresh_email()
    assert invite(client, t, email).status_code == 201
    rows = q("SELECT action, metadata->>'email' FROM audit_logs WHERE tenant_id=:t AND action='invite.create'", t=t)
    assert rows and rows[0][1] == email

    # if the audit insert fails, the change must not survive and the request must fail
    async def boom(*a, **k):
        raise RuntimeError("audit down")

    monkeypatch.setattr(iam, "write_audit", boom)
    victim = fresh_email()
    r = invite(client, t, victim)
    assert r.status_code == 500
    assert q("SELECT count(*) FROM invites WHERE lower(email)=:e", e=victim)[0][0] == 0
    n = seats(client, t)
    assert n["pending_invites"] == 1


# --------------------------------------------------------------------------- invites: accept


def test_accept_invite_end_to_end(client, sb):
    t = make_tenant(client, seat_limit=3)
    owner, _ = add_user(t, ["owner", "org_admin"])
    email = fresh_email()
    sid = sb.add(email)
    r = invite(client, t, email, ["manager"], headers=as_user(t, owner))
    assert r.status_code == 201
    assert r.json()["accept_link"].startswith("http://app.test/auth/accept?token=")
    tok = token_of(r)
    # only a hash is stored
    assert q("SELECT count(*) FROM invites WHERE token_hash=:h", h=tok)[0][0] == 0
    # someone else's identity cannot redeem it
    wrong = client.post("/invites/accept", json={"token": tok}, headers=bearer(uuid.uuid4(), "mallory@example.test"))
    assert wrong.status_code == 403
    assert client.post("/invites/accept", json={"token": tok}).status_code == 401
    ok = client.post("/invites/accept", json={"token": tok}, headers=bearer(sid, email))
    assert ok.status_code == 200, ok.text
    assert ok.json()["roles"] == ["manager"]
    s = seats(client, t)
    assert s["active_users"] == 2 and s["pending_invites"] == 0 and s["seats_used"] == 2
    assert sum(e["delta"] for e in s["events"]) == s["current_seats"]
    assert sb.users[sid]["app_metadata"]["tenant_id"] == str(t) and sb.users[sid]["app_metadata"]["roles"] == ["manager"]
    assert client.post("/invites/accept", json={"token": tok}, headers=bearer(sid, email)).json()["status"] == "already_accepted"
    assert q("SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action='invite.accept'", t=t)[0][0] == 1
    # one tenant per email
    assert invite(client, make_tenant(client), email).status_code == 409


def test_accept_race_at_limit_has_exactly_one_winner(client, sb):
    t = make_tenant(client, seat_limit=4)
    for _ in range(3):
        add_user(t)
    # over-reserved on purpose (e.g. limit lowered / admin filled seats): two pending invites, one seat
    people = []
    for _ in range(2):
        email = fresh_email()
        sid = sb.add(email)
        tok = uuid.uuid4().hex + uuid.uuid4().hex
        q(
            "INSERT INTO invites (tenant_id,email,role_names,token_hash,status,expires_at) "
            "VALUES (:t,:e,ARRAY['org_user'],:h,'pending',now()+interval '1 day')",
            t=t, e=email, h=iam.hash_token(tok),
        )
        people.append((tok, sid, email))

    def go(p):
        tok, sid, email = p
        return client.post("/invites/accept", json={"token": tok}, headers=bearer(sid, email)).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(go, people))
    assert codes == [200, 409], codes
    assert q("SELECT count(*) FROM users WHERE tenant_id=:t AND is_active", t=t)[0][0] == 4


def test_resend_rotates_token_and_expired_needs_seat(client):
    t = make_tenant(client, seat_limit=1)
    r = invite(client, t, fresh_email())
    old = token_of(r)
    again = client.post(f"/invites/{r.json()['invite_id']}/resend?send_email=false", headers=platform(t))
    assert again.status_code == 200 and token_of(again) != old
    assert q("SELECT count(*) FROM invites WHERE token_hash=:h", h=iam.hash_token(old))[0][0] == 0
    # let it expire, another invite takes the seat, then reviving it must fail
    q("UPDATE invites SET expires_at = now() - interval '1 second' WHERE id=:i", i=r.json()["invite_id"])
    assert invite(client, t, fresh_email()).status_code == 201
    assert client.post(f"/invites/{r.json()['invite_id']}/resend?send_email=false", headers=platform(t)).status_code == 409


def test_deactivate_frees_seat_and_reactivate_rechecks(client):
    t = make_tenant(client, seat_limit=2)
    admin, _ = add_user(t, ["org_admin"])
    m, _ = add_user(t)
    p = platform(t)
    assert client.post(f"/tenants/{t}/members/{m}/deactivate", headers=p).status_code == 200
    assert seats(client, t)["seats_used"] == 1
    assert (-1, "user_deactivated") in [(e["delta"], e["reason"]) for e in seats(client, t)["events"]]
    assert invite(client, t, fresh_email()).status_code == 201  # takes the freed seat
    r = client.post(f"/tenants/{t}/members/{m}/reactivate", headers=p)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "seat_limit_reached"


def test_owner_email_on_tenant_create_and_by_email_lookup(client, sb):
    email = fresh_email()
    name = f"t-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/tenants",
        json={"name": name, "domain": f"{name}.test", "seat_limit": 2, "owner_email": email, "send_owner_invite_email": False},
        headers=platform(),
    )
    assert r.status_code == 201, r.text
    t = uuid.UUID(r.json()["id"])
    assert r.json()["owner_invite"]["accept_link"]
    sid = sb.add(email)
    assert client.post("/invites/accept", json={"token": token_of_link(r.json()["owner_invite"])}, headers=bearer(sid, email)).status_code == 200
    look = client.get("/internal/users/by-email", params={"email": email}, headers={"x-internal-key": "test-internal-key"})
    body = look.json()
    assert look.status_code == 200 and body["is_active"] is True and "owner" in body["roles"] and body["tenant_id"] == str(t)
    assert client.get("/internal/users/by-email", params={"email": email}).status_code == 401
    # deactivated users are still reported (the proxy turns is_active=false into 403)
    other, _ = add_user(t, ["org_admin"])
    assert client.post(f"/tenants/{t}/members/{sid}/deactivate", headers=platform(t)).status_code == 409  # last owner
    assert client.post(f"/tenants/{t}/members/{sid}/deactivate", headers=as_user(t, other)).status_code == 403  # outranked
    assert seats(client, t)["seat_limit"] == 2


def token_of_link(d):
    return d["accept_link"].split("token=")[1]


# --------------------------------------------------------------------------- supabase sync


def test_reconcile_detects_and_fixes_drift(client, sb):
    t = make_tenant(client)
    uid, email = add_user(t, ["org_admin"])
    sid = sb.add(email, {"tenant_id": str(uuid.uuid4()), "roles": ["platform_admin"]}, uid=uid)
    orphan = sb.add(fresh_email(), {"tenant_id": str(t), "roles": ["org_user"]})

    dry = client.post("/admin/sync/reconcile", headers=platform(t))
    assert dry.status_code == 200 and dry.json()["dry_run"] is True
    drift = [d for d in dry.json()["drift"] if d["email"] == email]
    assert drift and drift[0]["fixed"] is False
    assert drift[0]["supabase"]["roles"] == ["platform_admin"] and drift[0]["db"]["roles"] == ["org_admin", "platform_admin"]
    assert sb.users[sid]["app_metadata"]["roles"] == ["platform_admin"]  # dry run touched nothing
    assert any(o["supabase_id"] == orphan for o in dry.json()["orphans_in_supabase_only"])
    assert client.post("/admin/sync/reconcile", headers=as_user(t, uid)).status_code == 403

    fixed = client.post("/admin/sync/reconcile?apply=true", headers=platform(t))
    assert fixed.status_code == 200
    assert [d["fixed"] for d in fixed.json()["drift"] if d["email"] == email] == [True]
    assert sb.users[sid]["app_metadata"]["tenant_id"] == str(t) and sb.users[sid]["app_metadata"]["roles"] == ["org_admin", "platform_admin"]  # never stripped
    assert sb.users[orphan]["app_metadata"]["tenant_id"] == str(t)  # orphans untouched unless adopt_orphans
    assert q("SELECT supabase_synced FROM users WHERE id=:u", u=uid)[0][0] is True
    again = client.post("/admin/sync/reconcile", headers=platform(t)).json()
    assert not [d for d in again["drift"] if d["email"] == email]


def test_role_change_syncs_supabase_and_deactivation_clears_metadata(client, sb, monkeypatch):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    email = fresh_email()
    m, _ = add_user(t, ["org_user"], email=email)
    sid = sb.add(email, uid=m)
    r = client.put(f"/tenants/{t}/members/{m}/roles", json={"roles": ["manager"]}, headers=as_user(t, admin))
    assert r.status_code == 200
    assert sb.users[sid]["app_metadata"]["roles"] == ["manager"]
    assert client.post(f"/tenants/{t}/members/{m}/deactivate", headers=as_user(t, admin)).status_code == 200
    meta = sb.users[sid]["app_metadata"]
    assert meta.get("tenant_id") is None and meta["roles"] == [] and meta["is_active"] is False
    assert sb.users[sid]["banned"] is True
    # a sync failure is recorded, not lost
    async def fail(uid, meta, banned=None):
        raise supabase_sync.SupabaseError(500, "down")

    monkeypatch.setattr(sb, "set_app_metadata", fail)
    assert client.post(f"/tenants/{t}/members/{m}/reactivate", headers=as_user(t, admin)).status_code == 200
    row = q("SELECT supabase_synced, supabase_sync_error FROM users WHERE id=:u", u=m)[0]
    assert row[0] is False and "down" in row[1]


# --------------------------------------------------------------------------- security hardening


def test_tenant_admin_cannot_enable_modules_platform_admin_can(client):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    owner, _ = add_user(t, ["owner"])
    key = q("SELECT key FROM modules ORDER BY key LIMIT 1")[0][0]
    body = {"modules": [{"name": key, "enabled": True}]}
    for uid in (admin, owner):
        assert client.put(f"/tenants/{t}/modules", json=body, headers=as_user(t, uid)).status_code == 403
    assert client.get(f"/tenants/{t}/modules", headers=as_user(t, admin)).status_code == 200  # read stays open
    r = client.put(f"/tenants/{t}/modules", json=body, headers=platform(t))
    assert r.status_code == 200, r.text
    assert q("SELECT tm.status FROM tenant_modules tm JOIN modules m ON m.id = tm.module_id WHERE tm.tenant_id=:t AND m.key=:k", t=t, k=key)[0][0] == "ENABLED"


def test_audit_logs_are_append_only(client):
    t = make_tenant(client)
    q("INSERT INTO audit_logs (tenant_id, action, resource_type) VALUES (:t, 'test.append', 'test')", t=t)  # INSERT still works
    with pytest.raises(Exception, match="append-only"):
        q("UPDATE audit_logs SET action = 'tampered' WHERE tenant_id = :t", t=t)
    with pytest.raises(Exception, match="append-only"):
        q("DELETE FROM audit_logs WHERE tenant_id = :t", t=t)
    assert q("SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action='test.append'", t=t)[0][0] == 1


def test_email_unique_case_insensitively(client):
    t = make_tenant(client)
    email = f"Case-{uuid.uuid4().hex[:8]}@Example.test"
    add_user(t, ["org_user"], email=email.lower())
    with pytest.raises(Exception, match="users_email_lower_key|duplicate key"):
        q("INSERT INTO users (id, tenant_id, email, hashed_password) VALUES (:i,:t,:e,'x')", i=uuid.uuid4(), t=t, e=email.upper())
    look = client.get("/internal/users/by-email", params={"email": email.upper()}, headers={"x-internal-key": "test-internal-key"})
    assert look.status_code == 200


def test_migration_skips_unique_email_index_when_duplicates_exist(client):
    import asyncio

    from services.admin import migrations

    # the index exists (applied at startup); dropping it, adding a case-variant duplicate, and
    # re-running must warn and skip, never fail or delete rows
    t = make_tenant(client)
    e = f"dup-{uuid.uuid4().hex[:8]}@example.test"
    q("DROP INDEX IF EXISTS users_email_lower_key")
    try:
        add_user(t, ["org_user"], email=e)
        q("INSERT INTO users (id, tenant_id, email, hashed_password) VALUES (:i,:t,:e,'x')", i=uuid.uuid4(), t=t, e=e.upper())

        async def go():
            from sqlalchemy.ext.asyncio import create_async_engine

            from services.common.db import _async_database_url

            eng = create_async_engine(_async_database_url())
            try:
                async with eng.begin() as conn:
                    return await migrations.ensure_unique_lower_email(conn)
            finally:
                await eng.dispose()

        assert asyncio.run(go()) is False
        assert q("SELECT count(*) FROM users WHERE lower(email)=:e", e=e)[0][0] == 2
    finally:
        q("DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE lower(email)=:e)", e=e)
        q("DELETE FROM users WHERE lower(email)=:e", e=e)
        q("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (lower(email))")


def test_invite_409_is_generic_for_tenant_admins(client):
    t1, t2 = make_tenant(client), make_tenant(client)
    admin, _ = add_user(t1, ["org_admin"])
    _, taken_email = add_user(t2, ["org_user"])
    pending_email = fresh_email()
    assert invite(client, t2, pending_email).status_code == 201
    h = as_user(t1, admin)
    a = invite(client, t1, taken_email, headers=h)
    b = invite(client, t1, pending_email, headers=h)
    fresh = invite(client, t1, fresh_email(), headers=h)
    assert fresh.status_code == 201
    assert a.status_code == b.status_code == 409
    assert a.json()["detail"] == b.json()["detail"]
    assert "belongs" not in a.json()["detail"] and "pending" not in b.json()["detail"]
    # platform admins keep the detail; a tenant may still learn about its OWN pending invite
    assert "belongs" in invite(client, t1, taken_email).json()["detail"]
    own = fresh_email()
    assert invite(client, t1, own, headers=h).status_code == 201
    assert "pending" in invite(client, t1, own, headers=h).json()["detail"]


# ── verify_bearer: an unconfirmed Supabase address proves nothing ──────────
_REAL_VERIFY_BEARER = iam.verify_bearer  # captured at import, before the `sb` fixture swaps it out


def _fake_supabase_user(monkeypatch, user):
    class _Client:
        async def verify_token(self, _token):
            return user

    monkeypatch.setattr(supabase_sync, "get_client", lambda: _Client())


def test_verify_bearer_rejects_unconfirmed_email(monkeypatch):
    import asyncio

    from fastapi import HTTPException

    _fake_supabase_user(monkeypatch, {"id": str(uuid.uuid4()), "email": "a@b.test", "email_confirmed_at": None, "confirmed_at": None})
    with pytest.raises(HTTPException) as e:
        asyncio.run(_REAL_VERIFY_BEARER("tok"))
    assert e.value.status_code == 401


def test_verify_bearer_accepts_confirmed_email(monkeypatch):
    import asyncio

    _fake_supabase_user(monkeypatch, {"id": str(uuid.uuid4()), "email": "a@b.test", "email_confirmed_at": "2026-01-01T00:00:00Z"})
    assert asyncio.run(_REAL_VERIFY_BEARER("tok"))["email"] == "a@b.test"
