"""Call-center: ws tenant isolation, consent gate, recording refs, FK tenant validation, CDR import,
bounded intelligence, role tiers, encrypted provider credentials.
Run: python -m pytest services/call_center/tests -q   (SQLite, no Postgres)
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from services.call_center import access, policy  # noqa: E402
from services.call_center import main as cc  # noqa: E402
from services.call_center.database import Agent, Base, CallQueue, CallSession, ProviderCredential  # noqa: E402
from services.common.auth import AuthContext, get_auth_context  # noqa: E402
from services.common import secretbox  # noqa: E402

T1 = uuid.UUID("a0000000-0000-0000-0000-00000000000a")
T2 = uuid.UUID("b0000000-0000-0000-0000-00000000000b")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CALL_VERIFY_CUSTOMER", "false")
    monkeypatch.delenv("CALL_RECORDING_DEFAULT_CONSENT", raising=False)
    monkeypatch.setenv("CALL_CENTER_ENFORCE_ROLES", "true")
    monkeypatch.setattr(cc.guard, "enforce_modules", False)  # entitlement lookup needs the real DB


@pytest.fixture()
def factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cc.db'}")

    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    return async_sessionmaker(engine, expire_on_commit=False)


def run(coro):
    return asyncio.run(coro)


# ── pure policy: websocket isolation ───────────────────────────────────────

def test_connection_key_is_tenant_scoped():
    sid = uuid.uuid4()
    assert policy.connection_key(T1, sid) != policy.connection_key(T2, sid)


def test_whisper_authorize_tenant_and_ownership():
    sid_agent, user = uuid.uuid4(), uuid.uuid4()
    base = dict(user_id=user, session_agent_id=sid_agent)
    # other tenant's session is never allowed, even for an admin
    assert not policy.whisper_authorize(tenant_id=T1, is_admin=True, session_tenant_id=T2, **base)
    # same tenant: admin ok; plain user who is not the agent: no
    assert policy.whisper_authorize(tenant_id=T1, is_admin=True, session_tenant_id=T1, **base)
    assert not policy.whisper_authorize(tenant_id=T1, is_admin=False, session_tenant_id=T1, **base)
    # the agent's linked user, or agent id == user id
    assert policy.whisper_authorize(tenant_id=T1, is_admin=False, session_tenant_id=T1, agent_user_id=user, **base)
    assert policy.whisper_authorize(tenant_id=T1, is_admin=False, session_tenant_id=T1, user_id=sid_agent,
                                    session_agent_id=sid_agent)
    assert not policy.whisper_authorize(tenant_id=T1, is_admin=True, session_tenant_id=None, **base)


def test_ws_auth_ignores_query_token_in_signed_mode(monkeypatch):
    from services.common.ws_auth import authenticate_ws
    monkeypatch.setenv("AUTH_MODE", "signed")
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "s" * 48)
    with pytest.raises(ValueError):
        authenticate_ws({"x-user-id": str(uuid.uuid4()), "x-tenant-id": str(T1)}, "/ws/whisper/x", "forged.jwt.token")
    monkeypatch.setenv("AUTH_MODE", "header")
    monkeypatch.setenv("AUTH_JWT_VERIFY", "false")
    with pytest.raises(ValueError):
        authenticate_ws({}, "/ws/whisper/x", "forged.jwt.token")


# ── consent gate ───────────────────────────────────────────────────────────

def test_consent_gate(monkeypatch):
    assert policy.consent_allows_recording("given") and policy.consent_allows_recording("not_required")
    assert not policy.consent_allows_recording("declined")
    assert not policy.consent_allows_recording("unknown")
    assert not policy.consent_allows_recording(None)
    monkeypatch.setenv("CALL_RECORDING_DEFAULT_CONSENT", "announced")
    assert policy.consent_allows_recording("unknown")
    assert not policy.consent_allows_recording("declined")  # never overridden


def test_retention_days(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert policy.retention_until(start) == start + timedelta(days=90)
    monkeypatch.setenv("CALL_RECORDING_RETENTION_DAYS", "30")
    assert policy.retention_until(start) == start + timedelta(days=30)


# ── recording ref ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd",
                                 "http://169.254.169.254/x", "https://127.0.0.1/x", "../../etc/passwd",
                                 "a//b", "ftp://example.com/x"])
def test_recording_ref_rejects(bad):
    with pytest.raises(ValueError):
        policy.validate_recording_ref(bad, resolver=lambda h, p: ["93.184.216.34"])


def test_recording_ref_accepts():
    pub = lambda h, p: ["93.184.216.34"]  # noqa: E731
    assert policy.validate_recording_ref("https://rec.example.com/a.mp3", resolver=pub) == "https://rec.example.com/a.mp3"
    assert policy.validate_recording_ref("tenant1/2026/call-1.mp3") == "tenant1/2026/call-1.mp3"
    assert policy.validate_recording_ref("  ") is None


# ── CDR parsing ────────────────────────────────────────────────────────────

def test_cdr_parse_validation_and_anomalies():
    agent = uuid.uuid4()
    csv_text = (
        "external_call_id,agent_extension,direction,start_time,end_time,duration_seconds,outcome,customer_id\n"
        "c1,1001,inbound,2026-01-01T10:00:00Z,2026-01-01T10:05:00Z,300,resolved,\n"
        "c2,1001,INBOUND,2026-01-01T11:00:00Z,2026-01-01T11:05:00Z,60,,\n"      # duration anomaly
        "c3,9999,INBOUND,2026-01-01T11:00:00Z,,,,\n"                              # unknown agent
        "c1,1001,INBOUND,2026-01-01T12:00:00Z,,,,\n"                              # dup in file
        "c4,1001,SIDEWAYS,2026-01-01T12:00:00Z,,,,\n"                             # bad direction
        "c5,1001,INBOUND,not-a-date,,,,\n"                                        # bad date
        "c6,1001,INBOUND,2026-01-01T12:10:00Z,2026-01-01T12:00:00Z,,,\n"          # end before start
    )
    out = policy.parse_cdr_csv(csv_text, {"1001": agent})
    assert [r["external_call_id"] for r in out["rows"]] == ["c1", "c2"]
    assert out["anomalies"] == 1 and len(out["errors"]) == 5 and out["total"] == 7
    assert out["rows"][1]["duration_seconds"] == 300  # derived from timestamps
    assert policy.parse_cdr_csv("a,b\n1,2\n", {})["header_error"]


# ── HTTP-level tests (SQLite) ──────────────────────────────────────────────

def _client(factory, roles, tenant=T1, user=None):
    from fastapi.testclient import TestClient
    user = user or uuid.uuid4()

    async def _db():
        async with factory() as s:
            yield s
            await s.commit()

    def _auth():
        return AuthContext(user_id=user, tenant_id=tenant, roles=list(roles))

    cc.app.dependency_overrides[get_auth_context] = _auth
    cc.app.dependency_overrides[cc.get_session] = _db
    c = TestClient(cc.app)
    c.headers["x-tenant-id"] = str(tenant)
    c.headers["x-user-id"] = str(user)
    return c


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    cc.app.dependency_overrides.clear()


async def _seed(factory):
    async with factory() as s:
        a1 = Agent(tenant_id=T1, name="A1", extension="1001")
        a2 = Agent(tenant_id=T2, name="A2", extension="2001")
        q2 = CallQueue(tenant_id=T2, name="Q2", direction="INBOUND", category="SALES")
        s.add_all([a1, a2, q2])
        await s.commit()
        return a1.id, a2.id, q2.id


def _create_body(agent, **kw):
    body = {"agent_id": str(agent), "start_time": "2026-01-01T10:00:00Z"}
    body.update(kw)
    return body


def test_create_session_rejects_foreign_agent_and_queue(factory):
    a1, a2, q2 = run(_seed(factory))
    c = _client(factory, ["agent"])
    assert c.post("/sessions", json=_create_body(a2)).status_code == 404            # other tenant's agent
    assert c.post("/sessions", json=_create_body(a1, queue_id=str(q2))).status_code == 404
    assert c.post("/sessions", json=_create_body(uuid.uuid4())).status_code == 404
    ok = c.post("/sessions", json=_create_body(a1))
    assert ok.status_code == 201 and ok.json()["recording_consent"] == "unknown"
    assert ok.json()["retention_until"]


def test_create_session_customer_verified(factory, monkeypatch):
    a1, _, _ = run(_seed(factory))
    monkeypatch.setenv("CALL_VERIFY_CUSTOMER", "true")

    async def missing(tenant, cust):
        return False
    monkeypatch.setattr(cc, "_customer_exists", missing)
    c = _client(factory, ["agent"])
    assert c.post("/sessions", json=_create_body(a1, customer_id=str(uuid.uuid4()))).status_code == 404


def test_create_session_recording_url_and_consent(factory):
    a1, _, _ = run(_seed(factory))
    c = _client(factory, ["agent"])
    r = c.post("/sessions", json=_create_body(a1, recording_url="javascript:alert(1)", recording_consent="given"))
    assert r.status_code == 422
    r = c.post("/sessions", json=_create_body(a1, recording_url="calls/2026/a.mp3"))          # consent unknown
    assert r.status_code == 409
    r = c.post("/sessions", json=_create_body(a1, recording_url="calls/2026/a.mp3", recording_consent="declined"))
    assert r.status_code == 409
    r = c.post("/sessions", json=_create_body(a1, recording_url="calls/2026/a.mp3", recording_consent="given"))
    assert r.status_code == 201
    # agent tier does not get the recording reference back; admin does
    assert r.json()["recording_url"] is None and r.json()["has_recording"] is True
    sid = r.json()["id"]
    adm = _client(factory, ["admin"])
    assert adm.get(f"/sessions/{sid}").json()["recording_url"] == "calls/2026/a.mp3"
    # declining consent afterwards wipes the recording reference
    assert adm.put(f"/sessions/{sid}/consent", json={"consent": "declined"}).status_code == 200
    assert adm.get(f"/sessions/{sid}").json()["recording_url"] is None


def test_whisper_session_needs_own_tenant_and_consent(factory):
    a1, a2, _ = run(_seed(factory))
    c = _client(factory, ["agent"])
    sess = c.post("/sessions", json=_create_body(a1)).json()["id"]
    assert c.post(f"/whisper/sessions?call_session_id={sess}&agent_id={a1}").status_code == 409  # no consent
    assert c.put(f"/sessions/{sess}/consent", json={"consent": "given"}).status_code == 200
    assert c.post(f"/whisper/sessions?call_session_id={sess}&agent_id={a2}").status_code == 404  # foreign agent
    assert c.post(f"/whisper/sessions?call_session_id={uuid.uuid4()}&agent_id={a1}").status_code == 404
    ok = c.post(f"/whisper/sessions?call_session_id={sess}&agent_id={a1}")
    assert ok.status_code == 201 and "tenant_id" not in ok.json()["ws_url"]


# ── import ─────────────────────────────────────────────────────────────────

CDR = (b"external_call_id,agent_extension,start_time,end_time,duration_seconds,outcome\n"
       b"x1,1001,2026-01-01T10:00:00Z,2026-01-01T10:05:00Z,300,RESOLVED\n"
       b"x2,1001,2026-01-01T11:00:00Z,2026-01-01T11:05:00Z,10,\n"
       b"x3,0000,2026-01-01T11:00:00Z,,,\n")


def test_import_persists_validates_and_is_idempotent(factory):
    run(_seed(factory))
    c = _client(factory, ["admin"])
    r = c.post("/reports/import", files={"file": ("cdr.csv", CDR, "text/csv")})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "PARTIAL"
    assert body["processed_records"] == 2 and body["rejected_rows"] == 1 and body["anomalies_detected"] == 1
    assert body["errors"][0]["row"] == 4
    again = c.post("/reports/import", files={"file": ("cdr.csv", CDR, "text/csv")}).json()
    assert again["processed_records"] == 0 and again["duplicates_skipped"] == 2

    async def count():
        async with factory() as s:
            return len((await s.execute(select(CallSession))).scalars().all())
    assert run(count()) == 2


def test_import_size_cap_header_and_role(factory, monkeypatch):
    run(_seed(factory))
    monkeypatch.setenv("CALL_IMPORT_MAX_MB", "0.0001")  # ~104 bytes
    c = _client(factory, ["admin"])
    assert c.post("/reports/import", files={"file": ("c.csv", CDR, "text/csv")}).status_code == 413
    monkeypatch.setenv("CALL_IMPORT_MAX_MB", "10")
    assert c.post("/reports/import", files={"file": ("c.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 422
    agent_client = _client(factory, ["agent"])
    assert agent_client.post("/reports/import", files={"file": ("c.csv", CDR, "text/csv")}).status_code == 403


# ── intelligence ───────────────────────────────────────────────────────────

def test_intelligence_semantics_and_bounds(factory):
    a1, _, _ = run(_seed(factory))
    now = datetime.now(timezone.utc)

    async def seed():
        async with factory() as s:
            def mk(hours_ago, outcome, finished=True, tenant=T1, dur=100, hour=None):
                st = now - timedelta(hours=hours_ago)
                if hour is not None:
                    st = st.replace(hour=hour, minute=0)
                return CallSession(tenant_id=tenant, agent_id=a1, start_time=st, end_time=st if finished else None,
                                   duration_seconds=dur, outcome=outcome)
            s.add_all([
                mk(1, "RESOLVED", hour=9), mk(2, "completed", hour=9), mk(3, "ESCALATED", hour=14),
                mk(4, None, finished=True, hour=9),            # ended but NO explicit outcome: not resolved
                mk(5, None, finished=False, hour=9),           # still open: excluded from the denominator
                mk(24 * 90, "RESOLVED"),                       # outside the 30-day window
                mk(1, "RESOLVED", tenant=T2),                  # other tenant
            ])
            await s.commit()
    run(seed())

    async def go():
        async with factory() as s:
            return await cc.compute_intelligence(s, T1, now - timedelta(days=30), 30)
    out = run(go())
    assert out["total_sessions"] == 5
    assert out["closed_queries"] == 2
    assert out["resolution_rate"] == 50.0               # 2 resolved / 4 finished (not 100%)
    assert out["peak_volume_period"].startswith("09:00-10:00")
    assert out["health_status"] == "NEEDS_ATTENTION"

    async def empty():
        async with factory() as s:
            return await cc.compute_intelligence(s, uuid.uuid4(), now - timedelta(days=30), 30)
    e = run(empty())
    assert e["resolution_rate"] is None and e["peak_volume_period"] is None and e["health_status"] == "NO_DATA"


def test_purge_expired(factory):
    a1, _, _ = run(_seed(factory))
    now = datetime.now(timezone.utc)

    async def go():
        async with factory() as s:
            s.add_all([
                CallSession(tenant_id=T1, agent_id=a1, start_time=now, retention_until=now - timedelta(days=1),
                            transcript="old", recording_url="k/old"),
                CallSession(tenant_id=T1, agent_id=a1, start_time=now, retention_until=now + timedelta(days=1),
                            transcript="new"),
            ])
            await s.commit()
            n = await cc.purge_expired_recordings(s, now)
            await s.commit()
            rows = (await s.execute(select(CallSession).order_by(CallSession.retention_until))).scalars().all()
            return n, [(r.transcript, r.recording_url) for r in rows]
    n, rows = run(go())
    assert n == 1 and rows == [(None, None), ("new", None)]


# ── roles + credentials ────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,tier", [
    ("GET", "/agents", "agent"), ("POST", "/sessions", "agent"), ("DELETE", "/sessions/x", "admin"),
    ("DELETE", "/agents/x", "admin"), ("DELETE", "/queues/x", "admin"),
    ("GET", "/provider-credentials", "admin"), ("PUT", "/provider-credentials/sip", "admin"),
    ("POST", "/reports/import", "admin"), ("GET", "/reports/export", "admin"),
    ("GET", "/sessions/x/recording", "admin"),
])
def test_required_tier(method, path, tier):
    assert access.required_tier(method, path) == tier


def test_roles_enforced_over_http(factory):
    a1, _, _ = run(_seed(factory))
    assert _client(factory, []).get("/agents").status_code == 403                       # no call-center role
    assert _client(factory, ["agent"]).get("/agents").status_code == 200
    assert _client(factory, ["agent"]).delete(f"/agents/{a1}").status_code == 403
    assert _client(factory, ["agent"]).get("/provider-credentials").status_code == 403
    assert _client(factory, ["admin"]).delete(f"/agents/{a1}").status_code == 204


def test_provider_credentials_encrypted_and_never_returned(factory):
    c = _client(factory, ["admin"])
    r = c.put("/provider-credentials/sip", json={"fields": {"host": "sip.example.com", "password": "TOP-SECRET-PW"}})
    assert r.status_code == 200 and "TOP-SECRET-PW" not in r.text and r.json()["fields"] == ["host", "password"]
    assert "TOP-SECRET-PW" not in c.get("/provider-credentials").text

    async def raw():
        async with factory() as s:
            return (await s.execute(select(ProviderCredential))).scalar_one().config_enc
    blob = run(raw())
    assert "TOP-SECRET-PW" not in blob and "TOP-SECRET-PW" in secretbox.decrypt(blob)
    assert c.put("/provider-credentials/unknown", json={"fields": {"a": "b"}}).status_code == 404


def test_provider_credentials_fail_closed_without_key(factory, monkeypatch):
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY")
    c = _client(factory, ["admin"])
    assert c.put("/provider-credentials/sip", json={"fields": {"password": "x"}}).status_code == 503
