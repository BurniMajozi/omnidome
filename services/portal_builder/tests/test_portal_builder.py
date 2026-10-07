import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import create_engine, text

from services.portal_builder import fetcher, main, security
from services.portal_builder.tests.conftest import _DB, Tenant, make_page

P = "/api/v1/portal"
EVIL = {"blocks": [{"type": "text", "body": "Hi <script>alert(1)</script><b onclick='x()'>there</b>",
                    "href": "javascript:alert(1)", "src": "https://img.example/a.png"}]}


# ── sanitisers ─────────────────────────────────────────────────────────

def test_sanitize_css_strips_active_content():
    css = "@import url(//evil/x.css); a{background:url(javascript:alert(1));width:expression(alert(1))} b{color:red}"
    out = security.sanitize_css(css)
    for bad in ("@import", "url(", "expression", "javascript"):
        assert bad not in out.lower()
    assert "color:red" in out
    assert "<" not in security.sanitize_css("</style><script>x</script>")
    assert "ur\\l(" not in security.sanitize_css("b{background:ur\\l(http://x)}") and "url(" not in security.sanitize_css("b{background:ur\\l(http://x)}")


def test_sanitize_content_and_urls():
    out = security.sanitize_content(EVIL)["blocks"][0]
    assert "<script" not in out["body"] and "onclick" not in out["body"] and "<b>there</b>" in out["body"]
    assert out["href"] == "" and out["src"] == "https://img.example/a.png"
    assert security.sanitize_html("Fast & cheap") == "Fast & cheap"
    assert security.sanitize_url("//evil.com") == "" and security.sanitize_url(" JaVa\tScript:x") == ""


# ── slugs, pages, roles ────────────────────────────────────────────────

def test_slug_validation_and_conflict(client, tenant):
    for bad in ("Has Space", "-lead", "trail-", "a_b", "x" * 101, "admin", "api"):
        r = client.post(f"{P}/pages", json={"slug": bad, "title": "t"}, headers=tenant.h())
        assert r.status_code == 422, bad
    p = make_page(client, tenant, slug="MyPromo")
    assert p["slug"] == "mypromo"
    r = client.post(f"{P}/pages", json={"slug": "mypromo", "title": "dup"}, headers=tenant.h())
    assert r.status_code == 409
    # same slug in another tenant is allowed while unpublished
    other = Tenant()
    assert client.post(f"{P}/pages", json={"slug": "mypromo", "title": "x"}, headers=other.h()).status_code == 201


def test_role_tiers(client, tenant):
    page = make_page(client, tenant)
    pid = page["id"]
    viewer = tenant.h("viewer")
    assert client.post(f"{P}/pages", json={"slug": "viewer-page", "title": "t"}, headers=viewer).status_code == 403
    assert client.get(f"{P}/pages/{pid}", headers=viewer).status_code == 200
    editor = tenant.h("marketing")
    assert client.put(f"{P}/pages/{pid}", json={"title": "New"}, headers=editor).status_code == 200
    assert client.post(f"{P}/pages/{pid}/publish", headers=editor).status_code == 403
    assert client.delete(f"{P}/pages/{pid}", headers=editor).status_code == 403
    assert client.post(f"{P}/pages/{pid}/share", json={"recipient_email": "a@b.co"}, headers=editor).status_code == 403
    mgr = tenant.h("manager")
    assert client.post(f"{P}/pages/{pid}/publish", headers=mgr).status_code == 200
    assert client.delete(f"{P}/pages/{pid}", headers=mgr).status_code == 200
    assert client.get(f"{P}/pages/{pid}", headers=mgr).status_code == 404


def test_tenant_isolation(client, tenant):
    page = make_page(client, tenant)
    other = Tenant()
    assert client.get(f"{P}/pages/{page['id']}", headers=other.h()).status_code == 404
    assert client.post(f"{P}/pages/{page['id']}/publish", headers=other.h()).status_code == 404
    assert client.delete(f"{P}/pages/{page['id']}", headers=other.h()).status_code == 404


def test_custom_js_rejected_and_status_publish_blocked(client, tenant):
    pid = make_page(client, tenant)["id"]
    assert client.put(f"{P}/pages/{pid}", json={"custom_js": "alert(1)"}, headers=tenant.h()).status_code == 422
    assert client.put(f"{P}/pages/{pid}", json={"status": "published"}, headers=tenant.h()).status_code == 422
    assert client.put(f"{P}/pages/{pid}", json={"status": "archived"}, headers=tenant.h()).status_code == 200


