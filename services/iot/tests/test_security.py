"""IoT hardening: SSRF policy, token encryption, role tiers, route order, SSE fan-out, migration guards."""
import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from services.common.url_safety import UnsafeUrl  # noqa: E402
from services.iot import access, ha_client  # noqa: E402
from services.iot.database import rebuild_decision  # noqa: E402
from services.iot.url_policy import validate_ha_url  # noqa: E402

PUBLIC = lambda host, port: ["93.184.216.34"]  # noqa: E731


def _res(ip):
    return lambda host, port: [ip]


# --------------------------------------------------------------------------- URL policy

@pytest.mark.parametrize("url", [
    "https://ha.example.com",
    "https://ha.example.com/",
    "https://ha.example.com:8123",
])
def test_public_https_ok(url):
    assert validate_ha_url(url, resolver=PUBLIC, allow_http=False, allow_private=False) == url.rstrip("/")


@pytest.mark.parametrize("url", [
    "http://ha.example.com",                    # http off by default
    "https://user:pw@ha.example.com",           # userinfo
    "https://ha.example.com:6379",              # odd port
    "https://ha.example.com?x=1",               # query
    "https://localhost",
    "https://db",                               # docker service name (single label)
    "https://admin",
    "https://crm:8001",
    "https://metadata.google.internal",
    "https://127.0.0.1",
    "https://169.254.169.254",
    "https://[::1]",
    "https://2130706433",                       # decimal loopback
    "https://0x7f.1",
    "https://192.168.1.10",                     # private blocked by default
    "https://10.0.0.5",
    "https://homeassistant.local",              # LAN name needs the flag
    "ftp://ha.example.com",
    "https://ha.example.com\\@evil",
])
def test_blocked_by_default(url):
    with pytest.raises(UnsafeUrl):
        validate_ha_url(url, resolver=PUBLIC, allow_http=False, allow_private=False)


def test_http_allowed_with_flag_but_loopback_still_blocked():
    assert validate_ha_url("http://ha.example.com", resolver=PUBLIC, allow_http=True, allow_private=False)
    for bad in ("http://127.0.0.1:8123", "http://169.254.169.254", "http://db:8123", "http://localhost:8123"):
        with pytest.raises(UnsafeUrl):
            validate_ha_url(bad, resolver=PUBLIC, allow_http=True, allow_private=True)


def test_private_lan_only_with_flag():
    assert validate_ha_url("http://192.168.1.10:8123", allow_http=True, allow_private=True) == "http://192.168.1.10:8123"
    assert validate_ha_url("https://10.1.2.3", allow_private=True)
    assert validate_ha_url("https://homeassistant.local", resolver=_res("192.168.0.7"), allow_private=True)
    # docker bridge range and CGNAT stay blocked even with the flag
    for bad in ("https://172.18.0.5", "https://100.64.0.1", "https://[fd00::1]:8123x"):
        with pytest.raises(UnsafeUrl):
            validate_ha_url(bad, allow_private=True)


def test_dns_pointing_inside_is_blocked_every_address():
    for ip in ("127.0.0.1", "169.254.169.254", "172.17.0.2", "192.168.1.1"):
        with pytest.raises(UnsafeUrl):
            validate_ha_url("https://ha.example.com", resolver=_res(ip), allow_private=False)
    with pytest.raises(UnsafeUrl):  # one bad address among good ones
        validate_ha_url("https://ha.example.com", resolver=lambda h, p: ["93.184.216.34", "127.0.0.1"], allow_private=True)


def test_client_disables_redirects_and_validates(monkeypatch):
    async def run():
        c = ha_client.HARestClient("https://127.0.0.1", "t")
        with pytest.raises(UnsafeUrl):
            await c._get_client()
        monkeypatch.setattr(ha_client, "validate_ha_url", lambda u: u)
        c2 = ha_client.HARestClient("https://ha.example.com", "t")
        cl = await c2._get_client()
        assert cl.follow_redirects is False
        await c2.aclose()
    asyncio.run(run())


def test_error_text_is_generic():
    import httpx
    raw = httpx.ConnectError("[Errno -2] Name or service not known: db.internal:5432")
    code, msg = ha_client.describe_ha_error(raw)
    assert code == "unreachable" and "db" not in msg and "5432" not in msg
    req = httpx.Request("GET", "https://x")
    assert ha_client.describe_ha_error(httpx.HTTPStatusError("boom", request=req, response=httpx.Response(401, request=req)))[0] == "auth_failed"
    assert ha_client.describe_ha_error(httpx.ReadTimeout("secret host"))[0] == "timeout"
    assert ha_client.describe_ha_error(RuntimeError("password=hunter2"))[1] == "Connection failed"
    err = ha_client.ha_http_error(raw)
    assert err.status_code == 502 and "Errno" not in str(err.detail)


# --------------------------------------------------------------------------- token encryption

