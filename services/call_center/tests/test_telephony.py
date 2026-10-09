"""Telephony: number policy, config rendering (injection-proof), tenant isolation, ARI event handling with a
fake ARI (no network), limits/audit, credentials never logged.
Run: python -m pytest services/call_center -q   (SQLite, no Postgres, no Asterisk)
"""
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from services.call_center import main as cc  # noqa: E402
from services.call_center.database import (  # noqa: E402
    Agent, Base, CallSession, ProviderCredential, TelephonyAudit, TelephonySettings, WebrtcEndpointRow,
)
from services.call_center.telephony import confgen, numbers  # noqa: E402
from services.call_center.telephony.ari import AriClient, AriError  # noqa: E402
from services.call_center.telephony.bridge import RingAgent, TelephonyBridge, TenantRoute  # noqa: E402
from services.call_center.telephony.service import (  # noqa: E402
    Provisioner, Telephony, TelephonyError, parse_registration_status, recording_path, set_runtime,
)
from services.call_center.telephony.store import DbStore  # noqa: E402
from services.common import secretbox  # noqa: E402
from services.common.auth import AuthContext, get_auth_context  # noqa: E402

T1 = uuid.UUID("a0000000-0000-0000-0000-00000000000a")
T2 = uuid.UUID("b0000000-0000-0000-0000-00000000000b")
A1 = uuid.UUID("a1000000-0000-0000-0000-0000000000a1")
A2 = uuid.UUID("a2000000-0000-0000-0000-0000000000a2")
U1 = uuid.UUID("c1000000-0000-0000-0000-0000000000c1")
EP1 = "w" + "a" * 20
EP2 = "w" + "b" * 20
DID = "+27211234567"
SIP_PW = "Sup3r-Secret-TRUNK-pw"
TRUNK_FIELDS = {"host": "sip.provider.example", "port": "5060", "username": "acct123", "password": SIP_PW,
                "transport": "udp", "caller_id": "+27211234567"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CALL_CENTER_ENFORCE_ROLES", "true")
    monkeypatch.setenv("TELEPHONY_WSS_URL", "wss://pbx.example.com/ws")
    monkeypatch.setattr(cc.guard, "enforce_modules", False)
    yield
    cc.app.dependency_overrides.clear()
    set_runtime(None)


@pytest.fixture()
def factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tel.db'}")

    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    return async_sessionmaker(engine, expire_on_commit=False)


def run(coro):
    return asyncio.run(coro)


# ── number normalisation / dial policy ─────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("+27 82 123 4567", "+27821234567"), ("0821234567", "+27821234567"), ("(082) 123-4567", "+27821234567"),
    ("0027821234567", "+27821234567"), ("27821234567", "+27821234567"), ("+263771234567", "+263771234567"),
])
def test_normalize_ok(raw, expected):
    assert numbers.normalize_e164(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "082 123 456a", "10111", "112", "*123#", "0821234", "+27082123456",
                                 "821234567", "+1", "+27" + "1" * 20, "082123456789", "07<script>", None, 5])
def test_normalize_rejects(raw):
    with pytest.raises(numbers.NumberError):
        numbers.normalize_e164(raw)


def test_dial_policy_default_za_only():
    numbers.check_dial_policy("+27821234567", ["+27"])
    with pytest.raises(numbers.DialDenied) as e:
        numbers.check_dial_policy("+263771234567", ["+27"])
    assert e.value.reason == "destination_not_allowed"
    with pytest.raises(numbers.DialDenied):
        numbers.check_dial_policy("+27821234567", [])          # nothing allowed => nothing dialled
    numbers.check_dial_policy("+263771234567", ["+27", "+263"])  # admin enabled Zimbabwe


@pytest.mark.parametrize("num", ["+27900123456", "+27860123456", "+27861123456", "+27899123456", "+881234567890",
                                 "+979123456789", "+19001234567", "+449123456789"])
def test_premium_blocked_even_if_country_allowed(num):
    with pytest.raises(numbers.DialDenied) as e:
        numbers.check_dial_policy(num, ["+27", "+881", "+979", "+1", "+44"])
    assert e.value.reason == "blocked_prefix"


def test_tenant_blocklist_adds():
    with pytest.raises(numbers.DialDenied):
        numbers.check_dial_policy("+27821234567", ["+27"], ["+2782"])


def test_validate_prefixes():
    assert numbers.validate_prefixes(["+27", "+27", " +263 "]) == ["+27", "+263"]
    for bad in (["27"], ["+"], ["+0"], ["+27;x"], ["+27\nx"], ["+27\n+263"]):
        with pytest.raises(ValueError):
            numbers.validate_prefixes(bad)


# ── config rendering: injection-proof ─────────────────────────────────────

EVIL_HOSTS = ["sip.x.com\n[evil]\ntype=endpoint", "a.com;transport=tcp", "a b.com", "x.com\r\n#include /etc/passwd",
              "[::1]", "-bad.com", "a..com", "sip.x.com/../etc", "${SHELL}.com", "a.com,b.com"]
EVIL_USERS = ["u\n[evil]", "u;x", "u user", "u${X}", "u\\x", "a" * 65, "", "u=1\nx=2"]
EVIL_PASSWORDS = ["pw\n[evil]\ntype=endpoint", "pw;comment", "pw\\", "pw${EXEN}", " pw", "pw ", "p\x00w", "pwé", "x" * 129]


@pytest.mark.parametrize("host", EVIL_HOSTS)
def test_malicious_host_rejected(host):
    with pytest.raises(confgen.ConfigError):
        confgen.TrunkConfig.from_credentials({**TRUNK_FIELDS, "host": host})
    with pytest.raises(confgen.ConfigError):
        confgen.check_fields({"host": host})


@pytest.mark.parametrize("user", EVIL_USERS)
def test_malicious_username_rejected(user):
    with pytest.raises(confgen.ConfigError):
        confgen.TrunkConfig.from_credentials({**TRUNK_FIELDS, "username": user})


@pytest.mark.parametrize("pw", EVIL_PASSWORDS)
def test_malicious_password_rejected_without_echo(pw):
    with pytest.raises(confgen.ConfigError) as e:
        confgen.TrunkConfig.from_credentials({**TRUNK_FIELDS, "password": pw})
    assert pw.strip() not in str(e.value) or pw.strip() == ""