def test_list_pages_count_and_versions_precedence(client):
    t = Tenant()
    ids = [make_page(client, t)["id"] for _ in range(3)]
    r = client.get(f"{P}/pages", params={"page_size": 2}, headers=t.h()).json()
    assert r["total"] == 3 and r["pages"] == 2
    for i in range(3):
        assert client.put(f"{P}/pages/{ids[0]}", json={"title": f"v{i}"}, headers=t.h()).status_code == 200
    v = client.get(f"{P}/pages/{ids[0]}/versions", headers=t.h()).json()
    assert [x["version_number"] for x in v["items"]] == [3, 2, 1]


# ── publish / public serving ───────────────────────────────────────────

def test_publish_flow_and_public_hardening(client, tenant):
    slug = f"pub-{uuid.uuid4().hex[:8]}"
    page = make_page(client, tenant, slug=slug, content=EVIL)
    pid = page["id"]
    assert client.put(f"{P}/pages/{pid}", json={"custom_css": "a{color:red;background:url(http://x/y)}"},
                      headers=tenant.h()).status_code == 200
    # draft is not public
    assert client.get(f"{P}/public/{slug}").status_code == 404
    pub = client.post(f"{P}/pages/{pid}/publish", headers=tenant.h("manager"))
    assert pub.status_code == 200 and pub.json()["version"] >= 1
    r = client.get(f"{P}/public/{slug}")
    assert r.status_code == 200
    body = r.json()
    assert "custom_js" not in body
    assert "url(" not in body["custom_css"] and "color:red" in body["custom_css"]
    assert "<script" not in str(body["content"])
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "script-src" not in r.headers["content-security-policy"]
    detail = client.get(f"{P}/pages/{pid}", headers=tenant.h()).json()
    assert detail["status"] == "published" and detail["published_at"] and detail["published_version"] == pub.json()["version"]
    # unpublish removes it
    assert client.post(f"{P}/pages/{pid}/unpublish", headers=tenant.h("manager")).status_code == 200
    assert client.get(f"{P}/public/{slug}").status_code == 404


def test_published_slug_cannot_be_claimed_by_other_tenant(client):
    a, b = Tenant(), Tenant()
    slug = f"shared-{uuid.uuid4().hex[:8]}"
    pa, pb = make_page(client, a, slug=slug), make_page(client, b, slug=slug)
    assert client.post(f"{P}/pages/{pa['id']}/publish", headers=a.h()).status_code == 200
    assert client.post(f"{P}/pages/{pb['id']}/publish", headers=b.h()).status_code == 409
    served = client.get(f"{P}/public/{slug}").json()
    assert served["id"] == pa["id"]


def test_public_ambiguous_slug_serves_nothing(client):
    """Legacy data: two tenants published the same slug before the unique index existed."""
    a, b = Tenant(), Tenant()
    slug = f"legacy-{uuid.uuid4().hex[:8]}"
    pa, pb = make_page(client, a, slug=slug), make_page(client, b, slug=slug)
    eng = create_engine(f"sqlite:///{_DB}")
    with eng.begin() as c:
        c.execute(text("UPDATE portal_pages SET status='published' WHERE slug=:s"), {"s": slug})
    assert client.get(f"{P}/public/{slug}").status_code == 404


def test_public_rate_limit(client, tenant, monkeypatch):
    monkeypatch.setattr(main._public_limiter, "max_requests", 3)
    for _ in range(3):
        assert client.get(f"{P}/public/nothing-here").status_code == 404
    assert client.get(f"{P}/public/nothing-here").status_code == 429


# ── submissions ────────────────────────────────────────────────────────

def _published(client, tenant):
    slug = f"sub-{uuid.uuid4().hex[:8]}"
    p = make_page(client, tenant, slug=slug)
    assert client.post(f"{P}/pages/{p['id']}/publish", headers=tenant.h()).status_code == 200
    return p, slug


