"""Pure helpers behind the lead action menu (SPEC-lead-actions.md) — no DB, no network.

Run with cwd = services/sales:  PYTHONPATH=../.. python -m pytest tests/ -q
"""

import os
import sys
from types import SimpleNamespace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.sales.lead_actions import (  # noqa: E402
    OUTBOUND_QUEUE,
    campaign_audience,
    email_html,
    lead_audience_member,
)


def lead(**kw):
    base = dict(first_name="Cape Town Dental", last_name="Studio", email="info@ctds.co.za", phone="+27 21 000 0000",
                address="Main Road, Sea Point", source="COMPANY_SEARCH")
    base.update(kw)
    return SimpleNamespace(**base)


def test_email_html_escapes_and_keeps_line_breaks():
    html = email_html("Hi <b>there</b>\n\nOur 50 Mbps & 100 Mbps plans.")
    assert "&lt;b&gt;" in html and "<b>" not in html
    assert "&amp;" in html
    assert html.count("<br>") == 2


def test_lead_audience_member_uses_business_shape():
    m = lead_audience_member(lead())
    assert m["name"] == "Cape Town Dental Studio"
    assert m["email"] == "info@ctds.co.za" and m["phone"] == "+27 21 000 0000"
    assert m["address"] == "Main Road, Sea Point"
    assert m["category"] == "Company Search"
    assert set(m) == {"name", "category", "address", "phone", "email", "website", "lat", "lng"}


def test_campaign_audience_is_one_idempotent_audience_per_campaign():
    members = [lead_audience_member(lead()), lead_audience_member(lead(first_name="Sea Point", last_name="Hotel"))]
    body = campaign_audience("c-1", "Winter Fibre Promo", members)
    assert body["name"] == "Sales leads · Winter Fibre Promo"
    assert body["member_count"] == 2
    rules = body["rules"]
    assert (rules["type"], rules["source"], rules["source_id"]) == ("businesses", "sales_campaign", "c-1")
    assert rules["businesses"] == members


def test_outbound_queue_name():
    assert OUTBOUND_QUEUE == "Outbound queue"
