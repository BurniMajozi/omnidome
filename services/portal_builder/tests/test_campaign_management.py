import pytest
from services.portal_builder.tests.conftest import Tenant, make_page

P = "/api/v1/portal"

def test_campaign_rejects_other_tenant_page(client, tenant):
    page = make_page(client, Tenant())
    result = client.post(f"{P}/campaigns", headers=tenant.h(), json={"name": "Private campaign", "page_id": page["id"]})
    assert result.status_code == 404

@pytest.mark.parametrize("budget", [-1, "Infinity", "NaN"])
def test_campaign_budget_must_be_nonnegative_finite(client, tenant, budget):
    assert client.post(f"{P}/campaigns", headers=tenant.h(), json={"name": "Budget", "budget_zar": budget}).status_code == 422

def test_campaign_and_profile_management_roundtrip(client, tenant):
    page = make_page(client, tenant)
    campaign = client.post(f"{P}/campaigns", headers=tenant.h(), json={"name": "Fibre launch", "page_id": page["id"], "budget_zar": 120.50}).json()
    assert client.get(f"{P}/campaigns", headers=tenant.h()).json()["items"][0]["id"] == campaign["id"]
    assert client.post(f"{P}/campaigns/{campaign['id']}/launch", headers=tenant.h("portal_writer")).status_code == 403
    assert client.post(f"{P}/campaigns/{campaign['id']}/launch", headers=tenant.h()).status_code == 200
    assert client.post(f"{P}/campaigns/{campaign['id']}/complete", headers=tenant.h()).json()["status"] == "completed"
    assert client.post(f"{P}/seo-profiles", headers=tenant.h(), json={"name": "Fibre", "target_keywords": ["fibre"], "sitemap_enabled": True}).status_code == 201
    assert client.get(f"{P}/seo-profiles", headers=tenant.h()).json()[0]["target_keywords"] == ["fibre"]
