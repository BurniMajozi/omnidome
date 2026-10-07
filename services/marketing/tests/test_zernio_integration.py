"""Zernio integration tests: OmniDome-hosted connect flow, posts/scheduling/media, campaigns + audiences,
ads, WhatsApp sender status, lead forms. The provider and the DB are faked (no network, no Postgres).

    python -m pytest services/marketing/tests/test_zernio_integration.py -q
"""
import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from services.common.auth import AuthContext, get_auth_context  # noqa: E402
from services.marketing import audience_members as am  # noqa: E402
from services.marketing import main as mk  # noqa: E402
from services.marketing import zernio_ads as ads  # noqa: E402
from services.marketing import zernio_connect as zc  # noqa: E402
from services.marketing import zernio_errors as zerr  # noqa: E402
from services.marketing import zernio_leads as leads  # noqa: E402
from services.marketing import zernio_posts as zp  # noqa: E402
from services.marketing.zernio_client import ZernioClient, ZernioError  # noqa: E402

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
USER = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


# ───────────────────────────── fakes ─────────────────────────────


class Rows:
    """Result object covering the SQLAlchemy surface the code under test uses."""

    def __init__(self, rows=None, scalar=None, rowcount=1):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows, first=lambda: self._rows[0] if self._rows else None)

    def first(self):
        return tuple(self._rows[0].values()) if self._rows else None

    def all(self):
        return [tuple(r.values()) for r in self._rows]

    def scalar(self):
        return self._scalar


class ScriptedEngine:
    """get_engine() stand-in. `handlers` = [(substring, callable(params)->Rows)]; every statement is logged."""

    def __init__(self, handlers=None):
        self.handlers = handlers or []
        self.log = []

    @contextmanager
    def begin(self):
        yield self

    connect = begin

    def execute(self, stmt, params=None):
        q = " ".join(str(stmt).split())
        self.log.append((q, params))
        for key, fn in self.handlers:
            if key in q:
                return fn(params or {})
        return Rows()


class FakeZernio:
    def __init__(self):
        self.calls = []
        self.profile_accounts = []  # accounts GET /accounts?profileId returns
        self.fail = None  # ZernioError to raise from the next mutating call

    def _rec(self, name, **kw):
        self.calls.append((name, kw))
        if self.fail is not None:
            exc, self.fail = self.fail, None
            raise exc

    async def start_connect(self, platform, profile_id, redirect_url, **kw):
        self._rec("start_connect", platform=platform, profile_id=profile_id, redirect_url=redirect_url, **kw)
        return {"authUrl": f"https://www.example-platform.com/oauth/{platform}?state=zz"}

    async def list_profile_accounts(self, profile_id, category=None):
        self._rec("list_profile_accounts", profile_id=profile_id)
        return self.profile_accounts

    async def connect_get(self, path, params=None, connect_token=None):
        self._rec("connect_get", path=path, params=params, connect_token=connect_token)
        if path == "facebook/select-page":
            return {"pages": [{"id": "p1", "name": "Acme Fibre", "access_token": "PAGE-SECRET", "category": "ISP"},
                              {"id": "p2", "name": "Acme Sales", "access_token": "PAGE-SECRET-2"}]}
        return {}

    async def connect_post(self, path, body, connect_token=None):
        self._rec("connect_post", path=path, body=body, connect_token=connect_token)
        if path == "facebook/select-page":
            return {"message": "ok", "account": {"accountId": "acc-fb", "platform": "facebook", "username": "acme"}}
        return {}

    async def disconnect_account(self, account_id):
        self._rec("disconnect_account", account_id=account_id)
        return {}

    async def publish_content(self, content, platforms, **kw):
        self._rec("publish_content", content=content, platforms=platforms, **kw)
        if kw.get("is_draft"):
            status = "draft"
        elif kw.get("publish_now"):
            status = "published"
        else:
            status = "scheduled"
        return {"_id": "zpost1", "status": status,
                "platforms": [{"platform": p["platform"], "accountId": p["accountId"], "status": status} for p in platforms]}

    async def ads_list_ad_accounts(self, account_id, limit=None):
        self._rec("ads_list_ad_accounts", account_id=account_id)
        return [{"id": "act_1", "name": "Acme Ads", "currency": "ZAR", "minimumDailyBudget": 50, "accountStatus": 1}]

    async def ads_create(self, body, idempotency_key=None):
        self._rec("ads_create", body=body, idempotency_key=idempotency_key)
        if body.get("validateOnly"):
            return {"validateOnly": True, "results": [{"node": "campaign", "status": "validated"}]}
        return [{"ad": {"_id": "ad-1", "name": body["name"], "platform": "facebook", "status": "paused",
                        "platformCampaignId": "c1", "platformAdSetId": "s1", "platformAdId": "a1"}}]

    async def whatsapp_number_info(self, account_id):
        self._rec("whatsapp_number_info", account_id=account_id)
        return {"phone": {"display_phone_number": "+27 82 000 0000", "verified_name": "Acme Fibre",
                          "name_status": "APPROVED", "quality_rating": "GREEN", "messaging_limit_tier": "TIER_1K",
                          "status": "CONNECTED", "platform_type": "CLOUD_API"},
                "waba": {"name": "Acme WABA", "business_verification_status": "not_verified"}}

    async def lead_forms_list(self, account_id, **kw):
        self._rec("lead_forms_list", account_id=account_id, **kw)
        return {"forms": [{"id": "f1", "name": "Fibre signup", "status": "ACTIVE", "questions": [{"type": "EMAIL"}]}],
                "pagination": {"hasMore": False, "cursor": None}}

    async def leads_list(self, **kw):
        self._rec("leads_list", **kw)
        return {"leads": [{"id": "l1", "leadgenId": "g1", "formId": "f1", "formName": "Fibre signup", "adId": "a1",
                           "fields": {"email": "x@y.co"}, "createdTime": "2026-10-01T10:00:00Z"}],
                "pagination": {"hasMore": False, "cursor": None}}


def auth_ctx(roles=("admin",), user=USER, tenant=TENANT):
    return AuthContext(user_id=user, tenant_id=tenant, roles=list(roles), permissions=[], rbac_loaded=True)


@pytest.fixture
def env(monkeypatch):
    for k in ("ZERNIO_API_KEY", "MARKETING_CONNECT_STATE_SECRET", "MARKETING_CONNECT_CALLBACK_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ZERNIO_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OMNIDOME_PUBLIC_URL", "https://app.omnidome.test")
    monkeypatch.setattr(mk.guard, "is_licensed", lambda: True)
    monkeypatch.setattr(mk.guard, "enforce_modules", False)
    monkeypatch.setattr(mk, "_ensure_marketing_tables", lambda e: None)
    return monkeypatch


@pytest.fixture
def api(env):
    fake = FakeZernio()
    env.setattr(mk, "get_zernio_client", lambda: fake)

    async def ensure_profile(tenant_id):
        return "prof-1"

    env.setattr(mk, "_ensure_tenant_profile", ensure_profile)
    env.setattr(mk, "_get_tenant_profile", lambda t: "prof-1")
    mapped = []
    env.setattr(mk, "_upsert_connected_account", lambda tid, pid, acct, status="connected": mapped.append((tid, pid, acct, status)))
    # in-memory connect-session store
    sessions = {}
    env.setattr(zc, "store_create", lambda row: sessions.__setitem__(row["nonce"], {
        **row, "reconnect_account_id": row["reconnect"], "options": json.loads(row["options"]) if isinstance(row["options"], str) else row["options"],
        "status": "pending", "pending_enc": None}))
    env.setattr(zc, "store_get", lambda n: sessions.get(n))
    env.setattr(zc, "store_update", lambda n, **f: sessions[n].update(f))
    ctx = auth_ctx()
    mk.app.dependency_overrides[get_auth_context] = lambda: ctx
    client = TestClient(mk.app)
    yield SimpleNamespace(c=client, z=fake, sessions=sessions, mapped=mapped, env=env, ctx=ctx)
    mk.app.dependency_overrides.clear()