def test_encrypt_requires_key(monkeypatch):
    monkeypatch.delenv("IOT_TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ha_client.TokenEncryptionUnavailable):
        ha_client.encrypt_token("abc")
    assert ha_client.ha_http_error(ha_client.TokenEncryptionUnavailable("x")).status_code == 503
    monkeypatch.setenv("IOT_TOKEN_ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(ha_client.TokenEncryptionUnavailable):
        ha_client.encrypt_token("abc")


def test_roundtrip_and_no_base64_fallback(monkeypatch):
    monkeypatch.setenv("IOT_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc = ha_client.encrypt_token("ll-token")
    assert enc != "ll-token" and ha_client.decrypt_token(enc) == "ll-token"
    import base64
    with pytest.raises(ha_client.ReconnectRequired):  # old base64 "encryption" is not accepted
        ha_client.decrypt_token(base64.b64encode(b"ll-token").decode())


def test_legacy_default_key_token_is_migrated_lazily(monkeypatch):
    import base64
    import hashlib
    legacy = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"omnidome-default-key-change-me").digest()))
    stored = legacy.encrypt(b"old-token").decode()
    monkeypatch.setenv("IOT_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    integ = SimpleNamespace(id=1, ha_token_encrypted=stored)
    assert ha_client.token_for_integration(integ) == "old-token"
    assert integ.ha_token_encrypted != stored
    assert ha_client.decrypt_token_ex(integ.ha_token_encrypted) == ("old-token", False)
    bad = SimpleNamespace(id=2, ha_token_encrypted=Fernet(Fernet.generate_key()).encrypt(b"x").decode())
    with pytest.raises(ha_client.ReconnectRequired):
        ha_client.token_for_integration(bad)
    assert ha_client.ha_http_error(ha_client.ReconnectRequired("x")).status_code == 409


# --------------------------------------------------------------------------- role tiers

def _ctx(roles=(), platform=False):
    return SimpleNamespace(roles=list(roles), permissions=[], is_platform_admin=platform, rbac_loaded=True)


def _tier_ok(ctx, tier, monkeypatch):
    monkeypatch.setenv("IOT_ENFORCE_ROLES", "true")
    return asyncio.run(access.has_tier(ctx, tier))


def test_tiers(monkeypatch):
    assert _tier_ok(_ctx(), "viewer", monkeypatch)
    assert not _tier_ok(_ctx(["viewer"]), "operator", monkeypatch)
    assert _tier_ok(_ctx(["manager"]), "operator", monkeypatch)
    assert not _tier_ok(_ctx(["manager"]), "admin", monkeypatch)
    assert _tier_ok(_ctx(["admin"]), "admin", monkeypatch)
    assert _tier_ok(_ctx([], platform=True), "admin", monkeypatch)
    monkeypatch.setenv("IOT_ENFORCE_ROLES", "false")
    assert asyncio.run(access.has_tier(_ctx(), "admin"))


def test_control_policy():
    f = access.required_tier_for_control
    assert f("light", "turn_on", {"brightness": 100}) == "operator"
    assert f("climate", "set_temperature", {"temperature": 21}) == "operator"
    for dom, svc in (("lock", "unlock"), ("alarm_control_panel", "disarm"), ("siren", "turn_on"), ("camera", "turn_off")):
        assert f(dom, svc, {}) == "admin"
    assert f("light", "some_custom_service", {}) == "admin"      # free-form service
    assert f("light", "turn_on", {"weird_key": 1}) == "admin"    # free-form service_data
    assert f("sensor", "turn_on", {}) == "admin"                 # unknown domain
    for bad in ("Turn-On", "turn_on;x", "../x", ""):
        with pytest.raises(HTTPException) as e:
            f("light", bad, {})
        assert e.value.status_code == 422
    with pytest.raises(HTTPException):                           # cannot retarget at another entity
        f("light", "turn_on", {"entity_id": "lock.front_door"})
    with pytest.raises(HTTPException):
        f("light", "turn_on", {"Target": {}})


def test_viewer_and_operator_cannot_lock(monkeypatch):
    needed = access.required_tier_for_control("lock", "unlock", {})
    assert needed == "admin"
    assert not _tier_ok(_ctx(["viewer"]), "operator", monkeypatch)
    assert not _tier_ok(_ctx(["manager"]), needed, monkeypatch)
    assert _tier_ok(_ctx(["owner"]), needed, monkeypatch)


def test_mutating_routes_have_a_gate():
    from services.iot.routes import alerts, automations, devices, events, integrations, rooms, scenes, sensors
    gated = {"POST", "PUT", "DELETE", "PATCH"}
    for mod in (alerts, automations, devices, events, integrations, rooms, scenes, sensors):
        for r in mod.router.routes:
            if gated & set(r.methods):
                deps = [d.call.__name__ for d in r.dependant.dependencies]
                assert any(n.startswith("require_iot_") for n in deps), (mod.__name__, r.path, r.methods)


# --------------------------------------------------------------------------- route order / SSE

def test_stream_declared_before_event_id():
    from services.iot.routes import events
    paths = [r.path for r in events.router.routes]
    assert paths.index("/stream") < paths.index("/{event_id}")


def test_no_static_route_shadowed_by_parametric_sibling():
    from services.iot.routes import alerts, automations, cameras, devices, events, integrations, rooms, scenes, sensors
    for mod in (alerts, automations, cameras, devices, events, integrations, rooms, scenes, sensors):
        seen_param = {}
        for r in mod.router.routes:
            for m in r.methods:
                parts = r.path.strip("/").split("/")
                if len(parts) == 1 and parts[0].startswith("{"):
                    seen_param[m] = r.path
                elif len(parts) == 1 and parts[0] and m in seen_param:
                    pytest.fail(f"{mod.__name__}: {r.path} {m} declared after {seen_param[m]}")


def test_sse_each_subscriber_gets_every_event():
    from services.iot.routes import events
    tenant = uuid.uuid4()
    ev = SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant, device_id=None, automation_id=None, alert_id=None,
                         event_type="x", source="s", message="m", data={}, created_at=None)

    async def run():
        q1, q2 = events.subscribe(tenant), events.subscribe(tenant)
        await events.publish_event(ev)
        await events.publish_event(ev)
        assert q1.qsize() == 2 and q2.qsize() == 2
        events.unsubscribe(tenant, q1)
        await events.publish_event(ev)
        assert q1.qsize() == 2 and q2.qsize() == 3
        events.unsubscribe(tenant, q2)
        assert tenant not in events._subscribers

    asyncio.run(run())


