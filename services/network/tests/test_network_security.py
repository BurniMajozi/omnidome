"""Network service: secrets at rest, CoA packets, notification honesty, role tiers.
Run: python -m pytest services/network/tests -q   (no Postgres needed)
"""
import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)

from services.common import secretbox  # noqa: E402
from services.network import access, radius_coa, secrets_migration  # noqa: E402
from services.network.models import (Base, NasClient, ONTProvisioningProfile, RadiusAccount,  # noqa: E402
                                     WiFiConfigProfile)
from services.network.schemas import NasClientRead, RadiusAccountRead  # noqa: E402


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture()
def db():
    eng = create_engine("sqlite://")
    tables = [RadiusAccount.__table__, ONTProvisioningProfile.__table__, WiFiConfigProfile.__table__,
              NasClient.__table__]
    Base.metadata.create_all(eng, tables=tables)
    with Session(eng) as s:
        yield s


# ── secrets ────────────────────────────────────────────────────────────────

def test_roundtrip_and_hash():
    tok = secretbox.encrypt("s3cret-pw")
    assert "s3cret-pw" not in tok and secretbox.decrypt(tok) == "s3cret-pw"
    h = secretbox.hash_password("s3cret-pw", iterations=1000)
    assert "s3cret-pw" not in h and secretbox.verify_password("s3cret-pw", h)
    assert not secretbox.verify_password("x", h)


def test_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY")
    with pytest.raises(secretbox.SecretsUnavailable):
        secretbox.encrypt("x")
    assert not secretbox.is_configured()
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(secretbox.SecretsUnavailable):
        secretbox.encrypt("x")


def _seed_plaintext(db):
    svc = uuid.uuid4()
    db.add(RadiusAccount(tenant_id=uuid.uuid4(), service_id=svc, username="u1", password_hash="PLAINTEXT-PW",
                         profile_name="p"))
    db.add(ONTProvisioningProfile(tenant_id=uuid.uuid4(), service_id=svc, loid_password="LOID-PW"))
    db.add(WiFiConfigProfile(tenant_id=uuid.uuid4(), service_id=svc, passphrase="WIFI-PW",
                             guest_ssid_passphrase="G-PW"))
    db.commit()


def test_backfill_encrypts_in_place(db):
    _seed_plaintext(db)
    stats = secrets_migration.backfill_plaintext(db)
    db.commit()
    assert stats["radius"] == 1 and stats["ont"] == 1 and stats["wifi"] == 1
    a = db.query(RadiusAccount).one()
    assert a.password_hash != "PLAINTEXT-PW" and secretbox.is_hashed(a.password_hash)
    assert secretbox.decrypt(a.password_enc) == "PLAINTEXT-PW"
    o = db.query(ONTProvisioningProfile).one()
    assert o.loid_password is None and secretbox.decrypt(o.loid_password_enc) == "LOID-PW"
    w = db.query(WiFiConfigProfile).one()
    assert w.passphrase is None and w.guest_ssid_passphrase is None
    assert secretbox.decrypt(w.passphrase_enc) == "WIFI-PW"
    assert secretbox.decrypt(w.guest_ssid_passphrase_enc) == "G-PW"
    assert secrets_migration.backfill_plaintext(db) == {"radius": 0, "ont": 0, "wifi": 0, "skipped_no_key": 0}


def test_backfill_refuses_without_key(db, monkeypatch):
    _seed_plaintext(db)
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY")
    stats = secrets_migration.backfill_plaintext(db)
    assert stats["skipped_no_key"] == 3 and stats["radius"] == 0
    assert db.query(RadiusAccount).one().password_hash == "PLAINTEXT-PW"  # untouched, startup not failed


def test_no_secret_in_responses():
    acct = RadiusAccount(id=uuid.uuid4(), tenant_id=uuid.uuid4(), service_id=uuid.uuid4(), username="u",
                         password_hash=secretbox.hash_password("PW-VALUE", iterations=1000),
                         password_enc=secretbox.encrypt("PW-VALUE"), profile_name="p", framing_protocol="PPPoE",
                         status="active")
    acct.created_at = acct.updated_at = datetime.utcnow()
    dumped = RadiusAccountRead.model_validate(acct).model_dump_json()
    assert "PW-VALUE" not in dumped and "pbkdf2" not in dumped and "password_enc" not in dumped
    assert '"has_password":true' in dumped and "••••" in dumped
    nas = NasClient(id=uuid.uuid4(), tenant_id=uuid.uuid4(), name="n", ip_address="10.0.0.1",
                    shared_secret_enc=secretbox.encrypt("NAS-SECRET"), coa_port=3799)
    nas.created_at = datetime.utcnow()
    nd = NasClientRead.model_validate(nas).model_dump_json()
    assert "NAS-SECRET" not in nd and "shared_secret_enc" not in nd


# ── CoA ────────────────────────────────────────────────────────────────────

def test_disconnect_request_packet_and_authenticator():
    secret = b"testing123"
    pkt = radius_coa.build_disconnect_request(secret, 7, username="alice", nas_ip="192.0.2.1")
    assert pkt[0] == 40 and pkt[1] == 7 and int.from_bytes(pkt[2:4], "big") == len(pkt)
    attrs = pkt[20:]
    assert attrs[:7] == bytes([1, 7]) + b"alice"                      # User-Name
    assert attrs[7:13] == bytes([4, 6, 192, 0, 2, 1])                  # NAS-IP-Address
    expect = hashlib.md5(pkt[:4] + b"\x00" * 16 + attrs + secret).digest()
    assert pkt[4:20] == expect


