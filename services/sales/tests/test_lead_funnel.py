"""Unit tests for lead channel normalization and funnel logic (SPEC-lead-lifecycle.md).

Run with cwd = services/sales:  python -m pytest tests/test_lead_funnel.py -q
"""

import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lead_stages import normalize_channel, SALES_CHANNELS


def test_sales_channels_defined():
    assert "FIELD_SALES" in SALES_CHANNELS
    assert "CALL_CENTER_OUTBOUND" in SALES_CHANNELS
    assert "CALL_CENTER_INBOUND" in SALES_CHANNELS
    assert "MARKETING" in SALES_CHANNELS
    assert "PORTAL_WEBSITE" in SALES_CHANNELS
    assert "TENDER" in SALES_CHANNELS
    assert "COMPANY_SEARCH" in SALES_CHANNELS


def test_normalize_channel_exact_matches():
    assert normalize_channel("FIELD_SALES") == "FIELD_SALES"
    assert normalize_channel("marketing") == "MARKETING"
    assert normalize_channel("call-center-outbound") == "CALL_CENTER_OUTBOUND"


def test_normalize_channel_legacy_sources():
    assert normalize_channel(None, "FIELD_VISIT") == "FIELD_SALES"
    assert normalize_channel(None, "door_to_door") == "FIELD_SALES"
    assert normalize_channel(None, "PORTAL_WEBSITE") == "PORTAL_WEBSITE"
    assert normalize_channel(None, "web_form") == "PORTAL_WEBSITE"
    assert normalize_channel(None, "inbound_call") == "CALL_CENTER_INBOUND"
    assert normalize_channel(None, "telesales") == "CALL_CENTER_OUTBOUND"
    assert normalize_channel(None, "tender_rfq") == "TENDER"
    assert normalize_channel(None, "campaign_ad") == "MARKETING"


def test_normalize_channel_from_notes():
    assert normalize_channel(None, "lead", notes="Captured via company search for fiber") == "COMPANY_SEARCH"


def test_normalize_channel_fallback():
    assert normalize_channel(None, None) == "OTHER"
    assert normalize_channel("", "") == "OTHER"