def test_submission_rules(client, tenant):
    page, slug = _published(client, tenant)
    ok = {"page_id": page["id"], "form_data": {"name": "Ann", "email": "ann@x.co"}, "consent": True}
    assert client.post(f"{P}/submissions", json={**ok, "consent": False}).status_code == 422
    assert client.post(f"{P}/submissions", json={k: v for k, v in ok.items() if k != "consent"}).status_code == 422
    # honeypot: silently accepted, nothing stored
    hp = client.post(f"{P}/submissions", json={**ok, "website": "http://spam"})
    assert hp.status_code == 200 and "id" not in hp.json()
    r = client.post(f"{P}/submissions", json=ok)
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    by_slug = client.post(f"{P}/submissions", json={"slug": slug, "form_data": {"n": 1}, "consent": True})
    assert by_slug.status_code == 200
    subs = client.get(f"{P}/pages/{page['id']}/submissions", headers=tenant.h()).json()
    assert subs["total"] == 2 and all(i["consent_given"] for i in subs["items"])
    assert client.get(f"{P}/pages/{page['id']}/submissions", headers=tenant.h("viewer")).status_code == 403
    # draft/unknown pages
    assert client.post(f"{P}/submissions", json={**ok, "page_id": str(uuid.uuid4())}).status_code == 404
    draft = make_page(client, tenant)
    assert client.post(f"{P}/submissions", json={**ok, "page_id": draft["id"]}).status_code == 404


def test_submission_size_and_shape_caps_and_rate_limit(client, tenant, monkeypatch):
    page, _ = _published(client, tenant)
    big = {"page_id": page["id"], "consent": True, "form_data": {"m": "x" * 20000}}
    assert client.post(f"{P}/submissions", json=big).status_code == 413
    nested = {"page_id": page["id"], "consent": True, "form_data": {"m": {"a": 1}}}
    assert client.post(f"{P}/submissions", json=nested).status_code == 422
    assert client.post(f"{P}/submissions", content=b"not json").status_code == 422
    main._submit_limiter._requests.clear()
    ok = {"page_id": page["id"], "consent": True, "form_data": {"a": "b"}}
    statuses = [client.post(f"{P}/submissions", json=ok).status_code for _ in range(7)]
    assert statuses[:5] == [200] * 5 and 429 in statuses[5:]
    # a different page is a different bucket
    other, _ = _published(client, tenant)
    assert client.post(f"{P}/submissions", json={**ok, "page_id": other["id"]}).status_code == 200


# ── analytics ──────────────────────────────────────────────────────────

def test_analytics_zero_then_real(client):
    t = Tenant()
    z = client.get(f"{P}/analytics/summary", headers=t.h()).json()
    assert z["views"] == 0 and z["submissions"] == 0 and z["conversion_rate"] == 0.0
    assert z["top_pages"] == [] and sum(d["views"] for d in z["daily"]) == 0
    page, slug = _published(client, t)
    for _ in range(4):
        assert client.get(f"{P}/public/{slug}", params={"utm_source": "fb"}).status_code == 200
    client.post(f"{P}/submissions", json={"page_id": page["id"], "consent": True, "form_data": {"a": 1}})
    s = client.get(f"{P}/analytics/summary", headers=t.h()).json()
    assert s["views"] == 4 and s["submissions"] == 1 and s["conversion_rate"] == 25.0
    assert s["unique_visitors"] == 1
    assert s["top_pages"][0]["slug"] == slug and s["top_pages"][0]["views"] == 4
    assert s["top_sources"][0] == {"source": "fb", "views": 4}
    assert s["pages"]["published"] == 1
    # other tenants see none of it
    assert client.get(f"{P}/analytics/summary", headers=Tenant().h()).json()["views"] == 0


# ── sharing ────────────────────────────────────────────────────────────

@pytest.fixture
def mail(monkeypatch):
    sent = []

    async def fake_get(service, path, **kw):
        return [{"id": "mb1", "is_active": True}]

    async def fake_post(service, path, json=None, **kw):
        sent.append(json)
        return {"status": "sent", "message_id": "m-1"}

    monkeypatch.setattr(main, "service_get", fake_get)
    monkeypatch.setattr(main, "service_post", fake_post)
    return sent


