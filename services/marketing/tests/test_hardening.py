"""Marketing hardening tests: Zernio webhook fail-closed/dedupe, tenant-scoped counters, suppression
helper, send path (filter + caps), unsubscribe tokens, role gates, campaign transitions, SMS.

The DB and providers are faked. Run from repo root:
    python -m pytest services/marketing/tests/test_hardening.py -q
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from services.common import suppression  # noqa: E402
from services.common.auth import AuthContext, get_auth_context  # noqa: E402
from services.marketing import main as mk  # noqa: E402
from services.marketing import security as sec  # noqa: E402

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")


# ───────────────────────────── fakes ─────────────────────────────

class Res:
    def __init__(self, rowcount=1, first=("draft",), rows=None):
        self.rowcount = rowcount
        self._first = first
        self._rows = rows or []

    def first(self):
        return self._first

    def all(self):
        return self._rows

    def mappings(self):
        return SimpleNamespace(first=lambda: None, all=lambda: [])


class FakeConn:
    def __init__(self, log, first=("draft",), dup_ids=None):
        self.log = log
        self._first = first
        self.dup_ids = dup_ids if dup_ids is not None else set()

    def execute(self, stmt, params=None):
        q = str(stmt)
        self.log.append((q, params))
        if "INSERT INTO marketing_webhook_events" in q:
            key = (params["p"], params["e"])
            if key in self.dup_ids:
                return Res(rowcount=0)
            self.dup_ids.add(key)
            return Res(rowcount=1)
        return Res(first=self._first)

    @contextmanager
    def begin_nested(self):
        yield


def fake_engine(log, first=("draft",), seen=None):
    seen = seen if seen is not None else set()

    class Engine:
        @contextmanager
        def begin(self):
            yield FakeConn(log, first, seen)

        connect = begin

    return Engine()


def auth(roles=(), perms=(), platform_admin=False):
    return AuthContext(user_id=uuid.uuid4(), tenant_id=TENANT, roles=list(roles), permissions=list(perms),
                       is_platform_admin=platform_admin, rbac_loaded=True)


@pytest.fixture
def env(monkeypatch):
    for k in ("ZERNIO_WEBHOOK_SECRET", "ZERNIO_WEBHOOK_ALLOW_UNSIGNED", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EMAIL_UNSUBSCRIBE_SECRET", "unit-test-unsubscribe-secret-0123456789")
    monkeypatch.setenv("EMAIL_UNSUBSCRIBE_BASE_URL", "https://app.test/svc/marketing")
    monkeypatch.setattr(mk.guard, "is_licensed", lambda: True)
    monkeypatch.setattr(mk.guard, "enforce_modules", False)
    monkeypatch.setattr(mk, "_ensure_marketing_tables", lambda e: None)
    monkeypatch.setattr(sec, "_email_limiter", None)
    monkeypatch.setattr(sec, "_sms_limiter", None)
    return monkeypatch


@pytest.fixture
def client(env):
    log = []
    eng = fake_engine(log)
    env.setattr(mk, "get_engine", lambda: eng)
    c = TestClient(mk.app)
    yield c, log
    mk.app.dependency_overrides.clear()


def act_as(roles=(), perms=(), platform_admin=False):
    ctx = auth(roles, perms, platform_admin)
    mk.app.dependency_overrides[get_auth_context] = lambda: ctx
    return ctx


# ───────────────────── C1: Zernio webhook ─────────────────────

def zsign(body, secret="whsec-test"):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


EVENT = json.dumps({"event": "message.received", "id": "evt-1", "message": {"platform": "instagram"}}).encode()


@pytest.fixture
def zernio(client, env):
    c, log = client
    calls = []

    async def fake_process(payload, header_tenant, event_type, platform):
        calls.append(event_type)
        return {"status": "received"}

    env.setattr(mk, "_process_zernio_event", fake_process)
    return c, log, calls


def test_zernio_unset_secret_fails_closed(zernio):
    c, log, calls = zernio
    r = c.post("/social/webhooks/zernio/inbound", content=EVENT, headers={"X-Zernio-Signature": zsign(EVENT)})
    assert r.status_code == 503
    assert calls == []  # ChatEngine path never reached
    assert log == []


def test_zernio_allow_unsigned_is_explicit_opt_out(zernio, env):
    c, log, calls = zernio
    env.setenv("ZERNIO_WEBHOOK_ALLOW_UNSIGNED", "true")
    r = c.post("/social/webhooks/zernio/inbound", content=EVENT)
    assert r.status_code == 200 and calls == ["message.received"]


def test_zernio_bad_signature_rejected_before_processing(zernio, env):
    c, log, calls = zernio
    env.setenv("ZERNIO_WEBHOOK_SECRET", "whsec-test")
    assert c.post("/social/webhooks/zernio/inbound", content=EVENT).status_code == 401
    assert c.post("/social/webhooks/zernio/inbound", content=EVENT,
                  headers={"X-Zernio-Signature": zsign(EVENT, "wrong")}).status_code == 401
    assert calls == []


def test_zernio_duplicate_event_has_no_side_effects(zernio, env):
    c, log, calls = zernio
    env.setenv("ZERNIO_WEBHOOK_SECRET", "whsec-test")
    h = {"X-Zernio-Signature": zsign(EVENT), "X-Zernio-Event-Id": "evt-dup"}
    assert c.post("/social/webhooks/zernio/inbound", content=EVENT, headers=h).json()["status"] == "received"
    second = c.post("/social/webhooks/zernio/inbound", content=EVENT, headers=h)
    assert second.status_code == 200 and second.json() == {"status": "duplicate"}
    assert calls == ["message.received"]  # processed once


def test_zernio_body_cap(zernio, env):
    c, log, calls = zernio
    env.setenv("ZERNIO_WEBHOOK_SECRET", "whsec-test")
    big = b"x" * (sec.WEBHOOK_MAX_BODY + 1)
    assert c.post("/social/webhooks/zernio/inbound", content=big,
                  headers={"X-Zernio-Signature": zsign(big)}).status_code == 413


def test_bound_payload_truncates_huge_events():
    small = {"a": 1}
    assert sec.bound_payload(small) == small
    huge = {"blob": "y" * (sec.STORED_PAYLOAD_MAX + 10)}
    out = sec.bound_payload(huge, "message.received")
    assert out["truncated"] is True and "blob" not in out


# ───────────────────── H5: tenant-scoped counter update ─────────────────────

def test_finalize_batch_updates_are_tenant_scoped_and_failures_not_bounces():
    log = []
    conn = FakeConn(log)
    cid = str(uuid.uuid4())
    status = mk._finalize_email_batch(conn, TENANT, uuid.uuid4(), cid, sent=2, failed=1)
    assert status == "partial"
    sql = [q for q, _ in log]
    assert len(sql) == 2
    for q, params in log:
        assert "tenant_id = :tid" in q and params["tid"] == str(TENANT)
    assert "total_failed" in sql[0] and "total_bounced" not in sql[0]
    assert "UPDATE marketing_campaigns" in sql[1]


def test_finalize_batch_without_campaign_skips_campaign_update():
    log = []
    assert mk._finalize_email_batch(FakeConn(log), TENANT, uuid.uuid4(), None, 0, 3) == "failed"
    assert len(log) == 1


def test_no_unscoped_update_delete_by_id_left_in_source():
    src = open(mk.__file__, encoding="utf-8").read()
    import re
    for m in re.finditer(r"(UPDATE marketing_\w+ SET[^\"]*?WHERE[^\"]*|DELETE FROM marketing_\w+ WHERE[^\"]*)", src, re.S):
        stmt = m.group(1)
        if "tenant_id" in stmt or "{where}" in stmt:  # {where} is 'id = :cid AND tenant_id = :tid'
            continue
        # allowed exceptions: rows already resolved inside the same tenant-scoped transaction
        assert "FROM marketing_email_batches" in stmt or "marketing_email_batches" in stmt or "SET {field}" in stmt, stmt[:120]


# ───────────────────── C3: suppression helper ─────────────────────

class FakeAsyncSession:
    def __init__(self, suppressed=(), fail=False):
        self.suppressed = {s.lower() for s in suppressed}
        self.fail = fail
        self.params = []

    @asynccontextmanager
    async def begin_nested(self):
        yield

    async def execute(self, stmt, params=None):
        if self.fail:
            raise RuntimeError('relation "marketing_suppressions" does not exist')
        self.params.append(params)
        hit = [(e,) for e in params["emails"] if e in self.suppressed]
        return SimpleNamespace(all=lambda: hit, rowcount=1)


def test_filter_suppressed_case_insensitive_and_dedupes():
    s = FakeAsyncSession(suppressed=["Bad@Example.com"])
    allowed, blocked = asyncio.run(suppression.filter_suppressed(
        s, TENANT, ["  BAD@example.COM ", "ok@x.co", "OK@x.co", "Name <Other@X.co>"]))
    assert blocked == ["bad@example.com"]
    assert allowed == ["ok@x.co", "other@x.co"]
    assert s.params[0]["tid"] == str(TENANT)  # tenant-scoped query


def test_is_suppressed():
    s = FakeAsyncSession(suppressed=["a@b.co"])
    assert asyncio.run(suppression.is_suppressed(s, TENANT, "A@B.co")) is True
    assert asyncio.run(suppression.is_suppressed(s, TENANT, "z@b.co")) is False
    assert asyncio.run(suppression.is_suppressed(s, TENANT, "")) is False


def test_suppression_safe_when_table_missing():
    s = FakeAsyncSession(fail=True)
    allowed, blocked = asyncio.run(suppression.filter_suppressed(s, TENANT, ["a@b.co", "c@d.co"]))
    assert allowed == ["a@b.co", "c@d.co"] and blocked == []
    assert asyncio.run(suppression.is_suppressed(s, TENANT, "a@b.co")) is False


def test_add_suppression_rejects_unknown_reason():
    with pytest.raises(ValueError):
        asyncio.run(suppression.add_suppression(FakeAsyncSession(), TENANT, "a@b.co", "spam", "x"))


def test_sync_filter_safe_when_table_missing():
    class Boom(FakeConn):
        def execute(self, stmt, params=None):
            raise RuntimeError("no table")

    allowed, blocked = suppression.filter_suppressed_sync(Boom([]), TENANT, ["A@b.co"])
    assert allowed == ["a@b.co"] and blocked == []


# ───────────────────── C3: send path ─────────────────────

@pytest.fixture
def send_env(client, env):
    c, log = client
    scheduled = []
    env.setattr(mk, "_email_provider_configured", lambda tid=None: True)
    env.setattr(suppression, "filter_suppressed_sync",
                lambda conn, tid, emails: ([e for e in emails if e != "blocked@x.co"],
                                           [e for e in emails if e == "blocked@x.co"]))

    def grab(coro):
        scheduled.append(coro)
        coro.close()

    env.setattr(mk, "schedule_background", grab)
    act_as(roles=["manager"])
    return c, log, scheduled


def send_body(recips):
    return {"subject": "Hi", "body_html": "<p>x</p>", "recipients": recips}


def test_send_filters_suppressed_dedupes_validates_and_returns_202(send_env):
    c, log, scheduled = send_env
    r = c.post("/email/send", json=send_body(["A@x.co", "a@x.co", "blocked@x.co", "not-an-email"]))
    assert r.status_code == 202
    body = r.json()
    assert (body["total_queued"], body["total_suppressed"], body["total_invalid"]) == (1, 1, 1)
    assert body["status"] == "sending" and len(scheduled) == 1
    insert = next(p for q, p in log if "INSERT INTO marketing_email_batches" in q)
    assert insert["tq"] == 1 and insert["ts"] == 1


def test_send_all_suppressed_sends_nothing(send_env):
    c, log, scheduled = send_env
    r = c.post("/email/send", json=send_body(["blocked@x.co"]))
    assert r.status_code == 202 and r.json()["total_queued"] == 0 and scheduled == []


def test_send_caps_recipients(send_env, env):
    c, log, scheduled = send_env
    env.setenv("EMAIL_MAX_RECIPIENTS", "3")
    r = c.post("/email/send", json=send_body([f"u{i}@x.co" for i in range(4)]))
    assert r.status_code == 413 and scheduled == []


def test_send_blocked_without_unsubscribe_secret(send_env, env):
    c, log, scheduled = send_env
    env.delenv("EMAIL_UNSUBSCRIBE_SECRET")
    assert c.post("/email/send", json=send_body(["a@x.co"])).status_code == 503


def test_send_rate_limited_per_tenant(send_env, env):
    c, log, scheduled = send_env
    env.setenv("EMAIL_RATE_PER_MIN", "2")
    codes = [c.post("/email/send", json=send_body(["a@x.co"])).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_send_requires_write_role(send_env):
    c, log, scheduled = send_env
    act_as(roles=["org_user"])
    assert c.post("/email/send", json=send_body(["a@x.co"])).status_code == 403


def test_background_batch_adds_unsubscribe_and_counts_failures_separately(env):
    log = []
    env.setattr(mk, "get_engine", lambda: fake_engine(log))
    sent_args = []

    async def fake_send(**kw):
        sent_args.append(kw)
        if kw["to_email"] == "fail@x.co":
            raise RuntimeError("provider down")
        return "<msg-1>"

    env.setattr(mk, "_send_one_email", fake_send)
    env.setattr(mk, "_record_email_event", lambda *a, **k: None)
    asyncio.run(mk._run_email_batch(
        tenant_id=TENANT, batch_id=uuid.uuid4(), cid=None, recipients=["ok@x.co", "fail@x.co"],
        subject="s", body_html="<p>b</p>", from_name=None, from_email=None, reply_to=None))
    ok = sent_args[0]
    assert "Unsubscribe" in ok["body_html"] and "List-Unsubscribe" in ok["headers"]
    assert ok["headers"]["List-Unsubscribe"].startswith("<https://app.test/svc/marketing/email/unsubscribe?t=")
    final = [p for q, p in log if "UPDATE marketing_email_batches" in q][0]
    assert (final["sent"], final["failed"], final["st"]) == (1, 1, "partial")


# ───────────────────── C3: unsubscribe tokens / endpoint ─────────────────────

def test_token_roundtrip(env):
    t = sec.sign_unsubscribe_token(TENANT, "User@Example.com")
    assert sec.verify_unsubscribe_token(t) == (TENANT, "user@example.com")


def test_token_tamper_expiry_and_garbage(env):
    t = sec.sign_unsubscribe_token(TENANT, "a@b.co")
    body, sig = t.split(".")
    forged = sec.sign_unsubscribe_token(OTHER, "a@b.co").split(".")[0] + "." + sig
    for bad in (forged, body + "." + sig[:-2] + "AA", "garbage", "", t + "x"):
        with pytest.raises(sec.BadUnsubscribeToken):
            sec.verify_unsubscribe_token(bad)
    expired = sec.sign_unsubscribe_token(TENANT, "a@b.co", ttl=10, now=time.time() - 100)
    with pytest.raises(sec.BadUnsubscribeToken):
        sec.verify_unsubscribe_token(expired)


def test_token_fails_closed_without_secret(env):
    env.delenv("EMAIL_UNSUBSCRIBE_SECRET")
    with pytest.raises(sec.UnsubscribeNotConfigured):
        sec.sign_unsubscribe_token(TENANT, "a@b.co")


def test_unsubscribe_get_confirms_post_applies(client, env):
    c, log = client
    added = []
    env.setattr(suppression, "add_suppression_sync", lambda conn, tid, email, reason, source: added.append((tid, email, reason)))
    t = sec.sign_unsubscribe_token(TENANT, "Who@X.co")
    g = c.get(f"/email/unsubscribe?t={t}")
    assert g.status_code == 200 and "Confirm unsubscribe" in g.text and added == []  # prefetch is harmless
    p = c.post(f"/email/unsubscribe?t={t}", content=b"List-Unsubscribe=One-Click")
    assert p.status_code == 200 and added == [(TENANT, "who@x.co", "unsubscribe")]
    bad = c.post("/email/unsubscribe?t=nope")
    assert "invalid" in bad.text.lower() and len(added) == 1


# ───────────────────── H4: role dependencies ─────────────────────

def test_role_dependencies():
    run = asyncio.run
    assert run(sec.require_marketing_write(auth(roles=["manager"]))) is not None
    assert run(sec.require_marketing_write(auth(perms=["marketing.write"]))) is not None
    assert run(sec.require_marketing_write(auth(perms=["marketing.*"]))) is not None
    assert run(sec.require_marketing_admin(auth(roles=["org_admin"]))) is not None
    assert run(sec.require_marketing_write(auth(platform_admin=True))) is not None
    for dep, a in ((sec.require_marketing_write, auth(roles=["org_user"])),
                   (sec.require_marketing_write, auth(perms=["marketing.read"])),
                   (sec.require_marketing_admin, auth(roles=["manager"])),
                   (sec.require_marketing_admin, auth(perms=["marketing.write"]))):
        with pytest.raises(Exception) as ei:
            run(dep(a))
        assert getattr(ei.value, "status_code", None) == 403


def test_routes_enforce_roles(client):
    c, log = client
    act_as(roles=["org_user"])
    assert c.post("/campaigns", json={"name": "n", "channel": "email"}).status_code == 403
    assert c.post("/email/suppressions", json={"email": "a@b.co"}).status_code == 403
    assert c.put("/social/analytics/profile", json={"zernio_profile_id": "p"}).status_code == 403
    assert c.post("/social/profile/offboard").status_code == 403
    assert c.post("/social/api-keys", json={"name": "k"}).status_code == 403
    act_as(roles=["manager"])
    assert c.post("/email/suppressions", json={"email": "a@b.co"}).status_code == 403  # admin only
    assert c.post("/social/profile/offboard").status_code == 403
    assert c.post("/campaigns", json={"name": "n", "channel": "bogus"}).status_code == 422  # passed the gate
    act_as(roles=["org_admin"])
    assert c.post("/email/suppressions", json={"email": "a@b.co"}).status_code == 201


def test_every_mutating_route_is_gated_or_public_by_design():
    public = {"/email/webhook", "/email/unsubscribe", "/social/webhooks/zernio/inbound"}
    gate_names = {"require_marketing_write", "require_marketing_admin"}
    ungated = []
    for route in mk.app.routes:
        methods = getattr(route, "methods", None) or set()
        if not methods & {"POST", "PUT", "PATCH", "DELETE"} or route.path in public:
            continue
        dep_calls = {d.call.__name__ for d in route.dependant.dependencies if getattr(d, "call", None)}
        if not dep_calls & gate_names and route.endpoint.__name__ not in {"send_sms_message"}:
            ungated.append((sorted(methods), route.path))
    assert ungated == []


# ───────────────────── M10: campaign status transitions ─────────────────────

def test_transition_map():
    assert sec.transition_allowed("draft", "scheduled")
    assert sec.transition_allowed("scheduled", "sending")
    assert sec.transition_allowed("sending", "sent")
    assert sec.transition_allowed("scheduled", "paused") and sec.transition_allowed("paused", "sending")
    assert sec.transition_allowed("draft", "cancelled")
    assert not sec.transition_allowed("sent", "draft")
    assert not sec.transition_allowed("draft", "sent")
    assert not sec.transition_allowed("cancelled", "sending")


def test_patch_campaign_rejects_bad_status_and_transition(client, env):
    c, log = client
    act_as(roles=["manager"])
    cid = uuid.uuid4()
    assert c.patch(f"/campaigns/{cid}", json={"status": "bogus"}).status_code == 422
    assert c.patch(f"/campaigns/{cid}", json={"channel": "telepathy"}).status_code == 422
    env.setattr(mk, "get_engine", lambda: fake_engine(log, first=("sent",)))
    assert c.patch(f"/campaigns/{cid}", json={"status": "draft"}).status_code == 409


def test_schedule_normalises_timezones(client):
    assert mk._to_utc(mk.datetime(2030, 1, 1, 12, 0)).tzinfo is not None
    aware = mk.datetime(2030, 1, 1, 14, 0, tzinfo=mk.timezone(mk.timedelta(hours=2)))
    assert mk._to_utc(aware).hour == 12


# ───────────────────── H7: SMS never mock-succeeds ─────────────────────

SMS = {"sender_id": "OmniDome", "to": "+27821234567", "message": "hi"}


def test_sms_unconfigured_is_501_not_mock_success(client):
    c, log = client
    act_as(roles=["manager"])
    r = c.post("/sms/send", json=SMS)
    assert r.status_code == 501 and "twilio-mock" not in r.text
    act_as(platform_admin=True)
    assert c.post("/sms/send", json=SMS).status_code == 501  # still no Twilio creds


def test_sms_platform_creds_not_usable_by_tenants(client, env):
    c, log = client
    env.setenv("TWILIO_ACCOUNT_SID", "ACxxxxxxxx")
    env.setenv("TWILIO_AUTH_TOKEN", "tok")
    act_as(roles=["admin"])
    assert c.post("/sms/send", json=SMS).status_code == 501


def test_sms_validates_e164_and_reports_provider_failure(client, env):
    c, log = client
    env.setenv("TWILIO_ACCOUNT_SID", "ACxxxxxxxx")
    env.setenv("TWILIO_AUTH_TOKEN", "tok")
    act_as(platform_admin=True)
    assert c.post("/sms/send", json={**SMS, "to": "0821234567"}).status_code == 422

    class FakeHttp:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return SimpleNamespace(status_code=400, text="bad", json=lambda: {})

    env.setattr(mk.httpx, "AsyncClient", FakeHttp)
    r = c.post("/sms/send", json=SMS)
    assert r.status_code == 502 and '"sent"' not in r.text


def test_journey_trigger_is_501(client):
    c, log = client
    act_as(roles=["manager"])
    r = c.post(f"/email/journeys/{uuid.uuid4()}/trigger", json={})
    assert r.status_code == 501 and "enrolled" not in r.text.lower()


def test_fresh_tenant_whatsapp_endpoints_are_empty_not_seeded(client):
    c, log = client
    act_as(roles=["manager"])
    for k in (mk._WHATSAPP_SENDERS, mk._WHATSAPP_TEMPLATES, mk._WHATSAPP_FLOWS,
              mk._WHATSAPP_GROUPS, mk._WHATSAPP_CONVERSIONS):
        k.pop(str(TENANT), None)
    for path in ("senders", "templates", "flows", "groups", "conversions"):
        r = c.get(f"/whatsapp/{path}")
        assert r.status_code == 200 and r.json() == [], (path, r.text)
    # a created asset is the only thing a tenant ever sees
    r = c.post("/whatsapp/templates", json={"name": "My Tpl", "body": "hello"})
    assert r.status_code == 201
    names = [x["name"] for x in c.get("/whatsapp/templates").json()]
    assert names == ["my_tpl"]
    assert "sandbox" not in c.get("/whatsapp/senders").text.lower()
    mk._WHATSAPP_TEMPLATES.pop(str(TENANT), None)


def test_whatsapp_number_provisioning_is_not_faked(client):
    c, log = client
    act_as(roles=["admin", "manager"])
    r = c.post("/whatsapp/senders/connect", json={"mode": "get_number"})
    assert r.status_code == 501


def test_journeys_have_no_invented_stats(client):
    c, log = client
    act_as(roles=["manager"])
    mk._EMAIL_JOURNEYS.pop(str(TENANT), None)
    r = c.get("/email/journeys")
    assert r.status_code == 200 and r.json() == []
    assert not hasattr(mk, "_default_journeys")
    mk._EMAIL_JOURNEYS[str(TENANT)] = [{"id": "j1", "name": "Mine", "total_enrolled": 5, "total_completed": 2, "steps": []}]
    j = c.get("/email/journeys").json()[0]
    assert j["enrollment_tracked"] is False and j["total_enrolled"] is None and j["total_completed"] is None
    mk._EMAIL_JOURNEYS.pop(str(TENANT), None)


# ───────────────────── H6 / M12: profile + upstream errors ─────────────────────

def test_no_platform_profile_fallback(env):
    env.setenv("ZERNIO_PROFILE_ID", "platform-profile")
    env.setattr(mk, "get_engine", lambda: fake_engine([], first=None))
    assert mk._get_tenant_profile(TENANT) is None
    with pytest.raises(Exception) as ei:
        mk._require_tenant_profile(TENANT)
    assert ei.value.status_code == 409


def test_upstream_error_hides_raw_exception():
    exc = mk._upstream_error("ctx", RuntimeError("secret upstream detail key=abc"))
    assert exc.status_code == 502 and "secret" not in exc.detail and "ref " in exc.detail