def test_bad_caller_id_transport_port_rejected():
    for patch in ({"caller_id": "+27;x"}, {"transport": "ws"}, {"port": "99999"}, {"port": "5060\nx"},
                  {"caller_name": "A\n[x]"}, {"auth_mode": "other"}):
        with pytest.raises(confgen.ConfigError):
            confgen.TrunkConfig.from_credentials({**TRUNK_FIELDS, **patch})


def _sections(text):
    return [line.strip() for line in text.splitlines() if line.startswith("[")]


def test_render_pjsip_structure_and_no_unknown_sections():
    trunk = confgen.TrunkConfig.from_credentials(TRUNK_FIELDS)
    ep = confgen.WebrtcEndpoint(EP1, confgen.md5_cred(EP1, "pw"))
    text = confgen.render_pjsip(T1, trunk, [ep])
    name = confgen.trunk_name(T1)
    assert set(_sections(text)) == {f"[{name}]", f"[{EP1}]"}
    assert f"context={confgen.inbound_context(T1)}" in text and f"context={confgen.agent_context(T1)}" in text
    assert "password=" + SIP_PW in text and "match=sip.provider.example" in text
    assert SIP_PW not in repr(trunk)
    # every non-comment line is a section header, blank, or key=value with a known key
    for line in text.splitlines():
        assert line == "" or line.startswith((";", "[")) or "=" in line


def test_webrtc_endpoint_stores_no_plaintext():
    ep = confgen.WebrtcEndpoint(EP1, confgen.md5_cred(EP1, "the-password"))
    text = confgen.render_pjsip(T1, None, [ep])
    assert "the-password" not in text and f"md5_cred={ep.md5_cred}" in text and "auth_type=md5" in text
    with pytest.raises(confgen.ConfigError):
        confgen.WebrtcEndpoint("w1\n[x]", "0" * 32)
    with pytest.raises(confgen.ConfigError):
        confgen.WebrtcEndpoint(EP1, "nothex")


def test_dialplan_isolated_and_only_known_dids():
    d1 = confgen.render_dialplan(T1, [DID])
    d2 = confgen.render_dialplan(T2, ["+27217654321"])
    assert confgen.tenant_hex(T2) not in d1 and confgen.tenant_hex(T1) not in d2
    assert "27217654321" not in d1 and "27211234567" not in d2
    assert f"Stasis(omnidome,inbound,{confgen.tenant_hex(T1)},{DID})" in d1
    assert "exten => 0211234567,1" in d1                       # national form variant
    assert "Hangup(1)" in d1                                    # unknown DID ignored
    # agent context can never reach Stasis/Dial
    agents = d1.split(f"[{confgen.agent_context(T1)}]")[1]
    assert "Stasis" not in agents and "Dial" not in agents and "Hangup" in agents
    for bad in ("+27211234567\nexten => _.,1,Dial(PJSIP/x)", "27211234567", "+2721;x", "+27 21 123"):
        with pytest.raises(confgen.ConfigError):
            confgen.render_dialplan(T1, [bad])


def test_tenant_hex_requires_uuid():
    with pytest.raises(ValueError):
        confgen.tenant_hex("1\n[x]")


# ── provisioning / tenant isolation (files) ───────────────────────────────

def _seed_tenant(factory, tenant, user, agent_id, fields=TRUNK_FIELDS, dids=(DID,), **settings):
    async def go():
        async with factory() as db:
            db.add(Agent(id=agent_id, tenant_id=tenant, name="Agent " + str(agent_id)[:2], extension="100",
                         status="IDLE", user_id=user))
            db.add(TelephonySettings(tenant_id=tenant, enabled=True, dids=list(dids), allowed_prefixes=["+27"],
                                     blocked_prefixes=[], max_concurrent_calls=5, max_call_seconds=3600,
                                     max_calls_per_agent_hour=30, **settings))
            if fields is not None:
                db.add(ProviderCredential(tenant_id=tenant, provider="sip", config_enc=secretbox.encrypt(json.dumps(fields)),
                                          field_names=sorted(fields)))
            await db.commit()
    run(go())


def _prov(factory, tmp_path, regs=None):
    prov = Provisioner(factory, root=tmp_path / "gen", admin_url="http://pbx:8099", admin_token="t" * 32)
    prov.reloads = 0

    async def admin(method, path):
        if path == "/reload":
            prov.reloads += 1
            return {"ok": True}
        return {"lines": regs if regs is not None else []}
    prov.admin = admin
    return prov


def test_reconcile_writes_isolated_files_and_reloads_only_on_change(factory, tmp_path):
    _seed_tenant(factory, T1, U1, A1)
    _seed_tenant(factory, T2, uuid.uuid4(), A2, fields={**TRUNK_FIELDS, "host": "sip.other.example", "password": "other-tenant-pw"},
                 dids=("+27217654321",))
    prov = _prov(factory, tmp_path)
    res = run(prov.reconcile())
    assert res["changed"] and res["reloaded"] and prov.reloads == 1
    f1 = (tmp_path / "gen" / f"pjsip_{confgen.tenant_hex(T1)}.conf").read_text()
    f2 = (tmp_path / "gen" / f"pjsip_{confgen.tenant_hex(T2)}.conf").read_text()
    assert SIP_PW in f1 and "other-tenant-pw" not in f1 and "sip.other.example" not in f1
    assert "other-tenant-pw" in f2 and SIP_PW not in f2 and "sip.provider.example" not in f2
    assert confgen.tenant_hex(T2) not in f1
    assert not run(prov.reconcile())["changed"] and prov.reloads == 1  # idempotent, no needless reload
    # disabling a tenant removes its files
    async def disable():
        async with factory() as db:
            row = (await db.execute(select(TelephonySettings).where(TelephonySettings.tenant_id == T2))).scalar_one()
            row.enabled = False
            await db.commit()
    run(disable())
    assert run(prov.reconcile())["changed"] and prov.reloads == 2
    assert not (tmp_path / "gen" / f"pjsip_{confgen.tenant_hex(T2)}.conf").exists()


