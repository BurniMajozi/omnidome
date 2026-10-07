"""Fee-policy API + cancellation integration on the in-memory SQLite harness (routes mounted on a bare app)."""
import os
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

from services.billing import fee_policies as fp  # noqa: E402
from services.billing.models import BillingFinanceOutbox, CancellationRequest, Invoice, InvoiceLine, Subscription, TerminationFee  # noqa: E402
from services.billing.models_fees import ContractFeeSnapshot, FeeCalculation, FeePolicy  # noqa: E402
from services.billing.tests.sqlite_harness import make_session_factory, patch_sessions  # noqa: E402
from services.common.auth import AuthContext, get_auth_context  # noqa: E402

D = Decimal
TENANT = uuid.uuid4()
CLERK, ADMIN, ADMIN2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
WHO = {"clerk": (CLERK, ["manager"]), "admin": (ADMIN, ["billing_admin"]), "admin2": (ADMIN2, ["billing_admin"])}
TERM_START = date(2026, 1, 15)
EFFECTIVE = date(2026, 11, 15)  # 10 whole months in


@pytest.fixture
def env(monkeypatch):
    get_session = make_session_factory()
    patch_sessions(monkeypatch, get_session)
    import importlib
    for name in ("services.billing.routes.fee_policies", "services.billing.routes.cancellations"):
        mod = importlib.import_module(name)
        if hasattr(mod, "get_session"):
            monkeypatch.setattr(mod, "get_session", get_session)
    from services.billing.routes.cancellations import router as cancel_router
    from services.billing.routes.fee_policies import router as fee_router
    from services.billing.routes.subscriptions import router as sub_router

    app = FastAPI()
    for r in (fee_router, cancel_router, sub_router):
        app.include_router(r)

    async def fake_ctx(request: Request):
        uid, roles = WHO[request.headers.get("x-who", "admin")]
        return AuthContext(user_id=uid, tenant_id=TENANT, roles=roles, rbac_loaded=True)

    app.dependency_overrides[get_auth_context] = fake_ctx
    monkeypatch.setenv("BILLING_ENFORCE_ROLES", "true")
    client = TestClient(app)
    client.get_session = get_session
    return client


def H(who="admin"):
    return {"x-who": who}


POLICY = {
    "name": "24m", "trigger_types": ["cancellation", "downgrade"], "term_months": 24, "is_default": True,
    "components": [{"code": "router"}, {"code": "activation"}, {"code": "installation"}],
    "router_credit": {"enabled": True, "mode": "offset_router_component"},
    "auto_approve_waiver_limit_zar": "200.00",
    "waivers": [{"reason_code": "fno_fault", "required_tier": "none"},
                {"reason_code": "relocation_in_coverage", "required_tier": "clerk"}],
}
SNAP_BODY = {"term_start": TERM_START.isoformat(), "term_months": 24, "components": [
    {"code": "router", "amount": "1500"}, {"code": "activation", "amount": "500"}, {"code": "installation", "amount": "1000"}]}


def make_sub(client, price="699.00", plan="Fibre 100"):
    with client.get_session() as s:
        sub = Subscription(tenant_id=TENANT, customer_id=uuid.uuid4(), plan=plan, status="active",
                           base_price_zar=D(price), billing_anchor=TERM_START)
        s.add(sub)
        s.flush()
        return str(sub.id), str(sub.customer_id)


def make_policy(client, **over):
    r = client.post("/fee-policies", json={**POLICY, **over}, headers=H())
    assert r.status_code == 201, r.text
    return r.json()


def make_snapshot(client, sub_id, **over):
    r = client.post("/fee-policies/snapshots", json={"subscription_id": sub_id, **SNAP_BODY, **over}, headers=H("clerk"))
    assert r.status_code == 201, r.text
    return r.json()


