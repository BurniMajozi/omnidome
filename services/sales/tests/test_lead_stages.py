"""Lead stage rules (SPEC-lead-lifecycle.md) — no DB.

Run with cwd = services/sales:  python -m pytest tests/ -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lead_stages import (  # noqa: E402
    StageChangeError,
    format_reference,
    lead_status_for_deal,
    plan_stage_change,
)

STAGES = ["Prospecting", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]


def plan(**kw):
    kw.setdefault("stage_names", STAGES)
    kw.setdefault("deal_status", None)
    return plan_stage_change(**kw)


# ── Lead phase (no deal yet) ───────────────────────────────────────────────

def test_lead_phase_move_sets_status_only():
    p = plan(current_status="NEW", target_status="CONTACTED")
    assert (p.lead_status, p.create_deal_at, p.move_deal_to, p.close_deal, p.closed) == (
        "CONTACTED", None, None, None, False)


def test_disqualify_closes_the_lead():
    p = plan(current_status="CONTACTED", target_status="DISQUALIFIED", reason="Out of coverage")
    assert p.lead_status == "DISQUALIFIED" and p.closed and p.reason == "Out of coverage"


def test_reopening_a_disqualified_lead_is_allowed():
    p = plan(current_status="DISQUALIFIED", target_status="NEW")
    assert p.lead_status == "NEW" and not p.closed


def test_unknown_lead_status_is_rejected():
    with pytest.raises(StageChangeError) as exc:
        plan(current_status="NEW", target_status="MAYBE")
    assert exc.value.status_code == 400


# ── Entering the pipeline ──────────────────────────────────────────────────

def test_choosing_a_board_stage_without_a_deal_creates_the_deal_there():
    p = plan(current_status="QUALIFIED", target_stage="proposal")
    assert p.create_deal_at == "Proposal" and p.lead_status == "CONVERTED" and p.move_deal_to is None


def test_closed_won_without_a_deal_creates_then_wins():
    p = plan(current_status="QUALIFIED", target_stage="Closed Won")
    assert p.create_deal_at == "Prospecting" and p.close_deal == "won" and p.lead_status == "WON" and p.closed


def test_closed_lost_without_a_deal_disqualifies_instead_of_making_a_lost_deal():
    p = plan(current_status="NEW", target_stage="Closed Lost", reason="No budget")
    assert p.create_deal_at is None and p.lead_status == "DISQUALIFIED" and p.closed


def test_unknown_board_stage_is_rejected():
    with pytest.raises(StageChangeError) as exc:
        plan(current_status="NEW", target_stage="Somewhere")
    assert exc.value.status_code == 400


# ── In the pipeline (deal open): the deal is the source of truth ───────────

def test_moving_an_open_deal_between_board_stages():
    p = plan(current_status="CONVERTED", deal_status="OPEN", target_stage="Negotiation")
    assert p.move_deal_to == "Negotiation" and p.create_deal_at is None and p.lead_status == "CONVERTED"


def test_closed_won_on_an_open_deal():
    p = plan(current_status="CONVERTED", deal_status="OPEN", target_stage="Closed Won")
    assert p.close_deal == "won" and p.lead_status == "WON" and p.closed


def test_closed_lost_needs_a_reason():
    with pytest.raises(StageChangeError) as exc:
        plan(current_status="CONVERTED", deal_status="OPEN", target_stage="Closed Lost")
    assert exc.value.status_code == 400
    p = plan(current_status="CONVERTED", deal_status="OPEN", target_stage="Closed Lost", reason="Went with competitor")
    assert p.close_deal == "lost" and p.lead_status == "LOST" and p.reason == "Went with competitor"


def test_lead_in_pipeline_cannot_go_back_to_a_lead_stage():
    with pytest.raises(StageChangeError) as exc:
        plan(current_status="CONVERTED", deal_status="OPEN", target_status="CONTACTED")
    assert exc.value.status_code == 409


def test_closed_deal_cannot_be_moved():
    with pytest.raises(StageChangeError) as exc:
        plan(current_status="WON", deal_status="WON", target_stage="Negotiation")
    assert exc.value.status_code == 409


# ── Legacy status values (field app, old UI) ───────────────────────────────

@pytest.mark.parametrize("legacy,stage", [("PROPOSAL", "Proposal"), ("NEGOTIATION", "Negotiation"), ("CONVERTED", "Prospecting")])
def test_legacy_pipeline_statuses_map_to_board_stages(legacy, stage):
    p = plan(current_status="QUALIFIED", target_status=legacy)
    assert p.create_deal_at == stage and p.lead_status == "CONVERTED"


def test_legacy_converted_on_a_lead_already_in_pipeline_is_a_no_op():
    p = plan(current_status="CONVERTED", deal_status="OPEN", target_status="CONVERTED")
    assert p.create_deal_at is None and p.move_deal_to is None and p.close_deal is None


def test_legacy_lost_without_deal_means_disqualified():
    p = plan(current_status="NEW", target_status="LOST", reason="Not interested")
    assert p.lead_status == "DISQUALIFIED"


def test_exactly_one_target_is_required():
    with pytest.raises(StageChangeError):
        plan(current_status="NEW")
    with pytest.raises(StageChangeError):
        plan(current_status="NEW", target_status="CONTACTED", target_stage="Proposal")


# ── Helpers ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("deal_status,expected", [("OPEN", "CONVERTED"), ("WON", "WON"), ("LOST", "LOST")])
def test_lead_status_mirrors_deal(deal_status, expected):
    assert lead_status_for_deal(deal_status) == expected


def test_reference_format():
    assert format_reference(42) == "LD-000042"
    assert format_reference(None) is None