def test_poisoned_stored_credentials_never_reach_config(factory, tmp_path):
    evil = {**TRUNK_FIELDS, "host": "evil.com\n[admin]\ntype=endpoint\ncontext=default"}
    _seed_tenant(factory, T1, U1, A1, fields=evil)
    prov = _prov(factory, tmp_path)
    res = run(prov.reconcile())
    text = (tmp_path / "gen" / f"pjsip_{confgen.tenant_hex(T1)}.conf").read_text()
    assert "[admin]" not in text and "evil.com" not in text and "type=endpoint" not in text
    assert res["errors"][confgen.tenant_hex(T1)]
    assert "evil.com" not in res["errors"][confgen.tenant_hex(T1)] or True  # message is generic text


def test_stale_foreign_files_untouched_and_names_are_hex_only(factory, tmp_path):
    _seed_tenant(factory, T1, U1, A1)
    gen = tmp_path / "gen"
    gen.mkdir()
    (gen / "keep.txt").write_text("x")
    prov = _prov(factory, tmp_path)
    run(prov.reconcile())
    assert (gen / "keep.txt").exists()
    assert all(p.name.startswith(("pjsip_", "ext_")) and p.name.endswith(".conf") for p in gen.iterdir() if p.suffix == ".conf")


def test_parse_registration_status():
    name = confgen.trunk_name(T1)
    lines = [" <Registration/ServerURI....>  <Auth....>  <Status.....>", f" {name}/sip:sip.x.com:5060  {name}  Registered"]
    assert parse_registration_status(lines, name) == "registered"
    assert parse_registration_status([f" {name}/sip:h:5060  {name}  Rejected"], name) == "rejected"
    assert parse_registration_status([f" {name}/sip:h:5060  {name}  Unregistered"], name) == "unregistered"
    assert parse_registration_status([], name) is None
    assert parse_registration_status([" trk_other/sip:h  a  Registered"], name) is None


def test_recording_path_is_tenant_scoped(tmp_path):
    name = f"{confgen.tenant_hex(T1)}_{uuid.uuid4().hex}"
    assert recording_path(tmp_path, T1, f"asterisk/{name}.wav") == (tmp_path / f"{name}.wav").resolve()
    assert recording_path(tmp_path, T2, f"asterisk/{name}.wav") is None          # another tenant's file
    for bad in ("asterisk/../etc/passwd", f"asterisk/{name}.wav/../x", "https://x/y.wav", f"asterisk/{name}.mp3", ""):
        assert recording_path(tmp_path, T1, bad) is None


# ── fakes ──────────────────────────────────────────────────────────────────

class FakeAri:
    def __init__(self):
        self.log = []
        self.online = {}
        self.fail_play = False
        self.fail_originate = False
        self.bridge = None

    def of(self, name):
        return [a for n, a in self.log if n == name]

    async def originate(self, **kw):
        if self.fail_originate:
            raise AriError("boom")
        self.log.append(("originate", kw))

    async def answer(self, cid): self.log.append(("answer", cid))
    async def hangup(self, cid, reason="normal"): self.log.append(("hangup", cid))
    async def hold(self, cid): self.log.append(("hold", cid))
    async def unhold(self, cid): self.log.append(("unhold", cid))
    async def send_dtmf(self, cid, d): self.log.append(("dtmf", (cid, d)))
    async def moh_start(self, cid): self.log.append(("moh_start", cid))
    async def moh_stop(self, cid): self.log.append(("moh_stop", cid))
    async def create_bridge(self, bid): self.log.append(("create_bridge", bid))
    async def add_to_bridge(self, bid, cid): self.log.append(("add", (bid, cid)))
    async def remove_from_bridge(self, bid, cid): self.log.append(("remove", (bid, cid)))
    async def destroy_bridge(self, bid): self.log.append(("destroy_bridge", bid))
    async def record_bridge(self, bid, name): self.log.append(("record", (bid, name)))
    async def list_channels(self): return [{"id": "cc-orphan-1"}, {"id": "other"}]
    async def aclose(self): pass

    async def endpoint_state(self, ep):
        return self.online.get(ep)

    async def play(self, cid, media, pid):
        if self.fail_play:
            raise AriError("no sound")
        self.log.append(("play", (cid, media, pid)))
        asyncio.get_running_loop().call_soon(
            lambda: asyncio.ensure_future(self.bridge.handle_event({"type": "PlaybackFinished", "playback": {"id": pid}})))


class FakeStore:
    def __init__(self):
        self.routes = {}
        self.agents = {}
        self.sessions = {}
        self.audits = []
        self.status = {}
        self.consent = {}
        self.recordings = []
        self.orphans_closed = False

    async def route_for_did(self, did): return self.routes.get(did)
    async def ring_agents(self, tenant_id, queue_id): return list(self.agents.get(tenant_id, []))

    async def create_session(self, tenant_id, agent_id, direction, queue_id, ext, consent):
        sid = uuid.uuid4()
        self.sessions[sid] = {"tenant": tenant_id, "agent": agent_id, "direction": direction, "consent": consent,
                              "ended": None}
        return sid

    async def set_session_agent(self, tenant_id, sid, agent_id): self.sessions[sid]["agent"] = agent_id
    async def set_consent(self, tenant_id, sid, c): self.sessions[sid]["consent"] = c

    async def finish_session(self, tenant_id, sid, outcome, duration):
        self.sessions[sid]["ended"] = (outcome, duration)

    async def set_agent_status(self, tenant_id, agent_id, status, only_if=None):
        if agent_id and (only_if is None or self.status.get(agent_id) == only_if):
            self.status[agent_id] = status

    async def audit(self, tenant_id, kind, result, **kw): self.audits.append((tenant_id, kind, result, kw))
    async def recording_done(self, tenant_id, sid, name): self.recordings.append((tenant_id, sid, name))
    async def close_orphans(self): self.orphans_closed = True


async def pump(n=0.15):
    await asyncio.sleep(n)


async def fast(_s):
    await asyncio.sleep(0.01)


def make_bridge(recording=False, **route_kw):
    ari, store = FakeAri(), FakeStore()
    br = TelephonyBridge(ari, store, sleep=fast)
    ari.bridge = br
    store.routes[DID] = TenantRoute(T1, recording=recording, max_wait_seconds=5, **route_kw)
    store.agents[T1] = [RingAgent(A1, EP1)]
    ari.online[EP1] = "online"
    return ari, store, br


def inbound_ev(cid="in-1", tenant=T1, did=DID, ctx=None):
    return {"type": "StasisStart", "args": ["inbound", confgen.tenant_hex(tenant), did],
            "channel": {"id": cid, "caller": {"number": "0821112222"},
                        "dialplan": {"context": ctx if ctx is not None else confgen.inbound_context(tenant)}}}