def test_sse_queue_bounded_and_generator_cleans_up(monkeypatch):
    from services.iot.routes import events
    tenant = uuid.uuid4()
    monkeypatch.setattr(events, "SUBSCRIBER_QUEUE_SIZE", 2)

    async def run():
        q = events.subscribe(tenant)
        for i in range(5):
            events._offer(q, str(i))
        assert q.qsize() == 2 and q.get_nowait() == "3"
        gen = events._sse_event_generator(tenant, q)
        assert (await gen.__anext__()).startswith("event: connected")
        await gen.aclose()
        assert tenant not in events._subscribers

    asyncio.run(run())


def test_subscriber_cap(monkeypatch):
    from services.iot.routes import events
    tenant = uuid.uuid4()
    monkeypatch.setattr(events, "MAX_SUBSCRIBERS_PER_TENANT", 1)

    async def run():
        q = events.subscribe(tenant)
        with pytest.raises(HTTPException) as e:
            events.subscribe(tenant)
        assert e.value.status_code == 429
        events.unsubscribe(tenant, q)

    asyncio.run(run())


# --------------------------------------------------------------------------- migration guards

def test_rebuild_decision():
    legacy = {"device_name", "id"}
    assert rebuild_decision(legacy, 0, []) == "rebuild"
    assert rebuild_decision(legacy, 3, []) == "refuse_rows"
    assert rebuild_decision(legacy, 0, ["view:v_devices"]) == "refuse_dependents"
    assert rebuild_decision({"device_name", "ha_entity_id"}, 0, []) == "skip"


class _Result:
    def __init__(self, rows): self._rows = rows
    def scalar(self): return self._rows[0][0] if self._rows else None
    def all(self): return self._rows
    def mappings(self): return self


class _FakeConn:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, count, dependents):
        self.sql, self.count, self.dependents = [], count, dependents

    def execute(self, stmt, *a, **k):
        q = " ".join(str(stmt).split())
        self.sql.append(q)
        if q.startswith("SELECT count"):
            return _Result([(self.count,)])
        if "pg_rewrite" in q:
            return _Result([(d,) for d in self.dependents])
        if "pg_policy" in q or "pg_trigger" in q:
            return _Result([])
        return _Result([])

    def all(self): return []


def _run_rebuild(monkeypatch, count, dependents):
    from services.iot import database
    legacy = [{"name": n} for n in ("id", "device_name", "device_type")]
    fake_insp = SimpleNamespace(has_table=lambda t: True, get_columns=lambda t: legacy)
    monkeypatch.setattr(database, "inspect", lambda c: fake_insp)
    monkeypatch.setattr(database.Base.metadata, "create_all", lambda *a, **k: None)
    conn = _FakeConn(count, dependents)
    return database._rebuild_empty_legacy_devices(conn), conn.sql


def test_migration_locks_before_count_and_drop(monkeypatch):
    rebuilt, sql = _run_rebuild(monkeypatch, 0, [])
    assert rebuilt
    lock = next(i for i, q in enumerate(sql) if q.startswith("LOCK TABLE iot_devices IN ACCESS EXCLUSIVE MODE"))
    count = next(i for i, q in enumerate(sql) if q.startswith("SELECT count"))
    drop = next(i for i, q in enumerate(sql) if q.startswith("DROP TABLE iot_devices"))
    assert lock < count < drop


def test_migration_refuses_rows_and_dependents(monkeypatch):
    rebuilt, sql = _run_rebuild(monkeypatch, 4, [])
    assert not rebuilt and not any(q.startswith("DROP TABLE") for q in sql)
    rebuilt, sql = _run_rebuild(monkeypatch, 0, ["v_devices"])
    assert not rebuilt and not any(q.startswith("DROP TABLE") for q in sql)