def simulate(client, sub_id, **over):
    r = client.post("/fee-policies/simulate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat(), **over}, headers=H("clerk"))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------------------------

def test_policy_crud_roles_and_versioning(env):
    r = env.post("/fee-policies", json=POLICY, headers=H("clerk"))
    assert r.status_code == 403
    p = make_policy(env)
    assert p["version"] == 1 and p["term_months"] == 24
    upd = env.put(f"/fee-policies/{p['id']}", json={**POLICY, "name": "24m v2", "term_months": 18}, headers=H())
    assert upd.status_code == 200
    v2 = upd.json()
    assert v2["version"] == 2 and v2["policy_key"] == p["policy_key"] and v2["id"] != p["id"]
    old = env.get(f"/fee-policies/{p['id']}", headers=H()).json()
    assert old["superseded_by"] == v2["id"] and old["effective_to"] is not None and old["term_months"] == 24
    assert len(env.get(f"/fee-policies/{v2['id']}/versions", headers=H()).json()) == 2
    assert len(env.get("/fee-policies", headers=H("clerk")).json()) == 1  # superseded hidden
    assert env.delete(f"/fee-policies/{v2['id']}", headers=H("clerk")).status_code == 403
    assert env.delete(f"/fee-policies/{v2['id']}", headers=H()).json()["deactivated"] is True
    assert env.post("/fee-policies", json={**POLICY, "components": []}, headers=H()).status_code == 422


def test_default_template_is_admin_only_and_not_duplicated(env):
    assert env.post("/fee-policies/templates/default-24m", headers=H("clerk")).status_code == 403
    assert env.get("/fee-policies", headers=H()).json() == []  # never auto-seeded
    r = env.post("/fee-policies/templates/default-24m", headers=H())
    assert r.status_code == 201
    t = r.json()
    assert t["term_months"] == 24 and [c["code"] for c in t["components"]] == ["router", "activation", "installation"]
    assert all(c["amount_source"] == "snapshot" and c["fixed_amount"] is None for c in t["components"])  # no fake amounts
    assert env.post("/fee-policies/templates/default-24m", headers=H()).status_code == 409


def test_simulate_canonical_example_with_snapshot(env):
    make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    out = simulate(env, sub_id)
    bd = out["breakdown"]
    assert out["snapshot_missing"] is False and out["persisted"] is False
    assert bd["months_elapsed"] == "10" and bd["months_remaining"] == "14"
    assert bd["totals"]["fee_net"] == "1750.00" and bd["totals"]["fee_vat"] == "262.50" and bd["totals"]["fee_total"] == "2012.50"
    assert out["policy"]["version"] == 1 and len(out["inputs_hash"]) == 64
    assert any("1500.00 x 14/24 = 875.00" in l["formula"] for l in bd["lines"] if l["kind"] == "component")
    with env.get_session() as s:
        assert s.query(FeeCalculation).count() == 0  # simulate persists nothing


def test_simulate_downgrade_trigger_and_snapshot_inputs_mode(env):
    make_policy(env)
    out = env.post("/fee-policies/simulate", headers=H("clerk"), json={
        "snapshot": SNAP_BODY, "trigger": "downgrade", "effective_date": EFFECTIVE.isoformat()}).json()
    assert out["breakdown"]["trigger"] == "downgrade" and out["breakdown"]["totals"]["fee_net"] == "1750.00"
    nope = env.post("/fee-policies/simulate", headers=H("clerk"), json={
        "snapshot": SNAP_BODY, "trigger": "relocation", "effective_date": EFFECTIVE.isoformat()})
    assert nope.status_code == 404  # no policy covers that trigger
    both = env.post("/fee-policies/simulate", headers=H("clerk"), json={"snapshot": SNAP_BODY, "subscription_id": str(uuid.uuid4())})
    assert both.status_code == 422


def test_snapshot_missing_flagged_and_fixed_amounts_used(env):
    make_policy(env, components=[{"code": "router", "amount_source": "fixed", "fixed_amount": "1200"}])
    sub_id, _ = make_sub(env)
    out = simulate(env, sub_id)
    assert out["snapshot_missing"] is True and "snapshot_missing" in out["flags"]
    assert out["breakdown"]["totals"]["fee_net"] == "700.00"  # 1200 x 14/24


def test_snapshot_is_immutable_against_price_and_policy_changes(env):
    p = make_policy(env, components=[{"code": "router", "amount_source": "fixed", "fixed_amount": "1500"},
                                     {"code": "activation", "amount_source": "fixed", "fixed_amount": "500"},
                                     {"code": "installation", "amount_source": "fixed", "fixed_amount": "1000"}])
    sub_id, _ = make_sub(env)
    snap = make_snapshot(env, sub_id)
    # later: catalogue prices change and the subscription is repriced
    env.put(f"/fee-policies/{p['id']}", headers=H(), json={**POLICY, "components": [
        {"code": "router", "amount_source": "fixed", "fixed_amount": "9999"},
        {"code": "activation", "amount_source": "fixed", "fixed_amount": "9999"},
        {"code": "installation", "amount_source": "fixed", "fixed_amount": "9999"}]})
    with env.get_session() as s:
        s.get(Subscription, uuid.UUID(sub_id)).base_price_zar = D("1999.00")
    out = simulate(env, sub_id)
    assert out["snapshot_id"] == snap["id"] and out["breakdown"]["totals"]["fee_net"] == "1750.00"
    # re-posting is refused; superseding adds a version and leaves v1 untouched
    again = env.post("/fee-policies/snapshots", json={"subscription_id": sub_id, **SNAP_BODY}, headers=H("clerk"))
    assert again.status_code == 409
    v2 = make_snapshot(env, sub_id, supersede=True, components=[{"code": "router", "amount": "2000"}])
    assert v2["version"] == 2
    allv = env.get(f"/fee-policies/snapshots?subscription_id={sub_id}&all_versions=true", headers=H()).json()
    assert [(s["version"], s["is_current"]) for s in allv] == [(2, True), (1, False)]
    assert allv[1]["components"][0]["amount"] == "1500.00"


def test_subscription_create_hook_snapshots_from_policy_fixed_amounts(env):
    make_policy(env, components=[{"code": "router", "amount_source": "fixed", "fixed_amount": "1500"},
                                 {"code": "installation", "amount_source": "fixed", "fixed_amount": "1000"}])
    r = env.post("/subscriptions", headers=H(), json={"customer_id": str(uuid.uuid4()), "plan": "Fibre 100", "base_price_zar": "599.00"})
    assert r.status_code == 201, r.text
    snaps = env.get(f"/fee-policies/snapshots?subscription_id={r.json()['id']}", headers=H()).json()
    assert len(snaps) == 1 and snaps[0]["source"] == "auto_create" and snaps[0]["term_months"] == 24
    assert {c["code"]: c["amount"] for c in snaps[0]["components"]} == {"router": "1500.00", "installation": "1000.00"}


def test_subscription_create_hook_is_silent_without_policy(env):
    r = env.post("/subscriptions", headers=H(), json={"customer_id": str(uuid.uuid4()), "plan": "Fibre 100", "base_price_zar": "599.00"})
    assert r.status_code == 201
    assert env.get(f"/fee-policies/snapshots?subscription_id={r.json()['id']}", headers=H()).json() == []


def test_calculate_is_idempotent_and_input_change_supersedes(env):
    make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    body = {"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}
    a = env.post("/fee-policies/calculate", json=body, headers=H("clerk")).json()
    b = env.post("/fee-policies/calculate", json=body, headers=H("clerk")).json()
    assert a["created"] is True and b["created"] is False and a["id"] == b["id"]
    assert a["fee_total_zar"] == "2012.50" and a["status"] == "calculated"
    c = env.post("/fee-policies/calculate", json={**body, "router_returned": True, "router_condition": "good"}, headers=H("clerk")).json()
    assert c["created"] is True and c["id"] != a["id"] and c["fee_total_zar"] == "1006.25"
    listed = env.get(f"/fee-policies/calculations?subscription_id={sub_id}", headers=H("clerk")).json()
    assert [x["id"] for x in listed] == [c["id"]]  # the older one is superseded
    assert env.get(f"/fee-policies/calculations/{a['id']}", headers=H("clerk")).json()["status"] == "superseded"
    # flipping back to the first inputs revives that row instead of inserting a duplicate
    a2 = env.post("/fee-policies/calculate", json=body, headers=H("clerk")).json()
    assert a2["id"] == a["id"] and a2["created"] is False and a2["status"] == "calculated"
    with env.get_session() as s:
        assert s.query(FeeCalculation).count() == 2


def test_waive_permissions_limits_and_self_approval(env):
    make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    calc = env.post("/fee-policies/calculate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}, headers=H("clerk")).json()
    url = f"/fee-policies/calculations/{calc['id']}/waive"
    small = {"reason_code": "relocation_in_coverage", "reason": "moved within coverage", "amount_zar": "150.00"}
    # clerk created the fee; within the auto-approve limit nothing needs a second person
    ok = env.post(url, json=small, headers=H("clerk"))
    assert ok.status_code == 200, ok.text
    assert ok.json()["calculation"]["amount_due_zar"] == "1862.50" and ok.json()["calculation"]["waived_total_zar"] == "150.00"
    # above the limit a clerk may not approve at all
    big = {"reason_code": "relocation_in_coverage", "reason": "bigger waiver", "amount_zar": "500.00"}
    assert env.post(url, json=big, headers=H("clerk")).status_code == 403
    # an unlisted reason needs admin even for a small amount
    assert env.post(url, json={"reason_code": "goodwill", "reason": "x y z", "amount_zar": "10"}, headers=H("clerk")).status_code == 403
    # admin approves a custom reason
    adm = env.post(url, json={"reason_code": "goodwill", "reason": "long standing customer", "amount_zar": "100.00"}, headers=H("admin"))
    assert adm.status_code == 200 and adm.json()["calculation"]["amount_due_zar"] == "1762.50"
    # bad inputs
    assert env.post(url, json={"reason_code": "goodwill", "reason": "too much", "amount_zar": "99999"}, headers=H("admin")).status_code == 400
    assert env.post(url, json={"reason_code": "goodwill", "reason": "both", "amount_zar": "1", "percent": "5"}, headers=H("admin")).status_code == 422
    audit = env.get(f"/fee-policies/audit?entity_id={calc['id']}", headers=H()).json()
    assert [a["action"] for a in audit].count("waived") == 2 and "calculated" in [a["action"] for a in audit]


def test_no_self_approval_above_limit_and_policy_override(env):
    p = make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    calc = env.post("/fee-policies/calculate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}, headers=H("admin")).json()
    url = f"/fee-policies/calculations/{calc['id']}/waive"
    body = {"reason_code": "goodwill", "reason": "retention gesture", "percent": "50"}
    own = env.post(url, json=body, headers=H("admin"))
    assert own.status_code == 403 and "self-approval" in own.json()["detail"]
    assert env.post(url, json=body, headers=H("admin2")).status_code == 200
    # a policy can explicitly allow self-approval (single-admin tenants)
    make_policy_v = env.put(f"/fee-policies/{p['id']}", headers=H(), json={**POLICY, "allow_self_approval": True}).json()
    calc2 = env.post("/fee-policies/calculate", headers=H("admin"), json={
        "subscription_id": sub_id, "effective_date": (EFFECTIVE + timedelta(days=40)).isoformat()}).json()
    assert calc2["policy_id"] == make_policy_v["id"]
    assert env.post(f"/fee-policies/calculations/{calc2['id']}/waive", json=body, headers=H("admin")).status_code == 200


def test_full_waiver_marks_waived_and_blocks_invoice(env):
    make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    calc = env.post("/fee-policies/calculate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}, headers=H("clerk")).json()
    w = env.post(f"/fee-policies/calculations/{calc['id']}/waive", headers=H("admin"),
                 json={"reason_code": "death", "reason": "account holder deceased", "percent": "100"})
    assert w.status_code == 200 and w.json()["calculation"]["status"] == "waived"
    inv = env.post(f"/fee-policies/calculations/{calc['id']}/invoice", headers=H("clerk"))
    assert inv.status_code == 409 and "nothing to invoice" in inv.json()["detail"]


def test_invoice_idempotent_one_line_per_component_draft_then_issued(env):
    make_policy(env)
    sub_id, cust = make_sub(env)
    make_snapshot(env, sub_id)
    calc = env.post("/fee-policies/calculate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}, headers=H("clerk")).json()
    url = f"/fee-policies/calculations/{calc['id']}/invoice"
    first = env.post(url, headers=H("clerk")).json()
    assert first["created"] is True and first["status"] == "draft" and first["invoice_type"] == "termination_fee"
    assert first["subtotal_zar"] == "1750.00" and first["vat_zar"] == "262.50" and first["total_zar"] == "2012.50"
    second = env.post(url, headers=H("clerk")).json()
    assert second["created"] is False and second["invoice_id"] == first["invoice_id"]
    with env.get_session() as s:
        assert s.query(Invoice).count() == 1
        lines = s.query(InvoiceLine).all()
        assert len(lines) == 3 and {l.line_type for l in lines} == {"termination_fee"}
        assert sum(l.total_zar for l in lines) == D("2012.50")
        assert s.query(BillingFinanceOutbox).count() == 0  # draft: nothing posted to the ledger
        c = s.get(FeeCalculation, uuid.UUID(calc["id"]))
        assert c.status == "invoiced" and c.invoice_id == uuid.UUID(first["invoice_id"])
    # waiving or recalculating after invoicing is refused / leaves the invoiced row alone
    assert env.post(f"/fee-policies/calculations/{calc['id']}/waive", headers=H("admin"),
                    json={"reason_code": "goodwill", "reason": "too late", "percent": "10"}).status_code == 409


def test_invoice_issue_posts_to_outbox_once(env):
    make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    calc = env.post("/fee-policies/calculate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}, headers=H("clerk")).json()
    url = f"/fee-policies/calculations/{calc['id']}/invoice"
    r = env.post(url, json={"issue": True}, headers=H("clerk")).json()
    assert r["status"] == "sent"
    env.post(url, json={"issue": True}, headers=H("clerk"))
    with env.get_session() as s:
        assert s.query(BillingFinanceOutbox).count() == 1


def test_invoice_after_partial_waiver_nets_correctly(env):
    make_policy(env)
    sub_id, _ = make_sub(env)
    make_snapshot(env, sub_id)
    calc = env.post("/fee-policies/calculate", json={"subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat()}, headers=H("clerk")).json()
    env.post(f"/fee-policies/calculations/{calc['id']}/waive", headers=H("clerk"),
             json={"reason_code": "relocation_in_coverage", "reason": "moved in coverage", "amount_zar": "115.00"})
    inv = env.post(f"/fee-policies/calculations/{calc['id']}/invoice", headers=H("clerk")).json()
    assert inv["total_zar"] == "1897.50" and inv["subtotal_zar"] == "1650.00" and inv["vat_zar"] == "247.50"


# --- cancellation integration ---------------------------------------------------------------------

def initiate(env, sub_id, **over):
    r = env.post("/cancellations/initiate", headers=H("clerk"), json={
        "subscription_id": sub_id, "effective_date": EFFECTIVE.isoformat(), **over})
    assert r.status_code == 201, r.text
    return r.json()


def test_cancellation_initiate_auto_calculates_without_human_step(env):
    make_policy(env)
    sub_id, _ = make_sub(env, price="299.00")  # below the retention threshold
    make_snapshot(env, sub_id)
    out = initiate(env, sub_id)
    assert out["fee_calculation_id"] and out["fee_total_zar"] == "2012.50" and out["fee_amount_due_zar"] == "2012.50"
    with env.get_session() as s:
        calc = s.get(FeeCalculation, uuid.UUID(out["fee_calculation_id"]))
        assert calc.auto_calculated and calc.cancellation_request_id == uuid.UUID(out["cancellation_id"])
        assert calc.termination_fee_id is not None
    st = env.get(f"/cancellations/{out['cancellation_id']}/status", headers=H("clerk")).json()
    assert st["fee_engine"] == "policy" and st["fee_calculation"]["breakdown"]["totals"]["fee_total"] == "2012.50"
    assert st["termination_fee"]["total_etf_zar"] == 1750.0


def test_cancellation_reason_code_drives_auto_waiver(env):
    make_policy(env)
    sub_id, _ = make_sub(env, price="299.00")
    make_snapshot(env, sub_id)
    out = initiate(env, sub_id, cancel_reason="fno_fault")
    assert out["fee_amount_due_zar"] == "0.00" and out["fee_total_zar"] == "0.00"


def test_calculate_etf_uses_engine_and_is_stable_across_calls(env):
    make_policy(env)
    sub_id, _ = make_sub(env, price="299.00")
    make_snapshot(env, sub_id)
    cid = initiate(env, sub_id)["cancellation_id"]
    r1 = env.post(f"/cancellations/{cid}/calculate-etf", headers=H("clerk")).json()
    r2 = env.post(f"/cancellations/{cid}/calculate-etf", headers=H("clerk")).json()
    assert r1["engine"] == "policy" and r1["calculation_id"] == r2["calculation_id"]
    assert r1["remaining_months"] == 14
    assert D(r1["router_charge_zar"]) == D("875.00") and D(r1["contract_etf_zar"]) == D("875.00")
    assert D(r1["total_etf_zar"]) == D("1750.00") and r1["amount_due_zar"] == "2012.50"
    with env.get_session() as s:
        assert s.query(TerminationFee).count() == 1  # one consistent row, not one per call
    withreason = env.post(f"/cancellations/{cid}/calculate-etf", headers=H("clerk"), json={"reason_code": "fno_fault"}).json()
    assert withreason["amount_due_zar"] == "0.00"


def test_legacy_fallback_when_no_policy_is_flagged(env):
    sub_id, _ = make_sub(env, price="299.00")
    out = initiate(env, sub_id)
    assert out["fee_calculation_id"] is None
    r = env.post(f"/cancellations/{out['cancellation_id']}/calculate-etf", headers=H("clerk")).json()
    assert r["engine"] == "legacy" and r["flags"] == ["legacy_no_policy"] and r["calculation_id"] is None
    st = env.get(f"/cancellations/{out['cancellation_id']}/status", headers=H("clerk")).json()
    assert st["fee_engine"] == "legacy" and st["fee_calculation"] is None
    proceed = env.post(f"/cancellations/{out['cancellation_id']}/proceed", headers=H("admin")).json()
    assert proceed["fee_invoice"]["legacy"] is True


def test_proceed_invoices_engine_fee_and_router_inspect_recomputes_before_invoice(env):
    make_policy(env, auto_invoice=True)
    sub_id, cust = make_sub(env, price="299.00")
    make_snapshot(env, sub_id)
    cid = initiate(env, sub_id)["cancellation_id"]
    # router comes back in good condition before the customer is invoiced: offset credit applies
    rr = env.post(f"/cancellations/{cid}/router-return", headers=H("clerk"), json={
        "cancellation_request_id": cid, "product_id": str(uuid.uuid4()), "serial_number": "SN1", "pickup_address": "1 Main"}).json()
    insp = env.post(f"/cancellations/router-returns/{rr['router_return_id']}/inspect", headers=H("admin"),
                    json={"router_return_id": rr["router_return_id"], "condition": "good"}).json()
    assert insp["fee_update"]["mode"] == "recalculated" and insp["fee_update"]["amount_due_zar"] == "1006.25"
    st = env.get(f"/cancellations/{cid}/status", headers=H("clerk")).json()
    assert st["fee_calculation"]["amount_due_zar"] == "1006.25" and st["termination_fee"]["router_returned"] is True
    proceed = env.post(f"/cancellations/{cid}/proceed", headers=H("admin")).json()
    fi = proceed["fee_invoice"]
    assert fi["status"] == "sent" and fi["total_zar"] == "1006.25"  # auto_invoice => issued
    again = env.post(f"/cancellations/{cid}/proceed", headers=H("admin")).json()
    assert again["fee_invoice"]["invoice_id"] == fi["invoice_id"]
    with env.get_session() as s:
        assert s.query(Invoice).count() == 1 and s.query(BillingFinanceOutbox).count() == 1
        assert s.query(TerminationFee).one().invoice_id == uuid.UUID(fi["invoice_id"])


def test_router_inspect_after_invoicing_reports_credit_note_instead_of_mutating(env):
    make_policy(env, auto_invoice=True)
    sub_id, _ = make_sub(env, price="299.00")
    make_snapshot(env, sub_id)
    cid = initiate(env, sub_id)["cancellation_id"]
    env.post(f"/cancellations/{cid}/proceed", headers=H("admin"))
    rr = env.post(f"/cancellations/{cid}/router-return", headers=H("clerk"), json={
        "cancellation_request_id": cid, "product_id": str(uuid.uuid4()), "serial_number": "SN2", "pickup_address": "1 Main"}).json()
    insp = env.post(f"/cancellations/router-returns/{rr['router_return_id']}/inspect", headers=H("admin"),
                    json={"router_return_id": rr["router_return_id"], "condition": "good"}).json()
    assert insp["fee_update"]["mode"] == "invoiced_no_change" and insp["fee_update"]["credit_note_required_zar"] == "1006.25"
    with env.get_session() as s:
        assert s.query(Invoice).one().total_zar == D("2012.50")


def test_initiate_auto_invoice_at_initiate_stage(env):
    make_policy(env, auto_invoice=True, auto_invoice_stage="initiate")
    sub_id, _ = make_sub(env, price="299.00")
    make_snapshot(env, sub_id)
    initiate(env, sub_id)
    with env.get_session() as s:
        inv = s.query(Invoice).one()
        assert inv.status == "sent" and inv.total_zar == D("2012.50")