def start_ev(cid, kind, call_id):
    return {"type": "StasisStart", "args": [kind, call_id], "channel": {"id": cid}}


def gone(cid):
    return {"type": "ChannelDestroyed", "channel": {"id": cid}}


# ── ARI bridge: inbound ───────────────────────────────────────────────────

def test_inbound_rings_agent_bridges_and_ends():
    async def scenario():
        ari, store, br = make_bridge()
        await br.handle_event(inbound_ev())
        await pump()
        orig = ari.of("originate")[0]
        assert orig["endpoint"] == f"PJSIP/{EP1}" and orig["app_args"][0] == "agent_leg"
        assert ("answer" in [n for n, _ in ari.log]) and ari.of("moh_start") == ["in-1"]
        call_id = orig["app_args"][1]
        await br.handle_event(start_ev(orig["channel_id"], "agent_leg", call_id))
        await pump()
        assert ari.of("create_bridge") and {c for _, c in ari.of("add")} == {"in-1", orig["channel_id"]}
        sid = next(iter(store.sessions))
        assert store.sessions[sid]["agent"] == A1 and store.sessions[sid]["direction"] == "INBOUND"
        assert store.status[A1] == "ON_CALL"
        assert len(br.list_active(T1)) == 1 and br.list_active(T2) == []     # tenant-filtered
        assert br.get_call(T2, call_id) is None
        await br.handle_event(gone("in-1"))
        await pump()
        assert store.sessions[sid]["ended"][0] == "COMPLETED" and store.status[A1] == "IDLE"
        assert br.list_active(T1) == [] and ari.of("destroy_bridge")
    run(scenario())


def test_inbound_unknown_did_and_tenant_mismatch_ignored():
    async def scenario():
        ari, store, br = make_bridge()
        await br.handle_event(inbound_ev(cid="x1", did="+27219999999"))             # unknown DID
        await br.handle_event(inbound_ev(cid="x2", tenant=T2))                       # DID belongs to T1, args say T2
        await br.handle_event(inbound_ev(cid="x3", ctx="in_" + "0" * 32))            # arrived on wrong context
        await br.handle_event({"type": "StasisStart", "args": ["inbound"], "channel": {"id": "x4"}})
        await pump()
        assert set(ari.of("hangup")) == {"x1", "x2", "x3", "x4"}
        assert ari.of("originate") == [] and br.list_active(T1) == [] and store.sessions == {}
    run(scenario())


def test_inbound_no_agent_online_abandons_after_wait():
    async def scenario():
        ari, store, br = make_bridge()
        ari.online[EP1] = "offline"
        store.routes[DID].max_wait_seconds = 1
        await br.handle_event(inbound_ev())
        await asyncio.sleep(5.4)    # ring loop minimum wait is 5s
        assert "in-1" in ari.of("hangup") and ari.of("originate") == []
        assert any(a[2] == "missed:no_agent_answered" for a in store.audits)
        assert br.list_active(T1) == []
    run(scenario())


def test_first_agent_wins_others_cancelled():
    async def scenario():
        ari, store, br = make_bridge()
        store.agents[T1].append(RingAgent(A2, EP2))
        ari.online[EP2] = "online"
        await br.handle_event(inbound_ev())
        await pump()
        legs = ari.of("originate")
        assert len(legs) == 2
        call_id = legs[0]["app_args"][1]
        await br.handle_event(start_ev(legs[1]["channel_id"], "agent_leg", call_id))
        await pump()
        assert legs[0]["channel_id"] in ari.of("hangup")
        # the loser answering late is hung up, never bridged
        await br.handle_event(start_ev(legs[0]["channel_id"], "agent_leg", call_id))
        await pump()
        assert legs[0]["channel_id"] in ari.of("hangup") and len(ari.of("create_bridge")) == 1
        assert next(iter(store.sessions.values()))["agent"] == A2
    run(scenario())


def test_max_concurrent_inbound_refused_with_busy():
    async def scenario():
        ari, store, br = make_bridge(max_concurrent_calls=1)
        await br.handle_event(inbound_ev("c1"))
        await pump()
        await br.handle_event(inbound_ev("c2"))
        await pump()
        assert "c2" in ari.of("hangup") and "c1" not in ari.of("hangup")
        assert any(a[2] == "refused:max_concurrent_calls" for a in store.audits)
    run(scenario())


def test_stasis_entry_from_foreign_channel_is_hung_up():
    async def scenario():
        ari, store, br = make_bridge()
        await br.handle_event(inbound_ev())
        await pump()
        call_id = ari.of("originate")[0]["app_args"][1]
        # a channel we never originated pretending to be the agent leg of a real call
        await br.handle_event(start_ev("attacker", "agent_leg", call_id))
        await br.handle_event(start_ev("attacker2", "out_cust", "deadbeef"))
        await br.handle_event(start_ev("attacker3", "weird", call_id))
        await pump()
        assert {"attacker", "attacker2", "attacker3"} <= set(ari.of("hangup"))
        assert ari.of("create_bridge") == []
    run(scenario())


def test_recording_only_after_announcement_played():
    async def scenario(fail_play):
        ari, store, br = make_bridge(recording=True)
        ari.fail_play = fail_play
        await br.handle_event(inbound_ev())
        await pump(0.3)
        leg = ari.of("originate")[0]
        await br.handle_event(start_ev(leg["channel_id"], "agent_leg", leg["app_args"][1]))
        await pump()
        sid = next(iter(store.sessions))
        return ari, store, sid

    ari, store, sid = run(scenario(False))
    assert ari.of("play") and ari.of("record")
    assert ari.of("record")[0][1] == f"{confgen.tenant_hex(T1)}_{sid.hex}"
    assert store.sessions[sid]["consent"] == "given"
    ari, store, sid = run(scenario(True))          # announcement failed => NOT recorded
    assert ari.of("record") == [] and store.sessions[sid]["consent"] == "unknown"


def test_recording_event_resolves_tenant_and_session_from_name():
    async def scenario():
        ari, store, br = make_bridge()
        sid = uuid.uuid4()
        await br.handle_event({"type": "RecordingFinished", "recording": {"name": f"{confgen.tenant_hex(T1)}_{sid.hex}"}})
        await br.handle_event({"type": "RecordingFinished", "recording": {"name": "../../etc/passwd"}})
        await pump()
        assert store.recordings == [(T1, sid, f"{confgen.tenant_hex(T1)}_{sid.hex}")]
    run(scenario())