def start(api, platform="facebook", **extra):
    r = api.c.post("/social/connect/start", json={"platform": platform, **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ═════════════════════ 1. connect flow ═════════════════════


def test_start_uses_omnidome_redirect_never_zernio(api):
    body = start(api, "linkedin")
    call = [c for c in api.z.calls if c[0] == "start_connect"][-1][1]
    assert call["redirect_url"].startswith("https://app.omnidome.test/dashboard/marketing/connect/callback?st=")
    assert "zernio.com" not in call["redirect_url"] and "zernio.com" not in body["auth_url"]
    assert call["profile_id"] == "prof-1"  # the tenant's own profile, never a shared/global one
    assert call["headless"] is True  # linkedin needs an org picker, rendered by OmniDome
    assert body["state"] in call["redirect_url"].replace("%2E", ".")
    assert len(call["redirect_url"]) <= 240  # X caps the encoded redirect at 258


def test_start_oauth_only_platform_is_not_headless_and_ads_use_ads_endpoint(api):
    start(api, "tiktok")
    assert [c for c in api.z.calls if c[0] == "start_connect"][-1][1]["headless"] is False
    start(api, "google_ads", category="ads")
    last = [c for c in api.z.calls if c[0] == "start_connect"][-1][1]
    assert last["ads"] is True and last["platform"] == "googleads"


def test_start_rejects_unknown_platform_and_wrong_flow(api):
    assert api.c.post("/social/connect/start", json={"platform": "myspace"}).status_code == 422
    assert api.c.post("/social/connect/start", json={"platform": "bluesky"}).status_code == 422  # credentials flow
    assert api.c.post("/social/connect/start", json={"platform": "whatsapp"}).status_code == 422  # embedded signup


def test_start_requires_admin_role(api):
    api.c.app.dependency_overrides[get_auth_context] = lambda: auth_ctx(roles=("viewer",))
    assert api.c.post("/social/connect/start", json={"platform": "tiktok"}).status_code == 403


def test_start_requires_configured_callback_in_production(api, monkeypatch):
    monkeypatch.delenv("OMNIDOME_PUBLIC_URL")
    monkeypatch.setenv("ENVIRONMENT", "production")
    r = api.c.post("/social/connect/start", json={"platform": "tiktok"})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "callback_not_configured"


def test_legacy_connect_route_returns_auth_url_and_state(api):
    r = api.c.get("/social/accounts/connect/instagram", params={"redirect_url": "https://evil.example/steal"})
    assert r.status_code == 200
    j = r.json()
    assert j["auth_url"].startswith("https://www.example-platform.com/") and j["state"]
    call = [c for c in api.z.calls if c[0] == "start_connect"][-1][1]
    assert "evil.example" not in call["redirect_url"]  # caller-supplied redirect ignored


def test_complete_direct_success_verifies_account_in_tenant_profile(api):
    st = start(api, "tiktok")["state"]
    api.z.profile_accounts = [{"_id": "acc-tt", "platform": "tiktok", "username": "acme", "profileId": "prof-1"}]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {
        "connected": "tiktok", "profileId": "prof-1", "accountId": "acc-tt", "username": "acme"}})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "connected" and r.json()["accounts"][0]["account_id"] == "acc-tt"
    assert api.mapped and api.mapped[0][0] == str(TENANT) and api.mapped[0][2]["accountId"] == "acc-tt"
    # a second completion of the same state is refused (replay)
    again = api.c.post("/social/connect/complete", json={"state": st, "params": {"connected": "tiktok", "accountId": "acc-tt"}})
    assert again.status_code == 409


def test_complete_rejects_account_id_not_in_tenant_profile(api):
    st = start(api, "tiktok")["state"]
    api.z.profile_accounts = [{"_id": "acc-mine", "platform": "tiktok", "profileId": "prof-1"}]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {"connected": "tiktok", "accountId": "acc-of-another-tenant"}})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "account_not_in_tenant"
    assert api.mapped == []


def test_complete_rejects_profile_mismatch(api):
    st = start(api, "tiktok")["state"]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {"connected": "tiktok", "profileId": "someone-elses", "accountId": "x"}})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "profile_mismatch"


def test_state_is_bound_to_user_and_tenant_and_ttl(api):
    st = start(api, "tiktok")["state"]
    params = {"connected": "tiktok", "accountId": "a"}
    # different user, same tenant
    api.c.app.dependency_overrides[get_auth_context] = lambda: auth_ctx(user=uuid.uuid4())
    assert api.c.post("/social/connect/complete", json={"state": st, "params": params}).status_code == 403
    # different tenant
    api.c.app.dependency_overrides[get_auth_context] = lambda: auth_ctx(tenant=OTHER)
    assert api.c.post("/social/connect/complete", json={"state": st, "params": params}).status_code == 403
    api.c.app.dependency_overrides[get_auth_context] = lambda: api.ctx
    # tampered MAC / garbage
    nonce = st.split(".")[0]
    assert api.c.post("/social/connect/complete", json={"state": nonce + ".AAAAAAAAAAAAAAAAAAAA", "params": params}).status_code == 400
    assert api.c.post("/social/connect/complete", json={"state": "nope", "params": params}).status_code == 400
    # expired
    api.sessions[nonce]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    r = api.c.post("/social/connect/complete", json={"state": st, "params": params})
    assert r.status_code == 400  # MAC covers the expiry, so editing it also invalidates the state


def test_expired_state_is_refused(api, monkeypatch):
    st = start(api, "tiktok")["state"]
    real_now = zc._now
    monkeypatch.setattr(zc, "_now", lambda: real_now() + timedelta(minutes=31))
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {"connected": "tiktok", "accountId": "a"}})
    assert r.status_code == 400 and r.json()["detail"]["error"] == "state_expired"


def test_complete_passes_through_provider_error(api):
    st = start(api, "tiktok")["state"]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {
        "error": "oauth_denied", "platform": "tiktok", "error_message": "You cancelled", "is_user_fixable": "true"}})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "error" and j["error"] == "oauth_denied" and j["user_fixable"] is True


