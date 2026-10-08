import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

from services.portal_builder import wordpress as wp
from services.portal_builder.tests.conftest import _DB, Tenant, make_page

P = "/api/v1/portal/wordpress"


@pytest.fixture
def remote(monkeypatch):
    state = {"pages": {}, "calls": [], "fail_after_write": False}
    class FakeClient:
        def __init__(self, *args):
            self.http = self
        async def aclose(self):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def discover(self):
            return list(wp.ABILITIES)
        async def execute(self, name, params):
            state["calls"].append(name)
            if name == "omnidome/site-info":
                return {"integration_version": 1, "site_name": "My ISP"}
            key = params["external_id"]
            if name == "omnidome/upsert-page-draft":
                state["pages"][key] = {"status": "draft_exported", "exported_hash": params["exported_hash"],
                                       "preview_url": "https://isp.example/?preview=true", "published_hash": None}
            if name == "omnidome/publish-page":
                state["pages"][key].update(status="published", published_hash=params["exported_hash"],
                                           live_url="https://isp.example/fibre")
            if state["fail_after_write"] and name != "omnidome/get-publication-status":
                state["fail_after_write"] = False
                raise wp.WordPressError("WordPress did not confirm the request")
            return state["pages"].get(key, {"status": "not_exported"})
    async def safe(url):
        return url.rstrip("/")
    monkeypatch.setattr(wp, "WordPressClient", FakeClient)
    monkeypatch.setattr(wp, "site_url", safe)
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    wp.limiter._requests.clear()
    return state


def connect(client, tenant):
    r = client.post(P + "/connections", json={"site_url": "https://isp.example", "username": "builder",
                                               "application_password": "super-secret"}, headers=tenant.h())
    assert r.status_code == 201, r.text
    assert "super-secret" not in r.text and "password_enc" not in r.text
    return r.json()["id"]


def target(client, tenant):
    cid = connect(client, tenant)
    page = make_page(client, tenant, content={"blocks": [{"type": "hero", "heading": "Fast fibre"}]})
    return cid, page["id"], f"{P}/connections/{cid}/pages/{page['id']}"


def test_connections_encrypt_and_respect_roles_and_tenants(client, tenant, remote):
    cid = connect(client, tenant)
    with create_engine(f"sqlite:///{_DB}").connect() as db:
        token = db.execute(text("SELECT password_enc FROM portal_wordpress_connections WHERE username='builder' ORDER BY checked_at DESC")).scalar()
    assert token != "super-secret" and wp.secretbox.decrypt(token) == "super-secret"
    body = {"site_url": "https://other.example", "username": "builder", "application_password": "secret"}
    assert client.post(P + "/connections", json=body, headers=tenant.h("editor")).status_code == 403
    other = Tenant()
    assert client.get(P + "/connections", headers=other.h()).json()["items"] == []
    assert client.post(f"{P}/connections/{cid}/test", headers=other.h()).status_code == 404
    assert client.delete(f"{P}/connections/{cid}", headers=other.h()).status_code == 404


def test_draft_review_publish_separate_from_native_status(client, tenant, remote):
    cid, pid, url = target(client, tenant)
    result = client.post(url + "/export", headers=tenant.h("editor"))
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["status"] == "draft_exported" and not data["local_changes"]
    digest = data["exported_hash"]
    assert client.post(url + "/publish", json={"exported_hash": digest}, headers=tenant.h("editor")).status_code == 403
    pub = client.post(url + "/publish", json={"exported_hash": digest}, headers=tenant.h()).json()
    assert pub["status"] == "published"
    assert client.get(f"/api/v1/portal/pages/{pid}", headers=tenant.h()).json()["status"] == "draft"
    client.put(f"/api/v1/portal/pages/{pid}", json={"title": "New offer"}, headers=tenant.h())
    assert client.get(url, headers=tenant.h()).json()["local_changes"]
    assert client.post(url + "/publish", json={"exported_hash": digest}, headers=tenant.h()).status_code == 409


def test_lost_write_response_requires_reconciliation(client, tenant, remote):
    cid, pid, url = target(client, tenant)
    remote["fail_after_write"] = True
    first = client.post(url + "/export", headers=tenant.h()).json()
    assert first["status"] == "uncertain"
    assert client.post(url + "/export", headers=tenant.h()).status_code == 409
    assert client.delete(f"/api/v1/portal/pages/{pid}", headers=tenant.h()).status_code == 409
    assert client.delete(f"{P}/connections/{cid}", headers=tenant.h()).status_code == 409
    refreshed = client.post(url + "/refresh", headers=tenant.h()).json()
    assert refreshed["status"] == "draft_exported"
    assert remote["calls"].count("omnidome/upsert-page-draft") == 1
    assert client.delete(f"{P}/connections/{cid}", headers=tenant.h()).status_code == 200
    assert client.post(url + "/export", headers=tenant.h()).status_code == 409


def test_publish_lost_response_recovers_confirmed_publication(client, tenant, remote):
    cid, pid, url = target(client, tenant)
    digest = client.post(url + "/export", headers=tenant.h()).json()["exported_hash"]
    remote["fail_after_write"] = True
    assert client.post(url + "/publish", json={"exported_hash": digest}, headers=tenant.h()).json()["status"] == "uncertain"
    recovered = client.post(url + "/refresh", headers=tenant.h()).json()
    assert recovered["published_hash"] == digest and recovered["status"] == "published"


def test_connection_secret_key_required_and_page_isolation(client, tenant, remote, monkeypatch):
    cid, pid, url = target(client, tenant)
    other = Tenant()
    other_cid = connect(client, other)
    assert client.post(f"{P}/connections/{other_cid}/pages/{pid}/export", headers=other.h()).status_code == 404
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY")
    assert client.post(url + "/export", headers=tenant.h()).status_code == 503
    assert client.post(P + "/connections", json={"site_url": "https://new.example", "username": "builder", "application_password": "secret"}, headers=tenant.h()).status_code == 503


def test_remote_link_cannot_inject_another_origin():
    with pytest.raises(wp.WordPressError):
        wp.validate_remote({"status": "published", "live_url": "javascript:alert(1)"}, "https://isp.example")
    with pytest.raises(wp.WordPressError):
        wp.validate_remote({"status": "published", "live_url": "https://evil.example"}, "https://isp.example")