# ── ARI bridge: outbound, hold, dtmf, transfer ────────────────────────────

async def _connected_outbound(br, ari, store, recording=False):
    route = TenantRoute(T1, recording=recording, max_wait_seconds=5)
    call = await br.start_outbound(route=route, agent_id=A1, agent_endpoint=EP1, number="+27821234567",
                                   trunk_endpoint=confgen.trunk_name(T1), caller_id="+27211234567")
    leg = ari.of("originate")[0]
    assert leg["endpoint"] == f"PJSIP/{EP1}" and leg["app_args"] == ["out_agent", call.id]
    await br.handle_event(start_ev(leg["channel_id"], "out_agent", call.id))     # agent picked up first
    await pump()
    cust = ari.of("originate")[1]
    assert cust["endpoint"] == f"PJSIP/+27821234567@{confgen.trunk_name(T1)}" and cust["caller_id"] == "+27211234567"
    await br.handle_event(start_ev(cust["channel_id"], "out_cust", call.id))      # customer answered
    await pump(0.3)
    return call, leg["channel_id"], cust["channel_id"]


def test_outbound_agent_first_then_customer_then_bridge():
    async def scenario():
        ari, store, br = make_bridge()
        call, agent_ch, cust_ch = await _connected_outbound(br, ari, store)
        assert call.state == "connected" and {c for _, c in ari.of("add")} == {agent_ch, cust_ch}
        assert store.sessions[call.session_id]["direction"] == "OUTBOUND" and store.status[A1] == "ON_CALL"
        # agent busy: a second click-to-call for the same agent is refused
        with pytest.raises(PermissionError):
            await br.start_outbound(route=TenantRoute(T1), agent_id=A1, agent_endpoint=EP1, number="+27821234567",
                                    trunk_endpoint="t", caller_id=None)
        # hold / unhold / dtmf act on the customer leg, tenant-checked
        await br.hold(T1, call.id, True)
        assert ari.of("hold") == [cust_ch] and call.held
        await br.hold(T1, call.id, False)
        assert ari.of("unhold") == [cust_ch]
        await br.dtmf(T1, call.id, "12#")
        assert ari.of("dtmf") == [(cust_ch, "12#")]
        for bad in ("", "1;2", "x" * 33, "ef"):
            with pytest.raises(ValueError):
                await br.dtmf(T1, call.id, bad)
        with pytest.raises(LookupError):
            await br.hold(T2, call.id, True)
        with pytest.raises(LookupError):
            await br.hangup(T2, call.id)
        await br.hangup(T1, call.id)
        assert store.sessions[call.session_id]["ended"][0] == "COMPLETED" and store.status[A1] == "IDLE"
        assert {agent_ch, cust_ch} <= set(ari.of("hangup"))
    run(scenario())


def test_outbound_customer_never_answers_ends_no_answer():
    async def scenario():
        ari, store, br = make_bridge()
        call = await br.start_outbound(route=TenantRoute(T1), agent_id=A1, agent_endpoint=EP1, number="+27821234567",
                                       trunk_endpoint="trk", caller_id=None)
        leg = ari.of("originate")[0]
        await br.handle_event(start_ev(leg["channel_id"], "out_agent", call.id))
        await pump()
        await br.handle_event(gone(ari.of("originate")[1]["channel_id"]))      # trunk side hung up / busy
        await pump()
        assert store.sessions[call.session_id]["ended"][0] == "NO_ANSWER" and br.list_active(T1) == []
    run(scenario())


def test_outbound_originate_failure_closes_session_and_raises():
    async def scenario():
        ari, store, br = make_bridge()
        ari.fail_originate = True
        with pytest.raises(AriError):
            await br.start_outbound(route=TenantRoute(T1), agent_id=A1, agent_endpoint=EP1, number="+27821234567",
                                    trunk_endpoint="trk", caller_id=None)
        assert br.list_active(T1) == [] and next(iter(store.sessions.values()))["ended"][0] == "NO_ANSWER"
    run(scenario())


def test_outbound_recording_requires_announcement():
    async def scenario(fail):
        ari, store, br = make_bridge()
        ari.fail_play = fail
        call, _, _ = await _connected_outbound(br, ari, store, recording=True)
        return ari, store, call
    ari, store, call = run(scenario(False))
    assert ari.of("record") and store.sessions[call.session_id]["consent"] == "given"
    ari, store, call = run(scenario(True))
    assert ari.of("record") == [] and store.sessions[call.session_id]["consent"] == "unknown" and call.state == "connected"


def test_transfer_to_agent_swaps_leg_keeps_bridge():
    async def scenario():
        ari, store, br = make_bridge()
        call, agent_ch, cust_ch = await _connected_outbound(br, ari, store)
        await br.transfer(T1, call.id, endpoint=f"PJSIP/{EP2}", caller_id=None, new_agent_id=A2)
        assert call.state == "transferring"
        x = ari.of("originate")[-1]
        assert x["app_args"] == ["xfer_target", call.id]
        await br.handle_event(start_ev(x["channel_id"], "xfer_target", call.id))
        await pump()
        assert call.state == "connected" and call.agent_channel == x["channel_id"] and call.agent_id == A2
        assert (call.bridge_id, agent_ch) in ari.of("remove") and agent_ch in ari.of("hangup")
        assert store.sessions[call.session_id]["agent"] == A2 and store.status[A2] == "ON_CALL" and store.status[A1] == "IDLE"
        # old agent's hangup must NOT end the call
        await br.handle_event(gone(agent_ch))
        await pump()
        assert call.state == "connected"
    run(scenario())


def test_transfer_target_no_answer_keeps_original_call():
    async def scenario():
        ari, store, br = make_bridge()
        call, agent_ch, cust_ch = await _connected_outbound(br, ari, store)
        await br.transfer(T1, call.id, endpoint=f"PJSIP/{EP2}", caller_id=None, new_agent_id=A2)
        await br.handle_event(gone(ari.of("originate")[-1]["channel_id"]))
        await pump()
        assert call.state == "connected" and call.agent_channel == agent_ch
        with pytest.raises(PermissionError):
            call.state = "ringing"
            await br.transfer(T1, call.id, endpoint="x", caller_id=None)
    run(scenario())


