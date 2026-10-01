"""DB-backed tests for the independent-review hardening (H2, M3-M8, M9, lows).

Same harness as test_iam.py (TEST_DATABASE_URL, fake Supabase); skipped without a test database.
"""
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_iam import (  # noqa: E402,F401  (fixtures + helpers; importing test_iam skips this module without a DB)
    FakeSupabase,
    add_user,
    admin_main,
    as_user,
    bearer,
    client,
    fresh_email,
    iam,
    invite,
    make_tenant,
    platform,
    q,
    sb,
    seats,
    supabase_sync,
)


def role_id(tenant, name):
    return q("SELECT id FROM roles WHERE tenant_id=:t AND name=:n", t=tenant, n=name)[0][0]


def held_permission_keys(tenant, role="org_admin"):
    return [
        r[0]
        for r in q(
            "SELECT p.key FROM role_permissions rp JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id "
            "WHERE r.tenant_id=:t AND r.name=:n",
            t=tenant, n=role,
        )
    ]


def test_platform_admin_preserved_across_role_change_and_deactivate(client, sb):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    email = fresh_email()
    m, _ = add_user(t, ["org_user"], email=email)
    sid = sb.add(email, {"roles": ["platform_admin"]}, uid=m)
    r = client.put(f"/tenants/{t}/members/{m}/roles", json={"roles": ["manager"]}, headers=as_user(t, admin))
    assert r.status_code == 200, r.text
    assert sb.users[sid]["app_metadata"]["roles"] == ["manager", "platform_admin"]
    assert r.json()["supabase_sync"]["sessions_revoked"] is False  # no admin API: reported honestly
    assert client.post(f"/tenants/{t}/members/{m}/deactivate", headers=as_user(t, admin)).status_code == 200
    assert sb.users[sid]["app_metadata"]["roles"] == ["platform_admin"]  # never removed implicitly
    assert sb.users[sid]["banned"] is True


