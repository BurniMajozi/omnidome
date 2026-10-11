"""Draft replacement-cost floors. Never used to alter an existing invoice."""
from decimal import Decimal, ROUND_CEILING
from services.common.platform_pricing import catalog


def draft_rate_card(usd_zar=None):
    card = catalog()["provider_rate_card"]
    assumptions = dict(card["assumptions"])
    if usd_zar is not None:
        assumptions["usd_zar"] = usd_zar
    a = {key: Decimal(str(value)) for key, value in assumptions.items()}
    if a["usd_zar"] <= 0 or not a["usd_zar"].is_finite():
        raise ValueError("Invalid FX scenario")
    # Conservative cash contribution: customer VAT increases the payment amount;
    # fee VAT is an expense here rather than silently assuming it is recovered.
    fee = a["gateway_rate"] * (1+a["customer_vat"]) * (1+a["gateway_vat"])
    denominator = 1-a["target_margin"]-fee
    if denominator <= 0:
        raise ValueError("Margin cannot be funded after payment fees")
    rows = []
    for entry in card["rates"]:
        provider = Decimal(str(entry["cost_usd"])) * a["usd_zar"] * (1+a["fx_buffer"])
        allocation = Decimal(str(entry["allocation_zar"]))
        fixed = a["gateway_fixed_zar"] * (1+a["gateway_vat"]) / Decimal(str(entry["invoice_units"]))
        cost = provider+allocation+fixed
        floor = (cost/denominator).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        price = Decimal(str(entry["price_zar"]))
        margin = 1-fee-cost/price
        rows.append({**entry, "minimum_net_zar":str(floor),
                     "scenario_cost_zar":str(cost.quantize(Decimal("0.0001"))),
                     "scenario_margin_percent":str((margin*100).quantize(Decimal("0.01"))),
                     "meets_target":price >= floor})
    return {"status":"draft", "reviewed_at":card["reviewed_at"], "assumptions":assumptions,
            "charges_enabled":False,"rates":rows,
            "limitation":"Scenario only. Confirm procurement, actual FX, fixed subscriptions, hosting, support and billable units before publishing; existing contracts are unchanged."}