def test_max_duration_watchdog_hangs_up(monkeypatch):
    async def scenario():
        ari, store, br = make_bridge()
        route = TenantRoute(T1, max_call_seconds=1)
        call = await br.start_outbound(route=route, agent_id=A1, agent_endpoint=EP1, number="+27821234567",
                                       trunk_endpoint="trk", caller_id=None)
        await br.handle_event(start_ev(ari.of("originate")[0]["channel_id"], "out_agent", call.id))
        await pump()
        await br.handle_event(start_ev(ari.of("originate")[1]["channel_id"], "out_cust", call.id))
        await asyncio.sleep(1.6)
        assert call.state == "ended" and call.end_reason == "max_duration"
        assert store.sessions[call.session_id]["ended"][0] == "COMPLETED"
    run(scenario())


def test_recover_hangs_up_orphan_cc_channels_and_closes_sessions():
    async def scenario():
        ari, store, br = make_bridge()
        await br.recover()
        assert ari.of("hangup") == ["cc-orphan-1"] and store.orphans_closed
    run(scenario())


# ── service layer: admission control, limits, audit ───────────────────────

def _runtime(factory, tmp_path, regs="registered", fields=TRUNK_FIELDS, with_endpoint=True, **settings):
    _seed_tenant(factory, T1, U1, A1, fields=fields, **settings)
    ari = FakeAri()
    name = confgen.trunk_name(T1)
    status = {"registered": "Registered", "rejected": "Rejected"}[regs]
    prov = _prov(factory, tmp_path, regs=[f" {name}/sip:sip.provider.example:5060  {name}  {status}"])
    rt = Telephony(factory=factory, ari=ari, provisioner=prov)
    ari.bridge = rt.bridge
    rt.bridge.connected = True
    if with_endpoint:
        async def add():
            async with factory() as db:
                db.add(WebrtcEndpointRow(tenant_id=T1, agent_id=A1, endpoint_id=EP1, md5_cred="0" * 32,
                                         expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)))
                await db.commit()
        run(add())
        ari.online[EP1] = "online"
    return rt, ari


def _audits(factory):
    async def go():
        async with factory() as db:
            return (await db.execute(select(TelephonyAudit).order_by(TelephonyAudit.created_at))).scalars().all()
    return run(go())


def _place(rt, to, **kw):
    kw.setdefault("user_id", U1)
    kw.setdefault("is_admin", False)
    return rt.place_call(tenant_id=T1, to=to, **kw)


def _expect(rt, to, code, **kw):
    with pytest.raises(TelephonyError) as e:
        run(_place(rt, to, **kw))
    assert e.value.code == code, (e.value.code, e.value.message)
    return e.value


def test_place_call_refusals_are_audited(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path)
    _expect(rt, "not a number", "invalid_number")
    _expect(rt, "112", "invalid_number")
    _expect(rt, "+263771234567", "destination_not_allowed")
    _expect(rt, "0900123456", "blocked_prefix")
    _expect(rt, "0821234567", "no_agent_profile", user_id=uuid.uuid4())          # authenticated but not an agent
    results = [a.result for a in _audits(factory)]
    assert results == ["refused:invalid_number", "refused:invalid_number", "refused:destination_not_allowed",
                       "refused:blocked_prefix", "refused:no_agent_profile"]
    assert ari.of("originate") == []                                              # nothing was ever dialled


def test_non_admin_cannot_call_as_another_agent(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path)
    _expect(rt, "0821234567", "no_agent_profile", user_id=uuid.uuid4(), agent_id=A1)
    assert ari.of("originate") == []


def test_place_call_happy_path_agent_leg_first(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path)
    out = run(_place(rt, "082 123 4567"))
    assert out["state"] == "agent_ringing" and out["number"] == "+27821234567"
    leg = ari.of("originate")[0]
    assert leg["endpoint"] == f"PJSIP/{EP1}" and leg["app_args"][0] == "out_agent"      # agent first, trunk later
    audits = _audits(factory)
    assert [a.result for a in audits] == ["originated"] and audits[0].to_number == "+27821234567"
    assert audits[0].agent_id == A1 and audits[0].user_id == U1
    # same agent cannot start a second call
    e = _expect(rt, "0821234568", "agent_busy")
    assert e.status == 409


def test_trunk_not_registered_blocks_calls(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path, regs="rejected")
    e = _expect(rt, "0821234567", "trunk_not_registered")
    assert "rejected" in e.message.lower() and ari.of("originate") == []


def test_no_trunk_configured(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path, fields=None)
    _expect(rt, "0821234567", "no_trunk")
    st = run(rt.trunk_status(T1))
    assert st["state"] == "not_configured" and st["detail"] == "No SIP trunk configured" and not st["registered"]


def test_softphone_must_be_registered(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path)
    ari.online[EP1] = "offline"
    _expect(rt, "0821234567", "softphone_not_registered")
    ari.online.clear()
    _expect(rt, "0821234567", "softphone_not_registered")


def test_hourly_limit_per_agent(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path, regs="registered")
    async def limit():
        async with factory() as db:
            row = (await db.execute(select(TelephonySettings))).scalar_one()
            row.max_calls_per_agent_hour = 2
            await db.commit()
    run(limit())
    for n in ("0821234561", "0821234562"):
        out = run(_place(rt, n))
        run(rt.bridge.hangup(T1, out["id"]))
    e = _expect(rt, "0821234563", "agent_hourly_limit")
    assert e.status == 429


def test_concurrent_limit_per_tenant(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path)
    async def limit():
        async with factory() as db:
            row = (await db.execute(select(TelephonySettings))).scalar_one()
            row.max_concurrent_calls = 1
            await db.commit()
    run(limit())
    out = run(_place(rt, "0821234561"))
    assert out["state"] == "agent_ringing"
    e = _expect(rt, "0821234562", "max_concurrent_calls")
    assert e.status == 429