def test_share_lifecycle(client, tenant, mail):
    page = make_page(client, tenant, content=EVIL)
    r = client.post(f"{P}/pages/{page['id']}/share",
                    json={"recipient_email": "Boss@Example.com", "message": "please review"}, headers=tenant.h())
    assert r.status_code == 201
    share = r.json()
    assert share["email_status"] == "sent" and share["recipient_email"] == "boss@example.com"
    assert mail[0]["to"] == ["boss@example.com"] and share["share_url"] in mail[0]["body_text"]
    token = share["share_url"].rsplit("/", 1)[1]
    assert len(token) >= 40
    # draft page previewable via token; hardened, no-index, no custom js
    v = client.get(f"{P}/shared/{token}")
    assert v.status_code == 200 and v.json()["preview"] is True and "custom_js" not in v.json()
    assert "<script" not in str(v.json()["content"])
    assert "noindex" in v.headers["x-robots-tag"]
    assert client.get(f"{P}/shared/{token}x").status_code == 404
    listing = client.get(f"{P}/pages/{page['id']}/shares", headers=tenant.h()).json()["items"]
    assert listing[0]["view_count"] == 1 and listing[0]["active"] is True and "token" not in listing[0]
    # token is not stored in clear
    eng = create_engine(f"sqlite:///{_DB}")
    with eng.begin() as c:
        stored = c.execute(text("SELECT token_hash FROM portal_page_shares")).scalars().all()
    assert token not in stored and security.hash_token(token) in stored
    # revoke
    assert client.post(f"{P}/shares/{share['id']}/revoke", headers=Tenant().h()).status_code == 404
    assert client.post(f"{P}/shares/{share['id']}/revoke", headers=tenant.h()).status_code == 200
    assert client.get(f"{P}/shared/{token}").status_code == 404


def test_share_expiry(client, tenant, mail):
    page = make_page(client, tenant)
    share = client.post(f"{P}/pages/{page['id']}/share", json={"recipient_email": "a@b.co", "expires_in_hours": 1},
                        headers=tenant.h()).json()
    token = share["share_url"].rsplit("/", 1)[1]
    assert client.get(f"{P}/shared/{token}").status_code == 200
    eng = create_engine(f"sqlite:///{_DB}")
    with eng.begin() as c:
        c.execute(text("UPDATE portal_page_shares SET expires_at='2000-01-01 00:00:00'"))
    assert client.get(f"{P}/shared/{token}").status_code == 404
    assert client.post(f"{P}/pages/{page['id']}/share", json={"recipient_email": "a@b.co", "expires_in_hours": 99999},
                       headers=tenant.h()).status_code == 422
    assert client.post(f"{P}/pages/{page['id']}/share", json={"recipient_email": "not-an-email"},
                       headers=tenant.h()).status_code == 422


def test_share_honours_suppression_and_reports_failures(client, tenant, mail, monkeypatch):
    page = make_page(client, tenant)

    async def suppressed(session, tenant_id, emails):
        return [], list(emails)

    monkeypatch.setattr(main.suppression, "filter_suppressed", suppressed)
    r = client.post(f"{P}/pages/{page['id']}/share", json={"recipient_email": "no@spam.co"}, headers=tenant.h())
    assert r.status_code == 201 and r.json()["email_status"] == "suppressed" and mail == []

    async def allow(session, tenant_id, emails):
        return list(emails), []

    monkeypatch.setattr(main.suppression, "filter_suppressed", allow)

    async def no_boxes(*a, **k):
        return []

    monkeypatch.setattr(main, "service_get", no_boxes)
    r = client.post(f"{P}/pages/{page['id']}/share", json={"recipient_email": "x@y.co"}, headers=tenant.h())
    assert r.status_code == 201 and r.json()["email_status"] == "no_mailbox"


# ── importer / SEO ─────────────────────────────────────────────────────

SITE = """<html lang="en"><head><title>Acme Fibre | Fast home internet in Gauteng</title>
<meta name="description" content="Uncapped fibre for homes and small businesses across Gauteng, installed in days with local support.">
<meta name="viewport" content="width=device-width"><meta property="og:image" content="/og.png">
<link rel="canonical" href="https://acme.example/"><script>steal()</script></head>
<body><h1>Fibre that just works</h1><p>Intro paragraph about fibre.</p><h2>Plans</h2><p>Uncapped plans from R499.</p>
<img src="/hero.jpg" alt="Router"><img src="javascript:alert(1)" alt="x"><a href="/pricing">Pricing</a>
<iframe src="http://evil"></iframe><script>alert(1)</script></body></html>"""


def _site_transport(handler=None):
    def default(request: httpx.Request):
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=SITE)
    return httpx.MockTransport(handler or default)


def test_import_site_structured_and_sanitised(client, tenant, monkeypatch):
    monkeypatch.setattr(fetcher, "_transport", _site_transport())
    r = client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h())
    assert r.status_code == 200, r.text
    d = r.json()["content"]
    assert d["title"].startswith("Acme Fibre") and d["blocks"][0]["type"] == "hero"
    assert d["blocks"][0]["heading"] == "Fibre that just works"
    assert d["og_image"] == "https://acme.example/og.png"
    assert [i["src"] for i in d["images"]] == ["https://acme.example/hero.jpg"]
    blob = r.text.lower()
    assert "<script" not in blob and "steal()" not in blob and "<iframe" not in blob and "javascript:" not in blob
    assert client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h("viewer")).status_code == 403


