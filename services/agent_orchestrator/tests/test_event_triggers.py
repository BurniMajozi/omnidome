"""Event-triggered workflows (SPEC-lead-automations.md) — pure parts.

Run with cwd = services/agent_orchestrator:  python -m pytest tests -q
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.event_triggers import LEAD_WARMING_TEMPLATES  # noqa: E402
from services.agent_orchestrator.workflow_engine import resolve_deep, service_request  # noqa: E402
from services.common.event_bus import normalise_event_type  # noqa: E402

DATA = {
    "input": {"event": {"id": "e-1", "type": "portal.cart.abandoned",
                        "payload": {"contact": {"first_name": "Thandi", "email": "t@example.com"},
                                    "cart_total_zar": 899}}},
    "steps": {"lead": {"body": {"id": "lead-1"}}, "draft": {"content": "Hi Thandi"}},
}


def test_exact_placeholder_keeps_the_raw_value():
    assert resolve_deep("{{input.event.payload.contact}}", DATA) == {"first_name": "Thandi", "email": "t@example.com"}
    assert resolve_deep("{{input.event.payload.cart_total_zar}}", DATA) == 899


def test_placeholders_inside_text_become_strings():
    assert resolve_deep("Lead {{steps.lead.body.id}} for {{input.event.payload.contact.first_name}}", DATA) \
        == "Lead lead-1 for Thandi"


def test_nested_bodies_are_resolved():
    body = {"contact": "{{input.event.payload.contact}}", "meta": {"event": "{{input.event.id}}"},
            "items": ["{{steps.draft.content}}", 3]}
    assert resolve_deep(body, DATA) == {
        "contact": {"first_name": "Thandi", "email": "t@example.com"},
        "meta": {"event": "e-1"}, "items": ["Hi Thandi", 3]}


def test_missing_values_resolve_to_none_or_empty():
    assert resolve_deep("{{input.event.payload.nothing}}", DATA) is None
    assert resolve_deep("x{{input.nothing}}y", DATA) == "xy"


def test_service_request_targets_the_service_with_tenant_headers(monkeypatch):
    monkeypatch.setenv("SALES_SERVICE_URL", "http://sales:8002/")
    url, headers = service_request("sales", "/leads/lead-1/notes", tenant_id="t-1", user_id="u-1")
    assert url == "http://sales:8002/leads/lead-1/notes"
    assert headers == {"X-Tenant-Id": "t-1", "X-User-Id": "u-1"}


def test_lead_warming_templates_are_well_formed():
    assert {t["trigger_event"] for t in LEAD_WARMING_TEMPLATES} == {
        "portal.cart.abandoned", "portal.quote.requested", "portal.registration.inactive"}
    for t in LEAD_WARMING_TEMPLATES:
        normalise_event_type(t["trigger_event"])
        nodes = {n["id"]: n for n in t["definition"]["nodes"]}
        assert nodes["trigger"]["type"] == "trigger"
        for edge in t["definition"]["edges"]:
            assert edge["from"] in nodes and edge["to"] in nodes
        types = [n["type"] for n in t["definition"]["nodes"]]
        assert "agent_invoke" in types and types.count("http_request") == 2
        lead_step = nodes["lead"]["config"]
        assert lead_step["service"] == "sales" and lead_step["path"] == "/automation/lead-events"
        assert lead_step["body"].get("target_status") or lead_step["body"].get("target_stage")