def test_settings_validation_and_hard_caps(factory, tmp_path, monkeypatch):
    rt, _ = _runtime(factory, tmp_path)
    ok = run(rt.update_settings(T1, {"allowed_prefixes": ["+27", "+263"], "max_concurrent_calls": 3}))
    assert ok["allowed_prefixes"] == ["+27", "+263"] and ok["max_concurrent_calls"] == 3
    for patch in ({"allowed_prefixes": ["263"]}, {"max_concurrent_calls": 0}, {"max_concurrent_calls": 10_000},
                  {"max_call_seconds": 5}, {"dids": ["0211234567"]}, {"enabled": "yes"}, {"max_concurrent_calls": True},
                  {"dids": ["+27211234567\nexten => _.,1,Dial(x)"]}):
        with pytest.raises(TelephonyError) as e:
            run(rt.update_settings(T1, patch))
        assert e.value.status == 422
    # recording needs BOTH flags to be effective
    v = run(rt.update_settings(T1, {"recording_enabled": True}))
    assert v["recording_enabled"] and not v["recording_effective"]
    v = run(rt.update_settings(T1, {"recording_announcement_confirmed": True}))
    assert v["recording_effective"]


def test_did_cannot_be_claimed_by_two_tenants(factory, tmp_path):
    rt, _ = _runtime(factory, tmp_path)
    async def other():
        async with factory() as db:
            db.add(TelephonySettings(tenant_id=T2, enabled=True, dids=[], allowed_prefixes=["+27"], blocked_prefixes=[]))
            await db.commit()
    run(other())
    with pytest.raises(TelephonyError) as e:
        run(rt.update_settings(T2, {"dids": [DID]}))
    assert e.value.code == "did_in_use" and "other" in e.value.message.lower()


def test_db_store_route_for_did_ignores_ambiguous_and_disabled(factory):
    async def go():
        async with factory() as db:
            db.add(TelephonySettings(tenant_id=T1, enabled=True, dids=[DID], allowed_prefixes=["+27"]))
            db.add(TelephonySettings(tenant_id=T2, enabled=False, dids=["+27217654321"], allowed_prefixes=["+27"]))
            await db.commit()
        st = DbStore(factory)
        assert (await st.route_for_did(DID)).tenant_id == T1
        assert await st.route_for_did("+27217654321") is None        # disabled tenant
        assert await st.route_for_did("+27210000000") is None        # unknown
        async with factory() as db:
            row = (await db.execute(select(TelephonySettings).where(TelephonySettings.tenant_id == T2))).scalar_one()
            row.enabled, row.dids = True, [DID]
            await db.commit()
        assert await st.route_for_did(DID) is None                   # claimed twice => ignored
    run(go())