def test_platform_admin_endpoints(client, monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(supabase_sync, "get_client", lambda: fake)
    first = fake.add(fresh_email(), {"roles": ["platform_admin", "org_user"]})
    second = fake.add(fresh_email(), {"roles": ["org_user"]})
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    assert client.put(f"/platform/admins/{second}", headers=as_user(t, admin)).status_code == 403
    assert client.delete(f"/platform/admins/{first}", headers=as_user(t, admin)).status_code == 403
    # refuses to remove the last platform admin
    r = client.delete(f"/platform/admins/{first}", headers=platform(t))
    assert r.status_code == 409 and r.json()["detail"]["error"] == "last_platform_admin"
    assert client.put(f"/platform/admins/{second}", headers=platform(t)).json()["platform_admin"] is True
    assert fake.users[second]["app_metadata"]["roles"] == ["org_user", "platform_admin"]
    r = client.delete(f"/platform/admins/{first}", headers=platform(t))
    assert r.status_code == 200 and fake.users[first]["app_metadata"]["roles"] == ["org_user"]
    assert client.put(f"/platform/admins/{uuid.uuid4()}", headers=platform(t)).status_code == 404
    acts = [x[0] for x in q("SELECT action FROM audit_logs WHERE metadata->>'supabase_user_id' IN (:a,:b)", a=first, b=second)]
    assert "platform_admin.grant" in acts and "platform_admin.revoke" in acts


def test_system_roles_are_immutable(client):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    a = as_user(t, admin)
    for name in ("org_admin", "org_user", "owner", "manager", "hr_manager"):
        rid = role_id(t, name)
        assert client.put(f"/roles/{rid}", json={"permissions": []}, headers=a).status_code == 409, name
        assert client.delete(f"/roles/{rid}", headers=a).status_code == 409, name
    assert client.put(f"/roles/{role_id(t, 'org_user')}", json={"permissions": []}, headers=platform(t)).status_code == 409


def test_custom_role_permission_cap_rank_and_audit(client, sb):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    a = as_user(t, admin)
    assert client.post("/roles", json={"name": "x1", "permissions": ["org.admin"]}, headers=a).status_code == 403
    assert client.post("/roles", json={"name": "x2", "permissions": ["org.manage"]}, headers=a).status_code == 403
    assert client.post("/roles", json={"name": "x3", "permissions": ["*"]}, headers=a).status_code == 400
    assert client.post("/roles", json={"name": "x4", "permissions": ["crm.*"]}, headers=a).status_code == 400
    held = [k for k in held_permission_keys(t) if not k.startswith(("org.", "platform."))]
    unheld = [r[0] for r in q("SELECT key FROM permissions WHERE key NOT LIKE 'org.%' AND key NOT LIKE 'platform.%'") if r[0] not in held]
    if unheld:
        assert client.post("/roles", json={"name": "x5", "permissions": [unheld[0]]}, headers=a).status_code == 403
    r = client.post("/roles", json={"name": "custom-a", "permissions": held[:1]}, headers=a)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert tuple(q("SELECT role_rank, is_system FROM roles WHERE id=:r", r=rid)[0]) == (40, False)  # 80 - 10, capped at 40
    assert q("SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action='role.create' AND resource_id=:r", t=t, r=rid)[0][0] == 1
    assert client.put(f"/roles/{rid}", json={"permissions": []}, headers=a).status_code == 200
    assert q("SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action='role.update' AND resource_id=:r", t=t, r=rid)[0][0] == 1
    # delete: audit row, user_roles removed, affected users re-synced
    email = fresh_email()
    m, _ = add_user(t, ["org_user"], email=email)
    sid = sb.add(email, uid=m)
    assert client.post(f"/users/{m}/roles", json={"role_id": rid}, headers=a).status_code == 200
    assert "custom-a" in sb.users[sid]["app_metadata"]["roles"]
    d = client.delete(f"/roles/{rid}", headers=a)
    assert d.status_code == 200 and d.json()["affected_users"] == [str(m)]
    assert q("SELECT count(*) FROM user_roles WHERE role_id=:r", r=rid)[0][0] == 0
    assert "custom-a" not in sb.users[sid]["app_metadata"]["roles"]
    assert q("SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action='role.delete' AND resource_id=:r", t=t, r=rid)[0][0] == 1


def test_role_audit_failure_rolls_back_role(client, monkeypatch):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])

    async def boom(*a, **k):
        raise RuntimeError("audit down")

    monkeypatch.setattr(iam, "write_audit", boom)
    assert client.post("/roles", json={"name": "ghost", "permissions": []}, headers=as_user(t, admin)).status_code == 500
    assert q("SELECT count(*) FROM roles WHERE tenant_id=:t AND name='ghost'", t=t)[0][0] == 0


def test_create_user_for_tenant_admin_points_to_invites(client):
    t = make_tenant(client, seat_limit=5)
    admin, _ = add_user(t, ["org_admin"])
    r = client.post("/users", json={"email": fresh_email(), "password": "Passw0rd!x"}, headers=as_user(t, admin))
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["error"] == "use_invites" and d["invite_endpoint"] == f"/tenants/{t}/invites"
    # platform admin keeps break-glass creation (seat check applies) and cannot squat a pending invite
    pending = fresh_email()
    other = make_tenant(client)
    assert invite(client, other, pending).status_code == 201
    r = client.post("/users", json={"email": pending, "password": "Passw0rd!x"}, headers=platform(t))
    assert r.status_code == 409 and "pending" in r.json()["detail"]
    assert client.post("/users", json={"email": fresh_email(), "password": "Passw0rd!x"}, headers=platform(t)).status_code == 201


