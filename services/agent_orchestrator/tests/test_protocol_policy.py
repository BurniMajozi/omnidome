"""Editable protocol limits: validation, defaults, admin-only change, and the sourcing tools' wiring. No DB, no network."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from services.agent_orchestrator.routes import protocols as P
from services.agent_orchestrator.tools import tool_registry


def test_policy_validation():
    assert P.ProtocolPolicy().ap2_max_expiry_minutes == 1440
    for bad in ({"ucp_auto_approve_limit_zar": -1}, {"ap2_max_expiry_minutes": 0}, {"ap2_max_expiry_minutes": 5000}, {"surprise": 1}):
        with pytest.raises(ValidationError):
            P.ProtocolPolicy(**bad)


def test_only_organisation_admins_may_change_limits():
    def ctx(*roles, platform=False):
        return SimpleNamespace(roles=list(roles), is_platform_admin=platform)
    P._require_policy_admin(ctx("admin"))
    P._require_policy_admin(ctx("owner"))
    P._require_policy_admin(ctx(platform=True))
    for role in ("support", "hr_admin", "inventory_manager"):
        with pytest.raises(HTTPException) as e:
            P._require_policy_admin(ctx(role))
        assert e.value.status_code == 403


def test_stored_policy_falls_back_to_defaults_when_invalid():
    class Row:
        config = {"ucp_auto_approve_limit_zar": 2500, "ap2_max_expiry_minutes": 99999, "legacy": 1}

    class Session:
        async def execute(self, _):
            return SimpleNamespace(scalar_one_or_none=lambda: Row())
    p = asyncio.run(P.load_policy(Session(), "t"))
    assert p.ucp_auto_approve_limit_zar == 500          # one bad value discards the stored row rather than blocking commerce

    class Good(Row):
        config = {"ucp_auto_approve_limit_zar": 2500, "legacy": 1}

    class Session2(Session):
        async def execute(self, _):
            return SimpleNamespace(scalar_one_or_none=lambda: Good())
    assert asyncio.run(P.load_policy(Session2(), "t")).ucp_auto_approve_limit_zar == 2500


def test_procurement_agent_can_buy_but_everything_that_commits_waits_for_a_person():
    names = {t.name: t for t in tool_registry.filter_for_agent("procurement")}
    for needed in ("sourcing_get_protocol", "sourcing_reorder_suggestions", "sourcing_find_suppliers", "sourcing_create_request", "sourcing_compare_quotes",
                   "sourcing_send_request", "sourcing_award_request", "inventory_create_purchase_order"):
        assert needed in names, needed
    gated = {n for n, t in names.items() if t.requires_approval}
    assert {"sourcing_send_request", "sourcing_award_request", "inventory_create_purchase_order", "inventory_submit_purchase_order"} <= gated
    assert not {"sourcing_create_request", "sourcing_find_suppliers", "sourcing_get_protocol"} & gated      # preparing work is free
    # others can look at what is being bought, never buy
    for agent in ("executive", "assistant", "products"):
        tools = {t.name for t in tool_registry.filter_for_agent(agent)}
        assert "sourcing_reorder_suggestions" in tools and "sourcing_send_request" not in tools and "inventory_create_purchase_order" not in tools
    assert "sourcing_send_request" not in {t.name for t in tool_registry.filter_for_agent("customer_facing")}