def test_selection_flow_strips_tokens_and_validates_choice(api):
    from cryptography.fernet import Fernet
    api.env.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    st = start(api, "facebook")["state"]
    profile = json.dumps({"id": "u1", "name": "Pat"})
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {
        "profileId": "prof-1", "tempToken": "TEMP-TOKEN", "step": "select_page", "connect_token": "CT", "userProfile": profile}})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "selection_required" and j["step"] == "select_page"
    assert [o["id"] for o in j["options"]] == ["p1", "p2"]
    blob = json.dumps(j)
    assert "PAGE-SECRET" not in blob and "TEMP-TOKEN" not in blob and "access_token" not in blob
    # the temp token never leaves the server unencrypted
    stored = api.sessions[st.split(".")[0]]["pending_enc"]
    assert stored and "TEMP-TOKEN" not in stored
    # a page that was not offered is refused
    bad = api.c.post("/social/connect/select", json={"state": st, "selection_ids": ["p-not-offered"]})
    assert bad.status_code == 422 and bad.json()["detail"]["error"] == "invalid_selection"
    # a valid pick connects, verified against the tenant profile
    api.z.profile_accounts = [{"_id": "acc-fb", "platform": "facebook", "username": "acme", "profileId": "prof-1"}]
    ok = api.c.post("/social/connect/select", json={"state": st, "selection_ids": ["p1"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "connected"
    post = [c for c in api.z.calls if c[0] == "connect_post"][-1][1]
    assert post["body"]["pageId"] == "p1" and post["body"]["tempToken"] == "TEMP-TOKEN" and post["connect_token"] == "CT"
    assert api.sessions[st.split(".")[0]]["pending_enc"] is None  # cleared after use


def test_selection_without_secret_key_fails_closed(api):
    api.env.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
    st = start(api, "facebook")["state"]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {"tempToken": "T", "step": "select_page", "userProfile": "{}"}})
    assert r.status_code == 503 and r.json()["detail"]["error"] == "secrets_unavailable"


def test_meta_ads_connect_auto_selects_first_page(api):
    api.env.setenv("SECRETS_ENCRYPTION_KEY", __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())
    st = start(api, "meta_ads", category="ads")["state"]

    async def post(path, body, connect_token=None):
        api.z.calls.append(("connect_post", {"path": path, "body": body, "connect_token": connect_token}))
        return {"account": {"accountId": "acc-fb"}, "adsAccountId": "acc-metaads"}

    api.z.connect_post = post
    api.z.profile_accounts = [{"_id": "acc-fb", "platform": "facebook", "profileId": "prof-1"},
                              {"_id": "acc-metaads", "platform": "metaads", "profileId": "prof-1"}]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {
        "tempToken": "T", "step": "select_page", "userProfile": json.dumps({"id": "1"})}})
    assert r.status_code == 200 and r.json()["status"] == "connected"
    assert {a["account_id"] for a in r.json()["accounts"]} == {"acc-fb", "acc-metaads"}


def test_disconnect_only_tenant_accounts(api):
    api.z.profile_accounts = [{"_id": "mine", "platform": "tiktok", "profileId": "prof-1"}]
    assert api.c.delete("/social/connect/accounts/theirs").status_code == 404
    assert [c for c in api.z.calls if c[0] == "disconnect_account"] == []
    assert api.c.delete("/social/connect/accounts/mine").status_code == 200
    assert api.mapped[-1][3] == "disconnected"


def test_user_profile_double_encoding_decoded():
    from urllib.parse import quote
    raw = quote(json.dumps({"id": "7", "name": "Pat"}))
    assert zc.decode_user_profile(raw) == {"id": "7", "name": "Pat"}
    assert zc.decode_user_profile(json.dumps({"a": 1})) == {"a": 1}
    assert zc.decode_user_profile(None) is None


def test_safe_return_to():
    assert zc.safe_return_to("/dashboard/marketing") == "/dashboard/marketing"
    for bad in ("https://evil.example", "//evil.example", "javascript:alert(1)", "/ok\\evil", "/a\nb"):
        assert zc.safe_return_to(bad) is None


# ═════════════════════ client wire format ═════════════════════


class CapturingClient(ZernioClient):
    def __init__(self):
        super().__init__(api_key="k")
        self.sent = []

    async def _request(self, method, path, params=None, json_data=None, headers=None):
        self.sent.append({"method": method, "path": path, "params": params, "json": json_data, "headers": headers})
        return {"post": {"_id": "p1", "status": "scheduled"}}


def run(coro):
    return asyncio.run(coro)


def test_publish_content_uses_documented_field_names():
    c = CapturingClient()
    run(c.publish_content("hi", [{"platform": "facebook", "accountId": "a1"}], publish_now=False,
                          schedule_date="2026-12-01T10:00:00Z", media_urls=["https://x/y.png", "https://x/v.mp4"],
                          timezone="Africa/Johannesburg", idempotency_key="k-1"))
    sent = c.sent[0]
    body = sent["json"]
    assert body["scheduledFor"] == "2026-12-01T10:00:00Z" and "scheduleDate" not in body  # the old, ignored name
    assert body["mediaItems"] == [{"type": "image", "url": "https://x/y.png"}, {"type": "video", "url": "https://x/v.mp4"}]
    assert "mediaUrls" not in body and "publishNow" not in body and "isDraft" not in body
    assert body["timezone"] == "Africa/Johannesburg"
    assert sent["headers"] == {"Idempotency-Key": "k-1"}


def test_publish_content_intents_and_precedence():
    c = CapturingClient()
    run(c.publish_content("a", [{"platform": "x", "accountId": "1"}], publish_now=True))
    assert c.sent[-1]["json"]["publishNow"] is True and "scheduledFor" not in c.sent[-1]["json"]
    run(c.publish_content("a", [{"platform": "x", "accountId": "1"}], publish_now=False, is_draft=True, schedule_date="2026-12-01T00:00:00Z"))
    assert c.sent[-1]["json"] == {"platforms": [{"platform": "x", "accountId": "1"}], "content": "a", "isDraft": True}
    run(c.publish_content("a", [{"platform": "x", "accountId": "1"}], publish_now=False, queued_from_profile="prof", queue_id="q9"))
    assert c.sent[-1]["json"]["queuedFromProfile"] == "prof" and c.sent[-1]["json"]["queueId"] == "q9"
    run(c.publish_content("a", [{"platform": "x", "accountId": "1"}], publish_now=False))  # no intent -> draft, never an accidental publish
    assert c.sent[-1]["json"]["isDraft"] is True


def test_start_connect_sends_redirect_headless_and_ads_path():
    c = CapturingClient()
    run(c.start_connect("facebook", "prof", "https://app/cb?st=1", headless=True, ads=True, login_mode="business",
                        ad_account_ids=["act_1", "act_2"]))
    s = c.sent[0]
    assert s["path"] == "/connect/facebook/ads"
    assert s["params"]["redirect_url"] == "https://app/cb?st=1" and s["params"]["headless"] == "true"
    assert s["params"]["adAccountIds"] == "act_1,act_2" and s["params"]["loginMode"] == "business"


# ═════════════════════ 2. posts ═════════════════════


def test_status_normalisation_and_filters():
    assert zp.norm_status("SCHEDULED") == "scheduled" and zp.norm_status("Queued") == "scheduled"
    assert zp.norm_status("bogus") == "draft" and zp.norm_status(None) == "draft"
    assert zp.parse_status_filter("Scheduled, DRAFT") == (["scheduled", "draft"], False)
    assert zp.parse_status_filter("queued") == (["scheduled"], True)
    assert zp.parse_status_filter("") == (None, False)
    assert zp.derive_intent("published", None, None) == "now"
    assert zp.derive_intent("scheduled", None, uuid.uuid4()) == "queue"
    assert zp.derive_intent("scheduled", None, None) == "schedule"
    assert zp.derive_intent("draft", None, None) == "draft"


def test_schedule_time_must_be_in_future():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        zp.check_schedule_time(now - timedelta(minutes=1), now)
    with pytest.raises(ValueError):
        zp.check_schedule_time(now + timedelta(seconds=5), now)
    assert zp.check_schedule_time(now + timedelta(hours=1), now) == now + timedelta(hours=1)
    assert zp.iso_z(datetime(2026, 12, 1, 12, 0, tzinfo=timezone(timedelta(hours=2)))) == "2026-12-01T10:00:00Z"


def test_build_targets_is_strictly_tenant_scoped():
    mine = [{"account_id": "a-fb", "platform": "facebook", "status": "connected"},
            {"account_id": "a-ig", "platform": "instagram", "status": "connected"},
            {"account_id": "a-old", "platform": "twitter", "status": "disconnected"}]
    t, miss = zp.build_targets(["Facebook", "x"], None, mine)
    assert t == [{"platform": "facebook", "accountId": "a-fb"}] and miss == ["twitter"]  # x alias -> twitter, disconnected ignored
    t, miss = zp.build_targets([], ["a-ig", "someone-elses"], mine)
    assert t == [{"platform": "instagram", "accountId": "a-ig"}] and miss == ["someone-elses"]