def test_update_user_rank_guard_and_email_change(client, sb):
    t = make_tenant(client, seat_limit=5)
    owner, _ = add_user(t, ["owner"])
    admin, _ = add_user(t, ["org_admin"])
    email = fresh_email()
    member, _ = add_user(t, ["org_user"], email=email)
    sid = sb.add(email, uid=member)
    a = as_user(t, admin)
    assert client.put(f"/users/{owner}", json={"name": "Renamed"}, headers=a).status_code == 403  # outranked
    assert client.put(f"/users/{member}", json={"name": "Fine"}, headers=a).status_code == 200
    assert client.put(f"/users/{member}", json={"email": fresh_email()}, headers=a).status_code == 403  # platform only
    new_email = fresh_email()
    r = client.put(f"/users/{member}", json={"email": new_email}, headers=platform(t))
    assert r.status_code == 200, r.text
    assert sb.users[sid]["email"] == new_email
    assert q("SELECT email FROM users WHERE id=:u", u=member)[0][0] == new_email


def test_adopt_orphans_respects_seat_limit_and_refuses_platform_roles(client, sb):
    t = make_tenant(client, seat_limit=2)
    add_user(t)  # 1 of 2 seats used
    a_email, b_email = fresh_email(), fresh_email()
    a = sb.add(a_email, {"tenant_id": str(t), "roles": ["platform_admin", "org_user"]})
    b = sb.add(b_email, {"tenant_id": str(t), "roles": ["org_user"]})
    r = client.post("/admin/sync/reconcile?apply=true&adopt_orphans=true", headers=platform(t))
    assert r.status_code == 200, r.text
    body = r.json()
    adopted_here = [e for e in body["adopted"] if e in (a_email, b_email)]
    skipped_here = {x["email"]: x["reason"] for x in body["adopt_skipped"] if x["email"] in (a_email, b_email)}
    assert len(adopted_here) == 1 and list(skipped_here.values()) == ["seat_limit_reached"]
    assert seats(client, t)["seats_used"] == 2
    winner = a if a_email in adopted_here else b
    rows = q("SELECT r.name, r.scope FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.user_id=:u", u=winner)
    assert [tuple(x) for x in rows] == [("org_user", "TENANT")]  # platform_admin from metadata never enters the DB
    assert q("SELECT count(*) FROM audit_logs WHERE tenant_id=:t AND action='sync.adopt' AND resource_id=:u", t=t, u=winner)[0][0] == 1
    ev = seats(client, t)["events"]
    assert (1, "adopted") in [(e["delta"], e["reason"]) for e in ev]
    assert sum(e["delta"] for e in ev) == seats(client, t)["current_seats"]


def test_invite_resend_revoke_need_rank(client):
    t = make_tenant(client, seat_limit=6)
    owner, _ = add_user(t, ["owner"])
    admin, _ = add_user(t, ["org_admin"])
    high = invite(client, t, fresh_email(), ["owner"], headers=as_user(t, owner)).json()["invite_id"]
    a = as_user(t, admin)
    assert client.post(f"/invites/{high}/resend?send_email=false", headers=a).status_code == 403
    assert client.delete(f"/invites/{high}", headers=a).status_code == 403
    low = invite(client, t, fresh_email(), ["manager"], headers=a).json()["invite_id"]
    assert client.post(f"/invites/{low}/resend?send_email=false", headers=a).status_code == 200
    assert client.delete(f"/invites/{low}", headers=a).status_code == 200
    assert client.delete(f"/invites/{high}", headers=as_user(t, owner)).status_code == 200


def test_reviving_expired_invite_with_pending_duplicate_is_409_not_500(client):
    t = make_tenant(client, seat_limit=5)
    email = fresh_email()
    old = invite(client, t, email).json()["invite_id"]
    q("UPDATE invites SET expires_at = now() - interval '1 minute' WHERE id=:i", i=old)
    assert invite(client, t, email).status_code == 201  # the lapsed one no longer blocks a new invite
    r = client.post(f"/invites/{old}/resend?send_email=false", headers=platform(t))
    assert r.status_code == 409, r.text