@pytest.mark.parametrize("url", [
    "http://acme.example/", "https://127.0.0.1/", "https://localhost/", "https://169.254.169.254/latest/meta-data/",
    "https://user:pw@acme.example/", "https://acme.example:8443/", "file:///etc/passwd", "https://2130706433/",
])
def test_import_rejects_unsafe_urls(client, tenant, url):
    assert client.post(f"{P}/import/site", json={"url": url}, headers=tenant.h()).status_code == 422


def test_import_revalidates_every_redirect(client, tenant, monkeypatch):
    hops = []

    def handler(request):
        hops.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://10.0.0.5/admin"})

    monkeypatch.setattr(fetcher, "_transport", _site_transport(handler))
    r = client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h())
    assert r.status_code == 422 and "not allowed" in r.json()["detail"].lower()
    assert hops == ["https://acme.example/"]  # the private hop was never requested

    # resolver that flips to a private IP on the second hostname
    monkeypatch.setattr(fetcher, "_resolver", lambda host, port: ["10.1.1.1"] if host == "evil.example" else ["93.184.216.34"])
    monkeypatch.setattr(fetcher, "_transport", _site_transport(lambda req: httpx.Response(301, headers={"location": "https://evil.example/"})))
    assert client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h()).status_code == 422


def test_import_caps_and_content_type(client, tenant, monkeypatch):
    monkeypatch.setattr(fetcher, "_transport", _site_transport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")))
    assert client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h()).status_code == 415
    loop = lambda r: httpx.Response(302, headers={"location": "https://acme.example/again"})  # noqa: E731
    monkeypatch.setattr(fetcher, "_transport", _site_transport(loop))
    assert client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h()).status_code == 502
    huge = "<html><body><p>" + "word " * 600_000 + "</p></body></html>"
    monkeypatch.setattr(fetcher, "_transport", _site_transport(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, text=huge)))
    r = client.post(f"{P}/import/site", json={"url": "https://acme.example/"}, headers=tenant.h())
    assert r.status_code == 200 and r.json()["fetch"]["truncated"] is True


def test_seo_audit_real_scoring(client, tenant, monkeypatch):
    monkeypatch.setattr(fetcher, "_transport", _site_transport())
    r = client.post(f"{P}/seo/audit", json={"url": "https://acme.example/", "keyword": "fibre"}, headers=tenant.h())
    assert r.status_code == 200, r.text
    a = r.json()
    checks = {c["id"]: c for c in a["checks"]}
    assert checks["title"]["status"] == "pass" and checks["meta_description"]["status"] == "pass"
    assert checks["h1"]["status"] == "pass" and checks["canonical"]["status"] == "pass"
    assert checks["image_alt"]["status"] == "pass" or checks["image_alt"]["status"] == "warn"
    assert checks["word_count"]["status"] == "fail"  # tiny page
    assert checks["viewport"]["status"] == "pass" and checks["structured_data"]["status"] == "warn"
    assert a["keyword"]["in_title"] and a["keyword"]["in_h1"] and a["keyword"]["in_meta_description"]
    assert 0 < a["score"] < 100 and a["grade"] in "ABCDF"
    assert a["stats"]["word_count"] == int(checks["word_count"]["detail"].split()[0])

    bare = "<html><body><p>hi</p></body></html>"
    monkeypatch.setattr(fetcher, "_transport", _site_transport(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, text=bare)))
    b = client.post(f"{P}/seo/audit", json={"url": "https://acme.example/"}, headers=tenant.h()).json()
    assert b["score"] < a["score"] and {c["id"]: c for c in b["checks"]}["title"]["status"] == "fail"


def test_seo_keywords_honest_without_provider(client, tenant, monkeypatch):
    monkeypatch.delenv("SEO_PROVIDER_API_KEY", raising=False)
    r = client.post(f"{P}/seo/keywords", json={"keywords": ["fibre", "wifi"]}, headers=tenant.h())
    assert r.status_code == 200
    d = r.json()
    assert d["provider_configured"] is False and d["keywords"] == []
    assert "search_volume" not in r.text


def test_sitemap_shape(client):
    t = Tenant()
    _, slug = _published(client, t)
    d = client.get(f"{P}/seo/sitemap", headers=t.h()).json()
    assert d["urls"][0]["loc"] == f"/portal/{slug}" and "base_url" in d
