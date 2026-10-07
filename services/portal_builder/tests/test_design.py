import json

import pytest

from services.portal_builder import design

P = "/api/v1/portal/design/suggest"


def proposal():
    return {"message": "A draft for your review", "draft": {
        "title": "Home fibre", "description": "Enquire about home connectivity",
        "theme": {"accent": "cyan", "appearance": "light"},
        "blocks": [{"type": "hero", "heading": "Connect your home", "subheading": "Tell us what you need.", "cta_label": "Enquire", "cta_url": "#enquiry"},
                   {"type": "features", "heading": "Designed around your home", "items": [{"title": "Stay connected", "body": "Find a plan that suits your needs."}]}],
    }}


@pytest.fixture(autouse=True)
def reset_design_limiter():
    design.limiter._requests.clear()


def test_design_requires_editor_and_never_calls_provider_for_reader(client, tenant, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Provider called without authorization")
    monkeypatch.setattr(design.openrouter, "chat_completion", forbidden)
    assert client.post(P, headers=tenant.h("customer"), json={"prompt": "Build a page"}).status_code == 403


def test_generation_returns_editable_sanitized_proposal_without_saving(client, tenant, monkeypatch):
    captured = {}
    raw = proposal()
    raw["draft"]["blocks"][0].update(heading='<script>bad()</script>Safe headline', image="javascript:bad()")
    async def answer(payload, **kwargs):
        captured.update(payload)
        return ({"choices": [{"message": {"content": json.dumps(raw)}}]}, "configured-model")
    monkeypatch.setattr(design.openrouter, "chat_completion", answer)
    response = client.post(P, headers=tenant.h(), json={"prompt": "Build a fibre page"})
    assert response.status_code == 200
    block = response.json()["draft"]["blocks"][0]
    assert block["heading"] == "Safe headline" and block["image"] == ""
    assert "tools" not in captured
    assert client.get("/api/v1/portal/pages", headers=tenant.h()).json()["total"] == 0


def test_revision_supplies_current_draft_and_selected_section(client, tenant, monkeypatch):
    current = proposal()["draft"]
    async def answer(payload, **kwargs):
        request = json.loads(payload["messages"][1]["content"])
        assert request["current"] == current and request["selected_section"] == 1
        assert request["prompt"] == "Shorten the benefit copy"
        return ({"choices": [{"message": {"content": "```json\n" + json.dumps(proposal()) + "\n```"}}]}, "configured-model")
    monkeypatch.setattr(design.openrouter, "chat_completion", answer)
    assert client.post(P, headers=tenant.h(), json={"prompt": "Shorten the benefit copy", "current": current, "selected_section": 1}).status_code == 200


@pytest.mark.parametrize("content", ["not JSON", '{"draft":{"title":"x","blocks":[]}}', json.dumps({"draft": {"title": "x", "blocks": [{"type": "html", "body": "<script>bad()</script>"}]}})])
def test_invalid_ai_response_is_a_failure_not_a_template(client, tenant, monkeypatch, content):
    async def answer(*args, **kwargs):
        return ({"choices": [{"message": {"content": content}}]}, "configured-model")
    monkeypatch.setattr(design.openrouter, "chat_completion", answer)
    assert client.post(P, headers=tenant.h(), json={"prompt": "Build a page"}).status_code == 502


def test_missing_provider_is_explicit(client, tenant, monkeypatch):
    async def offline(*args, **kwargs):
        return None
    monkeypatch.setattr(design.openrouter, "chat_completion", offline)
    response = client.post(P, headers=tenant.h(), json={"prompt": "Build a page"})
    assert response.status_code == 503 and "unchanged" in response.json()["detail"]


@pytest.mark.parametrize("body", [{"prompt": "   "}, {"prompt": "Build", "current": {"data": "x" * 60001}}, {"prompt": "Build", "selected_section": 24}, {"prompt": "Build", "tenant_id": "untrusted"}])
def test_design_bounds_and_unknown_identity_rejected(client, tenant, body):
    assert client.post(P, headers=tenant.h(), json=body).status_code == 422


def test_design_rate_limit_is_per_verified_caller(client, tenant, monkeypatch):
    async def offline(*args, **kwargs):
        return None
    monkeypatch.setattr(design.openrouter, "chat_completion", offline)
    for _ in range(12):
        assert client.post(P, headers=tenant.h(), json={"prompt": "Build a page"}).status_code == 503
    assert client.post(P, headers=tenant.h(), json={"prompt": "Build a page"}).status_code == 429


def test_editing_a_published_page_does_not_change_public_snapshot(client, tenant):
    from services.portal_builder.tests.conftest import make_page
    page = make_page(client, tenant, title="Original title", description="Original description", content={"blocks": [{"type": "hero", "heading": "Live heading"}]}, theme={"accent": "cyan"})
    path = f"/api/v1/portal/pages/{page['id']}"
    assert client.post(path + "/publish", headers=tenant.h()).status_code == 200
    assert client.put(path, headers=tenant.h(), json={"title": "Revised title", "description": "Draft description", "content": {"blocks": [{"type": "hero", "heading": "Draft heading"}]}, "theme": {"accent": "orange"}}).status_code == 200
    public = client.get(f"/api/v1/portal/public/{page['slug']}").json()
    assert public["title"] == "Original title" and public["description"] == "Original description"
    assert public["content"]["blocks"][0]["heading"] == "Live heading" and public["theme"]["accent"] == "cyan"
    assert "_publication" not in public["content"]
    assert client.get(path, headers=tenant.h()).json()["content"]["blocks"][0]["heading"] == "Draft heading"
    assert client.post(path + "/publish", headers=tenant.h()).status_code == 200
    public = client.get(f"/api/v1/portal/public/{page['slug']}").json()
    assert public["title"] == "Revised title" and public["theme"]["accent"] == "orange"


def test_legacy_publication_is_frozen_before_first_new_edit(client, tenant):
    from sqlalchemy import update
    from services.portal_builder.main import PortalPage
    from services.portal_builder.tests.conftest import make_page, _engine
    page = make_page(client, tenant, title="Legacy page", content={"blocks": [{"type": "hero", "heading": "Legacy live copy"}]})
    path = f"/api/v1/portal/pages/{page['id']}"
    assert client.post(path + "/publish", headers=tenant.h()).status_code == 200
    import uuid
    with _engine.begin() as db:
        db.execute(update(PortalPage).where(PortalPage.id == uuid.UUID(page["id"])).values(published_version=None))
    assert client.put(path, headers=tenant.h(), json={"title": "New draft title", "content": {"blocks": [{"type": "hero", "heading": "New draft copy"}]}}).status_code == 200
    public = client.get(f"/api/v1/portal/public/{page['slug']}").json()
    assert public["title"] == "Legacy page" and public["content"]["blocks"][0]["heading"] == "Legacy live copy"