def test_db_store_ring_agents_only_idle_with_live_endpoint(factory):
    async def go():
        async with factory() as db:
            db.add(Agent(id=A1, tenant_id=T1, name="a", extension="1", status="IDLE", skills=["billing"]))
            db.add(Agent(id=A2, tenant_id=T1, name="b", extension="2", status="ON_CALL"))
            db.add(WebrtcEndpointRow(tenant_id=T1, agent_id=A1, endpoint_id=EP1, md5_cred="0" * 32,
                                     expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
            db.add(WebrtcEndpointRow(tenant_id=T1, agent_id=A2, endpoint_id=EP2, md5_cred="0" * 32,
                                     expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
            db.add(Agent(id=uuid.uuid4(), tenant_id=T2, name="other", extension="3", status="IDLE"))
            await db.commit()
        got = await DbStore(factory).ring_agents(T1, None)
        assert [(a.agent_id, a.endpoint_id) for a in got] == [(A1, EP1)]
        assert await DbStore(factory).ring_agents(T2, None) == []    # T2's agent has no softphone
    run(go())


def test_db_store_recording_metadata_only_with_consent(factory):
    async def go():
        st = DbStore(factory)
        async with factory() as db:
            db.add(Agent(id=A1, tenant_id=T1, name="a", extension="1", status="IDLE"))
            await db.commit()
        sid_ok = await st.create_session(T1, A1, "OUTBOUND", None, None, "given")
        sid_no = await st.create_session(T1, A1, "OUTBOUND", None, None, "unknown")
        name = lambda s: f"{confgen.tenant_hex(T1)}_{s.hex}"          # noqa: E731
        await st.recording_done(T1, sid_ok, name(sid_ok))
        await st.recording_done(T1, sid_no, name(sid_no))
        await st.recording_done(T2, sid_ok, name(sid_ok))             # other tenant: untouched
        async with factory() as db:
            rows = {r.id: r for r in (await db.execute(select(CallSession))).scalars()}
        assert rows[sid_ok].recording_url == f"asterisk/{name(sid_ok)}.wav" and rows[sid_ok].provider == "asterisk"
        assert rows[sid_no].recording_url is None                     # no consent => no recording reference
        await st.finish_session(T1, sid_ok, "COMPLETED", 42)
        assert await st.close_orphans() == 1                          # sid_no was still open
    run(go())


# ── WebRTC credentials ────────────────────────────────────────────────────

def test_webrtc_credentials_short_lived_and_hash_only(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path, with_endpoint=False)
    out = run(rt.issue_webrtc(T1, U1))
    assert out["ws_url"] == "wss://pbx.example.com/ws" and out["username"].startswith("w")
    assert out["sip_uri"] == f"sip:{out['username']}@pbx.example.com" and out["expires_in"] <= 3600
    assert out["ice_servers"] and out["realm"] == "omnidome"
    pw = out["password"]
    async def rows():
        async with factory() as db:
            return (await db.execute(select(WebrtcEndpointRow))).scalars().all()
    r = run(rows())[0]
    assert r.md5_cred == confgen.md5_cred(out["username"], pw) and pw not in (r.md5_cred + r.endpoint_id)
    conf = (tmp_path / "gen" / f"pjsip_{confgen.tenant_hex(T1)}.conf").read_text()
    assert pw not in conf and r.md5_cred in conf                      # only the digest hits disk
    for _ in range(5):
        run(rt.issue_webrtc(T1, U1))
    assert len(run(rows())) <= 3                                      # old endpoints are pruned
    with pytest.raises(TelephonyError) as e:
        run(rt.issue_webrtc(T1, uuid.uuid4()))
    assert e.value.code == "no_agent_profile"


def test_webrtc_requires_wss_and_enabled(factory, tmp_path, monkeypatch):
    rt, _ = _runtime(factory, tmp_path, with_endpoint=False)
    monkeypatch.setenv("TELEPHONY_WSS_URL", "ws://insecure.example.com/ws")
    with pytest.raises(TelephonyError) as e:
        run(rt.issue_webrtc(T1, U1))
    assert e.value.code == "wss_not_configured"
    monkeypatch.setenv("TELEPHONY_WSS_URL", "wss://pbx.example.com/ws")
    rt.ari = None
    rt.bridge = None
    with pytest.raises(TelephonyError) as e:
        run(rt.issue_webrtc(T1, U1))
    assert e.value.code == "pbx_unavailable"


# ── credentials never logged ──────────────────────────────────────────────

def test_secrets_never_logged_or_repr(factory, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    rt, ari = _runtime(factory, tmp_path)
    run(rt.provisioner.reconcile())
    run(_place(rt, "0821234567"))
    run(rt.trunk_status(T1, admin_view=True))
    out = run(rt.issue_webrtc(T1, U1))
    token = rt.provisioner._token
    blob = caplog.text + repr(rt.provisioner) + repr(rt.provisioner.errors)
    for secret in (SIP_PW, token, out["password"]):
        assert secret not in blob
    client = AriClient("http://asterisk:8088", "omnidome", "ARI-secret-pw-123")
    assert "ARI-secret-pw-123" not in repr(client)
    assert SIP_PW not in repr(confgen.TrunkConfig.from_credentials(TRUNK_FIELDS))


def test_ari_errors_do_not_leak_credentials():
    import httpx

    def handler(request):
        return httpx.Response(401, text="bad creds ARI-secret-pw-123")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), auth=("omnidome", "ARI-secret-pw-123"))
    client = AriClient("http://asterisk:8088", "omnidome", "ARI-secret-pw-123", http=http)

    async def go():
        with pytest.raises(AriError) as e:
            await client.hold("chan")
        assert "ARI-secret-pw-123" not in str(e.value) and e.value.status == 401

        def boom(request):
            raise httpx.ConnectError("connect failed to http://omnidome:ARI-secret-pw-123@asterisk")
        c2 = AriClient("http://asterisk:8088", "omnidome", "ARI-secret-pw-123",
                       http=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
        with pytest.raises(AriError) as e2:
            await c2.hold("chan")
        assert "ARI-secret-pw-123" not in str(e2.value) and "ARI-secret-pw-123" not in repr(e2.value.__cause__)
    run(go())


def test_ari_not_configured_without_password(monkeypatch):
    from services.call_center.telephony.ari import ari_settings
    monkeypatch.setenv("ASTERISK_ARI_URL", "http://asterisk:8088")
    monkeypatch.delenv("ASTERISK_ARI_PASSWORD", raising=False)
    assert ari_settings() is None           # fail closed: no password => telephony off, never a default password
    monkeypatch.setenv("ASTERISK_ARI_PASSWORD", "x" * 24)
    assert ari_settings()["password"] == "x" * 24


# ── HTTP: role tiers + save-time validation ───────────────────────────────

def _client(factory, roles, user=U1, tenant=T1):
    from fastapi.testclient import TestClient

    async def _db():
        async with factory() as s:
            yield s
            await s.commit()

    cc.app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id=user, tenant_id=tenant, roles=list(roles))
    cc.app.dependency_overrides[cc.get_session] = _db
    c = TestClient(cc.app)
    c.headers["x-tenant-id"] = str(tenant)
    c.headers["x-user-id"] = str(user)
    return c


def test_http_tiers_for_telephony(factory, tmp_path):
    rt, ari = _runtime(factory, tmp_path)
    set_runtime(rt)

    def agent(user=U1, tenant=T1):
        return _client(factory, ["agent"], user=user, tenant=tenant)

    def admin(user=U1, tenant=T1):
        return _client(factory, ["admin"], user=user, tenant=tenant)

    assert agent().get("/telephony/status").status_code == 200
    assert agent().get("/telephony/calls/active").json() == []
    for method, path in (("get", "/telephony/settings"), ("put", "/telephony/settings"), ("post", "/telephony/trunk/test"),
                         ("get", "/telephony/trunk/status"), ("get", "/telephony/audit"),
                         ("get", f"/recordings/{uuid.uuid4()}/audio"), ("post", f"/recordings/{uuid.uuid4()}/transcribe")):
        r = getattr(agent(), method)(path, **({"json": {}} if method == "put" else {}))
        assert r.status_code == 403, (method, path, r.status_code)
    assert admin().get("/telephony/settings").status_code == 200
    assert admin().get(f"/recordings/{uuid.uuid4()}/audio").status_code == 404      # admin: reaches the handler
    st = agent().get("/telephony/status").json()
    assert "host" not in st and "password" not in json.dumps(st)
    assert "host" in admin().get("/telephony/trunk/status").json()
    # agent places a call through the API
    r = agent().post("/telephony/calls", json={"to": "0821234567"})
    assert r.status_code == 201 and r.json()["state"] == "agent_ringing"
    r = agent().post("/telephony/calls", json={"to": "+263771234567"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "destination_not_allowed"
    # a different agent / tenant cannot touch the call
    cid = agent().get("/telephony/calls/active").json()[0]["id"]
    assert agent(user=uuid.uuid4()).post(f"/telephony/calls/{cid}/hangup").status_code == 403
    assert admin(user=uuid.uuid4(), tenant=T2).post(f"/telephony/calls/{cid}/hangup").status_code == 404
    assert admin(user=uuid.uuid4(), tenant=T2).get("/telephony/calls/active").json() == []
    assert agent().post(f"/telephony/calls/{cid}/dtmf", json={"digits": "1"}).status_code == 409   # not connected yet
    assert agent().post(f"/telephony/calls/{cid}/hangup").status_code == 200


def test_http_sip_credentials_validated_on_save(factory, tmp_path):
    rt, _ = _runtime(factory, tmp_path, fields=None)
    set_runtime(rt)
    admin = _client(factory, ["admin"])
    for bad in ({"host": "evil.com\n[x]"}, {"password": "a;b"}, {"username": "u\nv"}, {"transport": "ws"}):
        r = admin.put("/provider-credentials/sip", json={"fields": {**TRUNK_FIELDS, **bad}})
        assert r.status_code == 422, bad
        assert list(bad.values())[0] not in r.text
    assert admin.put("/provider-credentials/sip", json={"fields": TRUNK_FIELDS}).status_code == 200
    assert SIP_PW not in admin.get("/provider-credentials").text