def test_response_verification_ack_nak_and_forgery():
    secret = b"testing123"
    pkt = radius_coa.build_disconnect_request(secret, 9, username="bob")
    ra = radius_coa.request_authenticator(pkt)
    ack = radius_coa.build_response(radius_coa.DISCONNECT_ACK, 9, ra, secret)
    nak = radius_coa.build_response(radius_coa.DISCONNECT_NAK, 9, ra, secret)
    assert radius_coa.verify_response(ack, ra, 9, secret) == 41
    assert radius_coa.verify_response(nak, ra, 9, secret) == 42
    assert radius_coa.verify_response(ack, ra, 9, b"wrong") is None
    assert radius_coa.verify_response(ack, ra, 10, secret) is None


def test_send_disconnect_against_fake_nas():
    import socket
    import threading
    secret = b"s3cretNAS"
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    def serve(code):
        data, addr = srv.recvfrom(4096)
        srv.sendto(radius_coa.build_response(code, data[1], data[4:20], secret), addr)

    for code, outcome in ((radius_coa.DISCONNECT_ACK, "ACK"), (radius_coa.DISCONNECT_NAK, "NAK")):
        t = threading.Thread(target=serve, args=(code,))
        t.start()
        assert radius_coa.send_disconnect("127.0.0.1", port, secret, username="a", timeout=2).outcome == outcome
        t.join()
    srv.close()
    res = radius_coa.send_disconnect("127.0.0.1", port, secret, username="a", timeout=0.2, retries=0)
    assert res.outcome in {"TIMEOUT", "ERROR"}


# ── notifications honesty ──────────────────────────────────────────────────

def _notif(channel, recipient="x@example.org"):
    return SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), channel=channel, recipient=recipient,
                           title="t", message="m", severity="info", trigger_type="x", status="pending",
                           error_message=None, sent_at=None)


def _conn_session():
    eng = create_engine("sqlite://")
    return SimpleNamespace(connection=lambda: eng.connect())


def test_notifications_never_claim_sent_without_delivery(monkeypatch):
    from services.network.routes import notifications as n
    monkeypatch.setattr(n.agentmail, "is_configured", lambda *a, **k: False)
    for ch, expect in (("sms", "queued_not_sent"), ("push", "queued_not_sent"), ("email", "skipped_no_provider")):
        obj = _notif(ch)
        asyncio.run(n.deliver_notification(_conn_session(), obj))
        assert obj.status == expect and obj.sent_at is None and "not sent" in obj.error_message
    obj = _notif("in_app")
    asyncio.run(n.deliver_notification(_conn_session(), obj))
    assert obj.status == "sent"


def test_webhook_only_public_urls_and_real_post(monkeypatch):
    from services.network.routes import notifications as n
    posted = []

    async def poster(url, payload):
        posted.append(url)
        return 200

    bad = _notif("webhook", "http://169.254.169.254/latest")
    asyncio.run(n.deliver_notification(_conn_session(), bad, webhook_poster=poster))
    assert bad.status == "failed" and not posted
    monkeypatch.setattr(n, "_webhook_allowed", lambda u: u)
    ok = _notif("webhook", "https://hooks.example.org/x")
    asyncio.run(n.deliver_notification(_conn_session(), ok, webhook_poster=poster))
    assert ok.status == "sent" and posted == ["https://hooks.example.org/x"]

    async def p500(u, p):
        return 500
    fail = _notif("webhook", "https://hooks.example.org/x")
    asyncio.run(n.deliver_notification(_conn_session(), fail, webhook_poster=p500))
    assert fail.status == "failed"


def test_email_suppressed_not_sent(monkeypatch):
    from services.network.routes import notifications as n
    monkeypatch.setattr(n.suppression, "filter_suppressed_sync", lambda c, t, e: ([], list(e)))
    sent = []

    async def sender(*a, **k):
        sent.append(a)
    obj = _notif("email")
    asyncio.run(n.deliver_notification(_conn_session(), obj, email_sender=sender))
    assert obj.status == "dismissed" and not sent


# ── role tiers ─────────────────────────────────────────────────────────────

def _auth(*roles, admin=False):
    return SimpleNamespace(roles=list(roles), permissions=[], is_platform_admin=admin)


@pytest.mark.parametrize("method,path,tier", [
    ("GET", "/radius/accounts", "viewer"),
    ("POST", "/radius/accounts", "admin"),
    ("PUT", "/radius/accounts/abc", "admin"),
    ("POST", "/radius/nas", "admin"),
    ("DELETE", "/radius/nas/abc", "admin"),
    ("POST", "/radius/accounts/abc/disconnect", "operator"),
    ("POST", "/devices", "admin"),
    ("POST", "/devices/abc/heartbeat", "operator"),
    ("POST", "/services/abc/terminate", "admin"),
    ("POST", "/services/suspend-by-customer", "operator"),
    ("POST", "/performance/sla-profiles", "admin"),
    ("POST", "/network/wifi-config/abc/push", "operator"),
])
def test_required_tier(method, path, tier):
    assert access.required_tier(method, path) == tier


def test_tier_enforcement(monkeypatch):
    monkeypatch.setenv("NETWORK_ENFORCE_ROLES", "true")
    assert access.has_tier(_auth(), "viewer")
    assert not access.has_tier(_auth("member"), "operator")
    assert access.has_tier(_auth("technician"), "operator")
    assert not access.has_tier(_auth("technician"), "admin")
    assert access.has_tier(_auth("admin"), "admin")
    assert access.has_tier(_auth(admin=True), "admin")
    monkeypatch.setenv("NETWORK_ENFORCE_ROLES", "false")
    assert access.has_tier(_auth(), "admin")