def test_result_fields_reports_provider_truth():
    ok = zp.result_fields({"_id": "z1", "status": "scheduled", "platforms": [{"platform": "facebook", "accountId": "a", "status": "scheduled"}]}, "schedule")
    assert ok["status"] == "scheduled" and ok["publish_error"] is None and ok["zernio_post_id"] == "z1"
    bad = zp.result_fields({"_id": "z2", "status": "failed", "platforms": [{"platform": "facebook", "status": "failed", "errorMessage": "token expired"}]}, "now")
    assert bad["status"] == "failed" and "token expired" in bad["publish_error"]
    assert zp.result_fields({}, "now")["status"] == "published"  # only when the provider omitted status on a publish-now 2xx
    assert zp.event_to_status("post.failed") == "failed" and zp.event_to_status("message.received") is None


@pytest.fixture
def post_env(env):
    fake = FakeZernio()
    env.setattr(mk, "get_zernio_client", lambda: fake)
    env.setattr(mk, "_require_tenant_profile", lambda t: "prof-1")
    env.setattr(mk, "_tenant_account_rows", lambda t: [
        {"account_id": "a-fb", "platform": "facebook", "status": "connected"},
        {"account_id": "a-ig", "platform": "instagram", "status": "connected"}])
    return fake


def new_post(**kw):
    base = dict(id=uuid.uuid4(), platforms=["facebook"], content="Hello", media_urls=None, scheduled_for=None,
                timezone=None, status="draft", publish_error=None, zernio_post_id=None, platform_post_ids=None, published_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_push_schedule_sends_scheduled_for_and_media(post_env):
    when = datetime.now(timezone.utc) + timedelta(days=2)
    post = new_post(scheduled_for=when, media_urls=["https://cdn/x.jpg"], timezone="Africa/Johannesburg")
    run(mk._push_post(post, TENANT, "schedule"))
    call = post_env.calls[-1][1]
    assert call["schedule_date"] == zp.iso_z(when) and call["publish_now"] is False
    assert call["media_urls"] == ["https://cdn/x.jpg"] and call["timezone"] == "Africa/Johannesburg"
    assert call["platforms"] == [{"platform": "facebook", "accountId": "a-fb"}]
    assert call["idempotency_key"].startswith("omnidome-post-")
    assert post.status == "scheduled" and post.zernio_post_id == "zpost1" and post.publish_error is None


def test_push_now_and_provider_draft(post_env):
    p = new_post()
    run(mk._push_post(p, TENANT, "now"))
    assert post_env.calls[-1][1]["publish_now"] is True and p.status == "published" and p.published_at
    d = new_post()
    run(mk._push_post(d, TENANT, "draft", provider_draft=True))
    assert post_env.calls[-1][1]["is_draft"] is True and d.status == "draft"
    local = new_post()
    n = len(post_env.calls)
    run(mk._push_post(local, TENANT, "draft"))
    assert len(post_env.calls) == n and local.status == "draft"  # plain drafts stay in OmniDome


def test_push_refuses_foreign_accounts_and_unconnected_platforms(post_env):
    with pytest.raises(HTTPException) as e:
        run(mk._push_post(new_post(platforms=[]), TENANT, "now", account_ids=["a-fb", "not-mine"]))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        run(mk._push_post(new_post(platforms=["facebook", "tiktok"]), TENANT, "now"))
    assert e.value.status_code == 400 and "tiktok" in e.value.detail
    assert [c for c in post_env.calls if c[0] == "publish_content"] == []


def test_push_rejects_past_schedule_and_maps_provider_rejection(post_env):
    with pytest.raises(HTTPException) as e:
        run(mk._push_post(new_post(scheduled_for=datetime.now(timezone.utc) - timedelta(hours=1)), TENANT, "schedule"))
    assert e.value.status_code == 422
    post_env.fail = ZernioError(400, json.dumps({"error": "Instagram requires media", "code": "media_required", "type": "invalid_request_error"}))
    with pytest.raises(HTTPException) as e:
        run(mk._push_post(new_post(platforms=["instagram"]), TENANT, "now"))
    assert e.value.status_code == 422 and e.value.detail["error"] == "provider_rejected"
    assert "requires media" in e.value.detail["message"]


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def refresh(self, obj):
        now = datetime.now(timezone.utc)
        obj.created_at = obj.updated_at = now
        obj.id = obj.id or uuid.uuid4()


def patch_session(env, session):
    @asynccontextmanager
    async def fake_get_session():
        yield session

    env.setattr(mk, "get_session", fake_get_session)

    async def legacy(sess, tenant_id, account_id, platform_hint):
        return SimpleNamespace(id=uuid.uuid4())

    env.setattr(mk, "_legacy_account", legacy)


def test_create_post_without_account_id_succeeds_the_old_422(post_env, env):
    """The composer sends no usable account_id for provider-connected tenants; that used to be a 422."""
    sess = FakeSession()
    patch_session(env, sess)
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    body = mk.SocialPostCreate(content="Fibre promo", platforms=["facebook"], status="SCHEDULED", scheduled_for=when,
                               account_id="", campaign_id="", queue_id="")
    out = run(mk._create_post_core(body, TENANT))
    assert out["status"] == "scheduled" and out["zernio_post_id"] == "zpost1" and out["publish_error"] is None
    assert sess.added[0].status in ("scheduled",)
    assert post_env.calls[-1][1]["schedule_date"].endswith("Z")


def test_create_post_failure_is_visible_not_faked(post_env, env):
    sess = FakeSession()
    patch_session(env, sess)
    body = mk.SocialPostCreate(content="x", platforms=["tiktok"], status="published")
    out = run(mk._create_post_core(body, TENANT))
    assert out["status"] == "failed" and "tiktok" in out["publish_error"]


def test_create_post_validation(post_env, env):
    patch_session(env, FakeSession())
    with pytest.raises(HTTPException) as e:
        run(mk._create_post_core(mk.SocialPostCreate(content="x", platforms=["facebook"], status="scheduled"), TENANT))
    assert e.value.status_code == 422  # scheduled needs scheduled_for
    with pytest.raises(HTTPException) as e:
        run(mk._create_post_core(mk.SocialPostCreate(content="x", status="published"), TENANT))
    assert e.value.status_code == 422  # no platform
    draft = run(mk._create_post_core(mk.SocialPostCreate(content="idea"), TENANT))
    assert draft["status"] == "draft"


def test_list_filters_are_case_insensitive_multi_status_and_queue_aware():
    from sqlalchemy.dialects import postgresql

    stmt = mk._apply_post_filters(mk.select(mk.SocialPost), TENANT, "SCHEDULED,Draft", None, None, "X", None, None, None)
    comp = stmt.compile(dialect=postgresql.dialect())
    sql = str(comp).lower()
    assert "lower(social_posts.status) in" in sql and "social_posts.platforms @>" in sql
    assert ["scheduled", "draft"] in comp.params.values() and ["twitter"] in comp.params.values()  # 'X' -> twitter alias
    q = mk._apply_post_filters(mk.select(mk.SocialPost), TENANT, "queued", None, None, None, None, None, None)
    assert "queue_id is not null" in str(q.compile(dialect=postgresql.dialect())).lower()


def test_post_webhook_event_updates_row():
    eng = ScriptedEngine()
    orig = mk.get_engine
    mk.get_engine = lambda: eng
    try:
        mk._apply_post_event(str(TENANT), "zpost1", "failed", "token expired")
    finally:
        mk.get_engine = orig
    q, params = eng.log[0]
    assert "UPDATE social_posts" in q and "tenant_id = :tid" in q and "zernio_post_id = :zid" in q
    assert params == {"st": "failed", "err": "token expired", "tid": str(TENANT), "zid": "zpost1"}


def test_media_presign_validates_and_proxies(api):
    class Z(FakeZernio):
        async def presign_media(self, filename, content_type, size=None):
            self.calls.append(("presign", {"filename": filename, "content_type": content_type, "size": size}))
            return {"uploadUrl": "https://bucket/put", "publicUrl": "https://cdn/f.png", "key": "k", "expiresIn": 3600}

        async def put_presigned(self, url, data, ct):
            self.calls.append(("put", {"url": url, "n": len(data), "ct": ct}))

    z = Z()
    api.env.setattr(mk, "get_zernio_client", lambda: z)
    r = api.c.post("/social/media/presign", json={"filename": "../../etc/pass wd.png", "content_type": "image/png", "size": 10})
    assert r.status_code == 200 and r.json()["public_url"] == "https://cdn/f.png"
    assert z.calls[0][1]["filename"] == "pass wd.png"  # path components stripped
    assert api.c.post("/social/media/presign", json={"filename": "a.exe", "content_type": "application/x-msdownload"}).status_code == 422
    import base64
    up = api.c.post("/social/media/upload-base64", json={"filename": "a.png", "content_type": "image/png",
                                                         "data_base64": base64.b64encode(b"\x89PNGdata").decode()})
    assert up.status_code == 201 and up.json()["public_url"] == "https://cdn/f.png"
    assert z.calls[-1] == ("put", {"url": "https://bucket/put", "n": 8, "ct": "image/png"})
    assert api.c.post("/social/media/upload-base64", json={"filename": "a.png", "content_type": "image/png", "data_base64": "###"}).status_code == 422


# ═════════════════════ 3. campaigns + audiences ═════════════════════


def test_campaign_blank_dates_become_null():
    c = mk.CampaignCreate(name="Spring", channel="email", start_date="", end_date="   ", budget_zar="", audience_id="",
                          audience_segment_id="", description="")
    assert c.start_date is None and c.end_date is None and c.budget_zar == 0 and c.audience_id is None and c.description is None
    u = mk.CampaignUpdate(start_date="", end_date="")
    assert u.start_date is None and u.end_date is None
    with pytest.raises(Exception):
        mk.CampaignCreate(name="x", channel="email", budget_zar="-5")


def campaign_engine(audience_rules=None):
    row = {}

    def on_insert(p):
        row.update({"id": p["id"], "tenant_id": p["tid"], "name": p["name"], "channel": p["ch"], "status": p["status"],
                    "description": p["desc"], "budget_zar": p["budget"], "start_date": p["sd"], "end_date": p["ed"],
                    "audience_segment_id": p["asid"], "total_sent": 0, "total_delivered": 0, "total_opened": 0,
                    "total_clicked": 0, "total_conversions": 0, "created_at": datetime.now(timezone.utc),
                    "audience_name": "Fibre businesses" if p["asid"] else None, "audience_size": 2 if p["asid"] else None})
        return Rows()

    handlers = [
        ("INSERT INTO marketing_campaigns", on_insert),
        ("FROM marketing_campaigns c", lambda p: Rows([row])),
        ("FROM marketing_audience_segments WHERE id", lambda p: Rows(
            [{"id": p["id"], "name": "Fibre businesses", "rules": audience_rules or {"type": "businesses", "businesses": []}, "member_count": 2}]
            if p["tid"] == str(TENANT) else [])),
    ]
    return ScriptedEngine(handlers), row


def test_create_campaign_with_blank_dates_and_audience_is_201(api):
    seg = uuid.uuid4()
    eng, row = campaign_engine()
    api.env.setattr(mk, "get_engine", lambda: eng)
    r = api.c.post("/campaigns", json={"name": "Spring promo", "channel": "email", "start_date": "", "end_date": "",
                                       "budget_zar": "", "audience_id": str(seg)})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["start_date"] is None and j["end_date"] is None
    assert j["audience_segment_id"] == str(seg) and j["audience_id"] == str(seg) and j["audience_name"] == "Fibre businesses"
    insert = [p for q, p in eng.log if q.startswith("INSERT INTO marketing_campaigns")][0]
    assert insert["asid"] == str(seg) and insert["sd"] is None


def test_create_campaign_rejects_foreign_audience_and_bad_dates(api):
    eng, _ = campaign_engine()
    api.env.setattr(mk, "get_engine", lambda: eng)
    api.c.app.dependency_overrides[get_auth_context] = lambda: auth_ctx(tenant=OTHER)  # audience belongs to TENANT only
    r = api.c.post("/campaigns", json={"name": "x", "channel": "email", "audience_id": str(uuid.uuid4())})
    assert r.status_code == 422 and "Audience not found" in r.text
    api.c.app.dependency_overrides[get_auth_context] = lambda: api.ctx
    r = api.c.post("/campaigns", json={"name": "x", "channel": "email", "start_date": "2026-12-02T00:00:00Z", "end_date": "2026-12-01T00:00:00Z"})
    assert r.status_code == 422 and "end_date" in r.text


def test_audience_members_resolution():
    rules = {"type": "businesses", "businesses": [
        {"name": "A", "email": "Ops@A.co.za", "phone": "082 000 1111"}, {"name": "B", "email": "ops@a.co.za"},
        {"name": "C", "phone": "+27 11 222 3333"}, {"name": "D"}, {"name": "E", "email": "not-an-email"}]}
    m = am.resolve_members(rules)
    assert m["emails"] == ["ops@a.co.za"] and m["phones"] == ["0820001111", "+27112223333"] and m["skipped"] == 2
    homes = am.resolve_members({"type": "homes", "areas": [{"name": "Sandton", "homes": 500}]})
    assert homes["emails"] == [] and "areas" in homes["note"]
    assert am.resolve_members({"type": "custom", "emails": ["x@y.co"], "contacts": [{"email": "z@y.co"}, "w@y.co"]})["emails"] == ["z@y.co", "w@y.co", "x@y.co"]
    assert am.resolve_members({"type": "businesses", "businesses": [{"name": "n"}]})["note"]


def test_email_send_uses_campaign_audience(api):
    rules = {"type": "businesses", "businesses": [{"email": "a@biz.co"}, {"email": "b@biz.co"}]}
    seg = uuid.uuid4()
    eng = ScriptedEngine([
        ("SELECT audience_segment_id FROM marketing_campaigns", lambda p: Rows([{"audience_segment_id": seg}])),
        ("FROM marketing_audience_segments WHERE id", lambda p: Rows([{"id": seg, "name": "Biz", "rules": rules, "member_count": 2}])),
    ])
    api.env.setattr(mk, "get_engine", lambda: eng)
    emails, name = mk._campaign_audience_emails(TENANT, uuid.uuid4())
    assert emails == ["a@biz.co", "b@biz.co"] and name == "Biz"
    stamp = [p for q, p in eng.log if "UPDATE marketing_campaigns SET audience_member_count" in q][0]
    assert stamp["n"] == 2 and stamp["tid"] == str(TENANT)
    # homes audience: nothing to send to -> 422 with the reason
    eng2 = ScriptedEngine([
        ("SELECT audience_segment_id FROM marketing_campaigns", lambda p: Rows([{"audience_segment_id": seg}])),
        ("FROM marketing_audience_segments WHERE id", lambda p: Rows([{"id": seg, "name": "H", "rules": {"type": "homes", "areas": []}, "member_count": 0}])),
    ])
    api.env.setattr(mk, "get_engine", lambda: eng2)
    with pytest.raises(HTTPException) as e:
        mk._campaign_audience_emails(TENANT, uuid.uuid4())
    assert e.value.status_code == 422 and "areas" in e.value.detail


def test_email_send_requires_recipients_or_campaign(api):
    api.env.setenv("EMAIL_UNSUBSCRIBE_SECRET", "unit-test-unsubscribe-secret-0123456789")
    api.env.setenv("EMAIL_UNSUBSCRIBE_BASE_URL", "https://app.test/svc/marketing")
    api.env.setattr(mk, "_email_provider_configured", lambda t=None: True)
    r = api.c.post("/email/send", json={"subject": "Hi", "body_html": "<p>x</p>"})
    assert r.status_code == 422 and "recipients" in r.text


# ═════════════════════ 4. ads ═════════════════════


def ad_payload(**over):
    base = {
        "account_id": "acc-metaads", "ad_account_id": "act_1", "name": "Fibre launch", "goal": "traffic",
        "budget": {"amount": 100, "type": "daily", "currency": "ZAR"},
        "creative": {"headline": "Get fibre", "body": "Uncapped from R399", "call_to_action": "LEARN_MORE",
                     "link_url": "https://example.com/fibre", "image_url": "https://cdn/x.jpg"},
        "targeting": {"countries": ["za"], "age_min": 25, "age_max": 55, "gender": "all",
                      "interests": [{"id": "1", "name": "Internet"}], "audience_id": "aud-9"},
    }
    base.update(over)
    return base


@pytest.fixture
def ads_api(api):
    api.env.setattr(ads, "tenant_ads_connections", lambda t: [{"account_id": "acc-metaads", "platform": "metaads", "username": "acme", "status": "connected"}]
                    if t == TENANT else [])
    ads._ACCT_CACHE.clear()
    mirrored = []
    api.env.setattr(ads, "_save_local_campaign", lambda *a: mirrored.append(a) or uuid.UUID(int=7))
    api.mirrored = mirrored
    return api


def test_goals_are_the_documented_enums(api):
    r = api.c.get("/ads/goals").json()
    by = {p["platform"]: [g["id"] for g in p["goals"]] for p in r["platforms"]}
    assert len(by["meta"]) == 11 and "lead_generation" in by["meta"]
    assert by["google"] == ["engagement", "traffic", "awareness"]
    assert "job_applicants" in by["linkedin"] and "app_promotion" in by["x"]
    assert api.c.get("/ads/goals", params={"platform": "myspace"}).status_code == 422


def test_ads_accounts_lists_ad_accounts_or_says_none_connected(ads_api):
    r = ads_api.c.get("/ads/accounts").json()
    assert r["connections"][0]["platform"] == "meta"
    assert r["ad_accounts"][0] == {**r["ad_accounts"][0], "ad_account_id": "act_1", "currency": "ZAR", "minimum_daily_budget": 50}
    ads_api.c.app.dependency_overrides[get_auth_context] = lambda: auth_ctx(tenant=OTHER)
    empty = ads_api.c.get("/ads/accounts").json()
    assert empty["connections"] == [] and "No ads account is connected" in empty["message"]


def test_validate_catches_missing_and_wrong_fields():
    ad = ads.AdCreateIn(**ad_payload(goal="lead_generation", creative={"headline": "h", "body": "b", "call_to_action": "SIGN_UP", "image_url": "https://x/y.png"}))
    errs, _ = ads.validate_ad(ad, "meta")
    assert any(e["field"] == "creative.lead_gen_form_id" for e in errs)
    ad = ads.AdCreateIn(**ad_payload(goal="video_views"))
    errs, _ = ads.validate_ad(ad, "google")
    assert any(e["code"] == "invalid_goal" for e in errs)  # google rejects video_views
    ad = ads.AdCreateIn(**ad_payload(budget={"amount": 10, "type": "lifetime"}))
    assert any(e["code"] == "end_date_required" for e in ads.validate_ad(ad, "meta")[0])
    ad = ads.AdCreateIn(**ad_payload(budget={"amount": 10, "type": "daily", "currency": "USD"}))
    errs, _ = ads.validate_ad(ad, "meta", {"currency": "ZAR", "minimum_daily_budget": 50})
    codes = {e["code"] for e in errs}
    assert {"currency_mismatch", "below_minimum"} <= codes
    ad = ads.AdCreateIn(**ad_payload(targeting={"countries": ["ZAF"], "age_min": 50, "age_max": 20}))
    codes = {e["code"] for e in ads.validate_ad(ad, "meta")[0]}
    assert {"invalid_country", "age_range"} <= codes
    ad = ads.AdCreateIn(**ad_payload(provider_overrides={"accountId": "evil"}))
    assert any(e["code"] == "override_not_allowed" for e in ads.validate_ad(ad, "meta")[0])
    ok = ads.AdCreateIn(**ad_payload())
    assert ads.validate_ad(ok, "meta", {"currency": "ZAR", "minimum_daily_budget": 50})[0] == []


def test_build_provider_body_maps_fields():
    ad = ads.AdCreateIn(**ad_payload(start_date="2026-12-01T08:00:00Z", status="paused",
                                     promoted_object={"pixel_id": "px", "custom_event_type": "LEAD"}))
    b = ads.build_provider_body(ad, "meta", "ZAR")
    assert b["accountId"] == "acc-metaads" and b["adAccountId"] == "act_1" and b["budgetAmount"] == 100 and b["budgetType"] == "daily"
    assert b["currency"] == "ZAR" and b["status"] == "PAUSED" and b["goal"] == "traffic" and b["startDate"] == "2026-12-01T08:00:00Z"
    assert b["headline"] == "Get fibre" and b["callToAction"] == "LEARN_MORE" and b["linkUrl"].startswith("https://")
    assert b["imageUrl"] == "https://cdn/x.jpg" and b["countries"] == ["ZA"] and b["ageMin"] == 25 and b["ageMax"] == 55
    assert b["interests"] == [{"id": "1", "name": "Internet"}] and b["audienceId"] == "aud-9"
    assert b["promotedObject"] == {"pixelId": "px", "customEventType": "LEAD"} and "gender" not in b
    tt = ads.build_provider_body(ads.AdCreateIn(**ad_payload(creative={"body": "cap", "video_url": "https://v/x.mp4"})), "tiktok")
    assert tt["imageUrl"] == "https://v/x.mp4" and "video" not in tt  # TikTok carries the video URL in imageUrl
    assert ads.build_provider_body(ad, "meta", validate_only=True)["validateOnly"] is True


def test_create_ad_success_is_paused_by_default_and_mirrored(ads_api):
    r = ads_api.c.post("/ads/create", json=ad_payload(client_request_id="req-1"))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "created" and j["created_as"] == "paused" and j["ad"]["ad_id"] == "ad-1" and j["ad"]["platform_campaign_id"] == "c1"
    call = [c for c in ads_api.z.calls if c[0] == "ads_create"][-1][1]
    assert call["body"]["status"] == "PAUSED" and call["idempotency_key"].endswith("req-1")
    assert ads_api.mirrored and j["local_campaign_id"]


def test_create_ad_provider_rejection_is_422_with_message(ads_api):
    ads_api.z.fail = None
    orig = ads_api.z.ads_create

    async def reject(body, idempotency_key=None):
        raise ZernioError(400, json.dumps({"error": "Meta rejected the ad: Page not connected", "type": "platform_error",
                                           "code": "platform_rejected", "details": {"stage": "creative"}}))

    ads_api.z.ads_create = reject
    r = ads_api.c.post("/ads/create", json=ad_payload())
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["error"] == "provider_rejected" and "Page not connected" in d["message"] and d["details"]["stage"] == "creative"
    assert ads_api.mirrored == []  # nothing saved locally as if it worked
    ads_api.z.ads_create = orig


def test_create_ad_never_fakes_success(ads_api):
    async def empty(body, idempotency_key=None):
        return {"message": "ok"}

    ads_api.z.ads_create = empty
    r = ads_api.c.post("/ads/create", json=ad_payload())
    assert r.status_code == 502 and r.json()["detail"]["error"] == "provider_no_ad" and ads_api.mirrored == []


def test_create_ad_no_ads_account_foreign_account_and_foreign_ad_account(ads_api):
    ads_api.c.app.dependency_overrides[get_auth_context] = lambda: auth_ctx(tenant=OTHER)
    r = ads_api.c.post("/ads/create", json=ad_payload())
    assert r.status_code == 409 and r.json()["detail"]["error"] == "no_ads_account"
    ads_api.c.app.dependency_overrides[get_auth_context] = lambda: ads_api.ctx
    r = ads_api.c.post("/ads/create", json=ad_payload(account_id="acc-of-another-tenant"))
    assert r.status_code == 403 and r.json()["detail"]["error"] == "account_not_in_tenant"
    r = ads_api.c.post("/ads/create", json=ad_payload(ad_account_id="act_999"))
    assert r.status_code == 403 and r.json()["detail"]["error"] == "ad_account_not_available"
    assert [c for c in ads_api.z.calls if c[0] == "ads_create"] == []


def test_create_ad_local_validation_blocks_before_provider(ads_api):
    r = ads_api.c.post("/ads/create", json=ad_payload(goal="nonsense"))
    assert r.status_code == 422 and r.json()["detail"]["error"] == "validation_failed"
    assert r.json()["detail"]["errors"][0]["code"] == "invalid_goal"
    assert [c for c in ads_api.z.calls if c[0] == "ads_create"] == []


def test_validate_endpoint_runs_meta_dry_run(ads_api):
    r = ads_api.c.post("/ads/validate", json=ad_payload())
    j = r.json()
    assert r.status_code == 200 and j["valid"] is True and j["provider_validated"] is True
    assert [c for c in ads_api.z.calls if c[0] == "ads_create"][-1][1]["body"]["validateOnly"] is True
    ads_api.c.app.dependency_overrides[get_auth_context] = lambda: ads_api.ctx


def test_provider_error_mapping():
    e = zerr.provider_error("x", ZernioError(500, "boom"))
    assert e.status_code == 502 and "boom" not in json.dumps(e.detail)
    e = zerr.provider_error("x", ZernioError(401, "bad key sk_live_abcdefghijk"))
    assert e.status_code == 502
    e = zerr.provider_error("x", ZernioError(403, json.dumps({"error": "Ads add-on required"})))
    assert e.status_code == 422 and "add-on" in e.detail["message"]
    e = zerr.provider_error("x", ZernioError(400, "Bearer abc.def.ghi leaked"))
    assert "abc.def.ghi" not in e.detail["message"]
    e = zerr.provider_error("x", RuntimeError("socket closed"))
    assert e.status_code == 502


# ═════════════════════ 5. WhatsApp senders ═════════════════════


def test_senders_come_from_provider_not_hard_coded(api):
    eng = ScriptedEngine([("FROM marketing_connected_accounts", lambda p: Rows([
        {"account_id": "wa-1", "username": "+27820000000", "connected_at": datetime(2026, 10, 1, tzinfo=timezone.utc)}]))])
    api.env.setattr(mk, "get_engine", lambda: eng)
    rows = api.c.get("/whatsapp/senders").json()
    assert len(rows) == 1
    s = rows[0]
    assert s["name"] == "Acme Fibre" and s["name_review"] == "Approved" and s["business_verification"] == "Not verified"
    assert s["quality_rating"] == "GREEN" and s["status"] == "LIVE" and s["live_data"] is True
    assert "Pending Meta Review" not in json.dumps(rows)  # the old hard-coded strings are gone
    assert eng.log[0][1]["tid"] == str(TENANT)


def test_sender_status_is_null_when_provider_unavailable(api):
    eng = ScriptedEngine([("FROM marketing_connected_accounts", lambda p: Rows([
        {"account_id": "wa-1", "username": "+27820000000", "connected_at": None}]))])
    api.env.setattr(mk, "get_engine", lambda: eng)

    async def boom(account_id):
        raise ZernioError(502, "meta down")

    api.z.whatsapp_number_info = boom
    s = api.c.get("/whatsapp/senders").json()[0]
    assert s["name_review"] is None and s["business_verification"] is None and s["live_data"] is False and s["status_error"]
    assert s["number"] == "+27820000000"


def test_sender_view_label_mapping():
    v = mk.whatsapp_sender_view("a", "u", {"phone": {"name_status": "PENDING_REVIEW"}, "waba": {"business_verification_status": "verified"}}, None)
    assert v["name_review"] == "Pending Meta review" and v["business_verification"] == "Verified"
    v = mk.whatsapp_sender_view("a", "u", {"phone": {"name_status": "DECLINED"}, "waba": {}}, None)
    assert v["name_review"] == "Declined" and v["business_verification"] is None


def test_old_fake_sender_connect_is_retired(api):
    r = api.c.post("/whatsapp/senders/connect", json={"mode": "own_number", "phone_number": "+27111111111"})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "use_embedded_signup"


def test_whatsapp_embedded_signup_flow(api):
    class Z(FakeZernio):
        async def connect_get(self, path, params=None, connect_token=None):
            return {"appId": "meta-app", "configId": "cfg-1", "branding": {"brandName": None}}

        async def connect_post(self, path, body, connect_token=None):
            self.calls.append(("connect_post", {"path": path, "body": body}))
            return {"account": {"accountId": "wa-1", "platform": "whatsapp"}}

    z = Z()
    z.profile_accounts = [{"_id": "wa-1", "platform": "whatsapp", "username": "+27820000000", "profileId": "prof-1"}]
    api.env.setattr(mk, "get_zernio_client", lambda: z)
    cfg = api.c.get("/social/connect/whatsapp/sdk-config").json()
    assert cfg["app_id"] == "meta-app" and cfg["config_id"] == "cfg-1" and cfg["state"]
    r = api.c.post("/social/connect/whatsapp/embedded-signup", json={"state": cfg["state"], "code": "AQB-code-123", "waba_id": "w", "phone_number_id": "p"})
    assert r.status_code == 200 and r.json()["accounts"][0]["account_id"] == "wa-1"
    sent = [c for c in z.calls if c[0] == "connect_post"][-1][1]
    assert sent["path"] == "whatsapp/embedded-signup" and sent["body"]["profileId"] == "prof-1" and sent["body"]["wabaId"] == "w"


# ═════════════════════ 6. lead forms + leads ═════════════════════


def test_normalize_lead_shapes():
    row = leads.normalize_lead({"id": "l1", "leadgenId": "g1", "formId": "f1", "fields": {"email": "a@b.co"},
                                "createdAt": "2026-10-01T10:00:00Z", "isOrganic": False}, "acc", "facebook")
    assert row["lead_id"] == "l1" and row["fields"] == {"email": "a@b.co"} and row["created_time"].tzinfo and row["account_id"] == "acc"
    raw = leads.normalize_lead({"id": "l2", "fieldData": [{"name": "email", "values": ["x@y.co"]}, {"name": "multi", "values": ["a", "b"]}]})
    assert raw["fields"] == {"email": "x@y.co", "multi": ["a", "b"]}
    assert leads.normalize_lead({}) is None


def test_lead_received_webhook_is_stored_tenant_scoped_and_idempotent(monkeypatch):
    eng = ScriptedEngine()
    monkeypatch.setattr(leads, "get_engine", lambda: eng)
    payload = {"event": "lead.received", "lead": {"id": "l9", "leadgenId": "g9", "formId": "f1", "formName": "Fibre", "fields": {"phone": "+27820000000"},
                                                  "isOrganic": False, "createdAt": "2026-10-02T08:00:00Z"},
               "account": {"id": "acc-fb", "accountId": "acc-fb", "platform": "facebook", "profileId": "prof-1"}}
    out = leads.ingest_lead_event(str(TENANT), payload)
    assert out["lead_id"] == "l9"
    q, p = eng.log[0]
    assert "ON CONFLICT (tenant_id, lead_id) DO NOTHING" in q and p["tid"] == str(TENANT) and p["account_id"] == "acc-fb"
    assert p["source"] == "webhook" and json.loads(p["fields"]) == {"phone": "+27820000000"}


def test_webhook_routes_lead_events_by_top_level_account(api, monkeypatch):
    """lead.* payloads have no `message`; routing must use payload.account (it used to 400 'could not route')."""
    stored = {}
    monkeypatch.setattr(mk, "_tenant_for_account", lambda aid: str(TENANT) if aid == "acc-fb" else None)
    monkeypatch.setattr(mk, "_tenant_for_profile", lambda pid: None)

    class Sess:
        async def flush(self):
            pass

        def add(self, o):
            o.id = uuid.uuid4()

        async def get(self, model, id_):
            return SimpleNamespace(processed=False)

    patch_session(monkeypatch, Sess())
    monkeypatch.setattr(leads, "ingest_lead_event", lambda tid, pl: stored.update(tid=tid) or {"stored": 1, "lead_id": "l1"})
    out = run(mk._process_zernio_event(
        {"event": "lead.received", "lead": {"id": "l1"}, "account": {"accountId": "acc-fb", "platform": "facebook"}},
        "", "lead.received", "facebook"))
    assert out["event"] == "lead.received" and stored["tid"] == str(TENANT)


def test_lead_sync_pulls_forms_and_leads_for_tenant_accounts_only(api, monkeypatch):
    eng = ScriptedEngine([("AND platform = ANY", lambda p: Rows([{"account_id": "acc-fb", "platform": "facebook"}]))])
    monkeypatch.setattr(leads, "get_engine", lambda: eng)
    forms = run(leads.sync_forms(TENANT))
    assert forms["forms_synced"] == 1 and forms["errors"] == []
    res = run(leads.sync_leads(TENANT))
    assert res["leads_seen"] == 1 and res["leads_inserted"] == 1
    assert any("INSERT INTO marketing_lead_forms" in q for q, _ in eng.log) and any("INSERT INTO marketing_ad_leads" in q for q, _ in eng.log)
    assert [c[1]["account_id"] for c in api.z.calls if c[0] == "leads_list"] == ["acc-fb"]


def test_lead_form_create_checks_account_ownership(api, monkeypatch):
    eng = ScriptedEngine([("AND account_id = :aid", lambda p: Rows([{"account_id": "acc-fb", "platform": "facebook"}]) if p["aid"] == "acc-fb" else Rows())])
    monkeypatch.setattr(leads, "get_engine", lambda: eng)

    async def create(body):
        api.z.calls.append(("lead_forms_create", body))
        return {"status": "ok", "form": {"id": "f-new", "name": body["name"]}}

    api.z.lead_forms_create = create
    good = {"account_id": "acc-fb", "name": "Signup", "privacy_policy_url": "https://example.com/privacy", "questions": [{"type": "EMAIL"}]}
    r = api.c.post("/ads/lead-forms", json=good)
    assert r.status_code == 201 and r.json()["form_id"] == "f-new"
    r = api.c.post("/ads/lead-forms", json={**good, "account_id": "acc-other"})
    assert r.status_code == 403
    r = api.c.post("/ads/lead-forms", json={**good, "privacy_policy_url": "http://insecure"})
    assert r.status_code == 422


# ═════════════════════ queue / connectors ═════════════════════


def test_enqueue_schedules_at_the_provider_for_the_next_slot(api, monkeypatch):
    qid = uuid.uuid4()
    slots = [{"day": d, "time": "09:00"} for d in range(7)]
    eng = ScriptedEngine([
        ("FROM marketing_post_queues WHERE id", lambda p: Rows([{"id": qid, "status": "active", "slots": slots, "timezone": "UTC"}])),
        ("SELECT scheduled_for FROM social_posts", lambda p: Rows([])),
    ])
    monkeypatch.setattr(mk, "get_engine", lambda: eng)
    seen = {}

    async def core(body, tenant_id):
        seen["body"] = body
        return {"id": uuid.uuid4(), "status": "scheduled", "scheduled_for": body.scheduled_for, "publish_error": None, "zernio_post_id": "z1"}

    monkeypatch.setattr(mk, "_create_post_core", core)
    r = api.c.post(f"/social/queues/{qid}/enqueue", json={"content": "queued post", "platforms": ["facebook"], "status": "scheduled"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["queue_id"] == str(qid) and j["zernio_post_id"] == "z1"
    b = seen["body"]
    assert b.queue_id == qid and b.status == "scheduled" and b.scheduled_for > datetime.now(timezone.utc)  # a real, future slot


def test_connectors_catalog_includes_ads_and_maps_ads_accounts(api, monkeypatch):
    eng = ScriptedEngine([("FROM marketing_connected_accounts", lambda p: Rows([
        {"account_id": "m1", "platform": "metaads", "username": "acme", "status": "connected"}]))])
    monkeypatch.setattr(mk, "get_engine", lambda: eng)
    j = api.c.get("/social/zernio/connectors").json()
    by = {c["id"]: c for c in j["connectors"]}
    assert by["meta_ads"]["connected"] is True and by["meta_ads"]["category"] == "Ads"
    assert by["google_ads"]["connected"] is False and "snapchat" in by and not by["snapchat"].get("coming_soon")


# ═════════════════════ pending-data pickers (LinkedIn / Google Business) ═════════════════════


def test_linkedin_organization_pick_via_pending_data(api):
    from cryptography.fernet import Fernet
    api.env.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def pending(token):
        api.z.calls.append(("pending", {"token": token}))
        return {"platform": "linkedin", "tempToken": "LI-TEMP", "userProfile": {"id": "li-user"}, "selectionType": "organizations",
                "organizations": [{"id": "111", "urn": "urn:li:organization:111", "name": "Acme Ltd", "vanityName": "acme"}]}

    api.z.get_pending_connect_data = pending
    st = start(api, "linkedin")["state"]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {"profileId": "prof-1", "step": "select_organization", "pendingDataToken": "PDT"}})
    assert r.status_code == 200, r.text
    opts = r.json()["options"]
    assert [o["id"] for o in opts] == ["personal", "111"] and opts[1]["account_type"] == "organization"
    assert "LI-TEMP" not in json.dumps(r.json())

    async def post(path, body, connect_token=None):
        api.z.calls.append(("connect_post", {"path": path, "body": body}))
        return {"account": {"accountId": "acc-li", "platform": "linkedin"}}

    api.z.connect_post = post
    api.z.profile_accounts = [{"_id": "acc-li", "platform": "linkedin", "username": "acme", "profileId": "prof-1"}]
    ok = api.c.post("/social/connect/select", json={"state": st, "selection_ids": ["111"]})
    assert ok.status_code == 200, ok.text
    body = [c for c in api.z.calls if c[0] == "connect_post"][-1][1]["body"]
    assert body["accountType"] == "organization" and body["selectedOrganization"]["urn"] == "urn:li:organization:111"
    assert body["tempToken"] == "LI-TEMP" and body["profileId"] == "prof-1"


def test_no_options_is_a_clear_user_fixable_error(api):
    from cryptography.fernet import Fernet
    api.env.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())

    async def empty(path, params=None, connect_token=None):
        return {"pages": []}

    api.z.connect_get = empty
    st = start(api, "facebook")["state"]
    r = api.c.post("/social/connect/complete", json={"state": st, "params": {"tempToken": "T", "step": "select_page", "userProfile": "{}"}})
    j = r.json()
    assert r.status_code == 200 and j["status"] == "error" and j["error"] == "no_options" and j["user_fixable"] is True
