"""Pure-logic tests for services/common/event_bus.py (SPEC-event-bus.md).

The SQL paths (publish in a transaction, SKIP LOCKED claiming, retries and
dead-lettering) are live-verified against Postgres.

Run with cwd = services/fno_intelligence:  python -m pytest tests/ -q
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.common.event_bus import (  # noqa: E402
    MAX_ATTEMPTS,
    handler_for,
    is_exhausted,
    normalise_event_type,
    pattern_matches,
    retry_delay_seconds,
)


@pytest.mark.parametrize("pattern,event_type,expected", [
    ("*", "sales.lead.created", True),
    ("sales.lead.created", "sales.lead.created", True),
    ("sales.lead.created", "sales.lead.created_extra", False),
    ("sales.*", "sales.lead.created", True),
    ("sales.lead.*", "sales.lead.created", True),
    ("sales.lead.*", "sales.deal.won", False),
    ("sales.*", "salesforce.lead.created", False),
    ("portal.*", "sales.lead.created", False),
])
def test_pattern_matches(pattern, event_type, expected):
    assert pattern_matches(pattern, event_type) is expected


def test_handler_for_prefers_exact_then_longest_prefix():
    exact, lead, any_ = object(), object(), object()
    handlers = {"*": any_, "sales.lead.*": lead, "sales.lead.email_requested": exact}
    assert handler_for(handlers, "sales.lead.email_requested") is exact
    assert handler_for(handlers, "sales.lead.created") is lead
    assert handler_for(handlers, "portal.cart.abandoned") is any_
    assert handler_for({"sales.*": lead}, "portal.cart.abandoned") is None


def test_retry_delay_grows_and_caps():
    delays = [retry_delay_seconds(n) for n in range(1, MAX_ATTEMPTS)]
    assert delays[0] == 10
    assert delays == sorted(delays)
    assert delays[-1] == 3600


def test_is_exhausted_after_max_attempts():
    assert not is_exhausted(MAX_ATTEMPTS - 1)
    assert is_exhausted(MAX_ATTEMPTS)


@pytest.mark.parametrize("raw,expected", [
    ("portal.cart.abandoned", "portal.cart.abandoned"),
    ("  Portal.Cart.Abandoned ", "portal.cart.abandoned"),
    ("sales.lead.email_requested", "sales.lead.email_requested"),
])
def test_normalise_event_type_accepts_dotted_names(raw, expected):
    assert normalise_event_type(raw) == expected


@pytest.mark.parametrize("raw", ["", "abandoned", "portal..cart", "portal.cart abandoned", "1portal.cart", "portal.*", "x" * 130])
def test_normalise_event_type_rejects_bad_names(raw):
    with pytest.raises(ValueError):
        normalise_event_type(raw)
