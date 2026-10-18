"""Sourcing logic: protocol validation, supply scoring, reading replies, drafting, discovery helpers. No DB, no network."""
import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

from services.inventory import sourcing as S


def test_protocol_defaults_and_validation():
    p = S.Protocol()
    assert p.outreach_requires_approval and p.min_quotes_before_award == 2 and p.max_suppliers_per_request == 5 and not p.share_target_price
    with pytest.raises(ValidationError):
        S.Protocol(max_suppliers_per_request=0)
    with pytest.raises(ValidationError):
        S.Protocol(min_supplier_score=101)
    with pytest.raises(ValidationError):
        S.Protocol(unknown_rule=True)                                   # typos are refused, not silently ignored
    with pytest.raises(ValidationError):
        S.Protocol(weights={"price": 0, "lead_time": 0, "performance": 0, "completeness": 0})


def test_stored_protocol_falls_back_to_defaults():
    assert S.protocol_from(None).min_quotes_before_award == 2
    assert S.protocol_from({"min_quotes_before_award": 3, "legacy_key": 1}).min_quotes_before_award == 3     # unknown stored keys are dropped
    assert S.protocol_from({"max_suppliers_per_request": 9999}).max_suppliers_per_request == 5               # an invalid stored value does not block


def test_supply_score_rewards_price_speed_track_record_and_completeness():
    field = [{"unit_price": 100, "lead_time_days": 10}, {"unit_price": 125, "lead_time_days": 5}, {"unit_price": 90, "lead_time_days": 30}]
    w = S.Weights()
    cheap = S.supply_score({"unit_price": 90, "lead_time_days": 30, "moq": 10, "valid_until": date(2027, 1, 1)}, field, w, 80)
    fast = S.supply_score({"unit_price": 125, "lead_time_days": 5, "moq": 10, "valid_until": date(2027, 1, 1)}, field, w, 80)
    assert cheap["price_pts"] == 100 and fast["lead_pts"] == 100 and cheap["price_pts"] > fast["price_pts"] and fast["lead_pts"] > cheap["lead_pts"]
    thin = S.supply_score({"unit_price": 100, "lead_time_days": 10}, field, w, None)
    assert thin["completeness_pts"] == 50 and thin["performance_pts"] == 50 and thin["track_record"] is False
    only_price = S.supply_score({"unit_price": 100, "lead_time_days": 10}, field, S.Weights(price=100, lead_time=0, performance=0, completeness=0), None)
    assert only_price["score"] == 90.0                                  # 90 / 100 of the best price, nothing else counts


def test_patterns_read_a_typical_reply():
    t = "Hi, we can supply. Unit price R 1,249.50 each excl VAT. Lead time 2 weeks. MOQ: 20 units. Quote valid until 2026-12-31. Regards"
    r = S.regex_reply(t)
    assert (r["unit_price"], r["lead_time_days"], r["moq"], r["valid_until"], r["declined"]) == (1249.5, 14, 20, "2026-12-31", False)
    assert S.regex_reply("Sorry, we no longer stock this model.")["declined"] is True
    assert S.regex_reply("Thanks for your email.")["unit_price"] is None            # never guesses


def test_ai_output_is_cleaned_before_use():
    c = S.clean_reply({"unit_price": "-5", "lead_time_days": "abc", "moq": 12.0, "valid_until": "not a date", "declined": 0, "notes": "x" * 900})
    assert c["unit_price"] is None and c["lead_time_days"] is None and c["moq"] == 12 and c["valid_until"] is None and len(c["notes"]) == 400


def test_reading_a_reply_falls_back_to_patterns_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    r = asyncio.run(S.read_reply("Unit price R 99.00 each, lead time 3 days"))
    assert r["method"] == "patterns" and r["unit_price"] == 99.0 and r["lead_time_days"] == 3


VIEW = {"name": "Outdoor camera", "nature": "Physical item", "family": "Equipment", "definition": {
    "description": "4K PoE outdoor camera with night vision.", "identifiers": ["Serial number", "MAC address"], "price": 1500, "costs": [{"name": "secret cost", "amount": 800}],
    "provisioning": {"protocol": "TR-069", "profile": "CAM-X"}}}


def test_drafts_never_leak_our_costs_or_prices():
    subject, body = S.template_request("RFQ", VIEW, "Acme ISP", 40, date(2026, 12, 1), 700.0, False, 5, "RFQ-AB12-000001")
    assert subject.startswith("[RFQ-AB12-000001]") and "x 40" in subject
    low = body.lower()
    for forbidden in ("1500", "secret cost", "800", "700", "margin"):
        assert forbidden not in low, forbidden
    assert "serial number and mac address" in low and "TR-069" in body and "2026-12-01" in body and "RFQ-AB12-000001" in body
    _, with_target = S.template_request("RFQ", VIEW, "Acme ISP", 40, None, 700.0, True, 5, "RFQ-1")
    assert "R700.00" in with_target                                     # only when the protocol allows it
    s_rfi, b_rfi = S.template_request("RFI", VIEW, "Acme ISP", None, None, None, False, 7, "RFI-1")
    assert "information" in s_rfi.lower() and "within 7 days" in b_rfi


def test_draft_request_falls_back_to_the_template_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    d = asyncio.run(S.draft_request("RFQ", VIEW, "Acme ISP", 10, None, None, S.Protocol(), "RFQ-9"))
    assert d["drafted_by"] == "template" and d["subject"].startswith("[RFQ-9]")


def test_discovery_helpers():
    assert S.domain_of("https://www.Metro-Fibre.co.za/products?x=1") == "metro-fibre.co.za"
    assert S.prospect_name("Buy cameras | Metro Fibre Supplies", "metro-fibre.co.za") == "Metro Fibre"
    assert S.fit_score("4K outdoor camera supplier South Africa", ["Outdoor", "camera", "wifi"]) == 67
    assert S.fit_score("anything", []) == 0
    q = S.discovery_question(VIEW, "za", "")
    assert "South Africa" in q and "Outdoor camera" in q and len(q) <= 900
    assert any(m in "takealot.com" for m in S.MARKETPLACES)