def test_reinvited_deactivated_user_gets_invite_roles_only(client, sb):
    t = make_tenant(client, seat_limit=4)
    add_user(t, ["owner", "org_admin"])
    email = fresh_email()
    old, _ = add_user(t, ["org_admin"], active=False, email=email)
    sb.add(email, uid=old)
    tok = uuid.uuid4().hex + uuid.uuid4().hex
    q(
        "INSERT INTO invites (tenant_id,email,role_names,token_hash,status,expires_at) "
        "VALUES (:t,:e,ARRAY['org_user'],:h,'pending',now()+interval '1 day')",
        t=t, e=email, h=iam.hash_token(tok),
    )
    r = client.post("/invites/accept", json={"token": tok}, headers=bearer(old, email))
    assert r.status_code == 200, r.text
    names = sorted(x[0] for x in q("SELECT r.name FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE ur.user_id=:u", u=old))
    assert names == ["org_user"]


def test_parallel_accept_across_tenants_never_500(client, sb):
    t1, t2 = make_tenant(client), make_tenant(client)
    email = fresh_email()
    sid = sb.add(email)
    toks = []
    for t in (t1, t2):
        tok = uuid.uuid4().hex + uuid.uuid4().hex
        q(
            "INSERT INTO invites (tenant_id,email,role_names,token_hash,status,expires_at) "
            "VALUES (:t,:e,ARRAY['org_user'],:h,'pending',now()+interval '1 day')",
            t=t, e=email, h=iam.hash_token(tok),
        )
        toks.append(tok)

    def go(tok):
        return client.post("/invites/accept", json={"token": tok}, headers=bearer(sid, email)).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(go, toks))
    assert codes == [200, 409], codes


def test_list_members_hides_raw_sync_error(client):
    t = make_tenant(client)
    admin, _ = add_user(t, ["org_admin"])
    m, _ = add_user(t)
    q("UPDATE users SET supabase_synced=false, supabase_sync_error='HTTPError https://secret.internal/token=abc' WHERE id=:u", u=m)
    rows = client.get(f"/tenants/{t}/members", headers=as_user(t, admin)).json()
    row = next(x for x in rows if x["id"] == str(m))
    assert row["sync_status"] == "error" and "supabase_sync_error" not in row
    assert "secret" not in str(rows)


def test_reactivate_refused_when_tenant_suspended(client):
    t = make_tenant(client, seat_limit=5)
    add_user(t, ["org_admin"])
    m, _ = add_user(t)
    assert client.post(f"/tenants/{t}/members/{m}/deactivate", headers=platform(t)).status_code == 200
    q("UPDATE tenants SET status='SUSPENDED' WHERE id=:t", t=t)
    assert client.post(f"/tenants/{t}/members/{m}/reactivate", headers=platform(t)).status_code == 409
    q("UPDATE tenants SET status='ACTIVE' WHERE id=:t", t=t)
    assert client.post(f"/tenants/{t}/members/{m}/reactivate", headers=platform(t)).status_code == 200


def test_seat_events_cannot_be_deleted_or_updated(client):
    t = make_tenant(client)
    add_user(t)
    with pytest.raises(Exception, match="append-only"):
        q("DELETE FROM seat_events WHERE tenant_id=:t", t=t)
    with pytest.raises(Exception, match="append-only"):
        q("UPDATE seat_events SET reason='x' WHERE tenant_id=:t", t=t)


def test_internal_lookup_is_not_rate_limited(client):
    k = {"x-internal-key": "test-internal-key"}
    limiter = admin_main._global_rate_limiter
    old = limiter.max_requests
    limiter.max_requests = 3
    limiter._requests.clear()
    try:
        codes = [client.get("/internal/users/by-email", params={"email": "nobody@example.test"}, headers=k).status_code for _ in range(10)]
        assert set(codes) == {404}  # never 429
        assert sum(client.get("/health").status_code == 429 for _ in range(6)) >= 1  # other routes are still limited
    finally:
        limiter.max_requests = old
        limiter._requests.clear()
