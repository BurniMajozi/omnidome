"""One versioned commercial catalogue for the public page, provisioning and invoices."""
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


def catalog():
    local = Path(__file__).with_name("platform-pricing.json")
    source = local if local.exists() else Path(__file__).parents[2] / "apps/web/lib/platform-pricing.json"
    return json.loads(source.read_text(encoding="utf-8"))


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle: str | None = None
    modules: dict[str, Literal["starter", "professional", "enterprise"]] = Field(default_factory=dict)
    period: Literal["monthly", "annually"] = "monthly"
    seats: int | None = Field(None, ge=1, le=100000)

    @model_validator(mode="after")
    def valid_catalogue(self):
        data = catalog()
        ids = {m["id"] for m in data["modules"]}
        if self.bundle and self.bundle not in data["bundles"]: raise ValueError("Unknown bundle")
        if set(self.modules) - ids: raise ValueError("Unknown or unpriced module")
        if not self.bundle and not self.modules: raise ValueError("Choose a bundle or at least one module")
        return self


def quote(selection: Selection):
    data = catalog()
    months = 12 if selection.period == "annually" else 1
    factor = (Decimal(100) - Decimal(data["annual_discount_percent"])) / 100 if months == 12 else Decimal(1)
    bundle = data["bundles"].get(selection.bundle) if selection.bundle else None
    chosen = {m: bundle["tier"] for m in bundle["modules"]} if bundle else {}
    chosen.update(selection.modules)
    included = bundle["seats"] if bundle else 1
    seats = selection.seats or included
    if seats < included: raise ValueError(f"This selection includes {included} seats; choose at least that many")
    lines = []
    def add(label, monthly):
        # Preserve the public page's per-month annual discount rounding.
        monthly = (Decimal(monthly) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        lines.append({"description": label, "monthly_net_zar": str(monthly), "quantity": months, "net_zar": str(monthly * months)})
    if bundle: add(bundle["name"] + " bundle", bundle["monthly_price"])
    for module in data["modules"]:
        tier = chosen.get(module["id"])
        if not tier: continue
        if bundle and module["id"] in bundle["modules"]:
            if tier != bundle["tier"]: raise ValueError("Change to modular pricing to use different tiers for bundled panels")
            continue
        add(module["name"] + " (" + tier + ")", module["prices"][tier])
    extra_seat_price = bundle["extra_seat_price"] if bundle else 45
    if seats > included: add(f"{seats - included} extra seats", (seats - included) * extra_seat_price)
    net = sum((Decimal(l["net_zar"]) for l in lines), Decimal(0))
    vat_rate = Decimal(os.getenv("PLATFORM_VAT_RATE", "0.15"))
    if not 0 <= vat_rate <= 1: raise ValueError("Invalid platform VAT rate")
    vat = (net * vat_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = net + vat
    usage_policy = {**data["usage_policy"], "monthly_credits": bundle["credits"] if bundle else data["usage_policy"]["allowances"][max(chosen.values(), key=lambda x: ["starter", "professional", "enterprise"].index(x))]}
    return {"catalog_version": data["version"], "usage_policy": usage_policy, "selection": {**selection.model_dump(), "modules": chosen, "seats": seats},
            "name": bundle["name"] if bundle else "Custom modules", "tier": "FREE" if selection.bundle == "starter" and net == 0 else (bundle["tier"] if bundle else max(chosen.values(), key=lambda x: ["starter", "professional", "enterprise"].index(x))).upper(),
            "period": selection.period, "currency": data["currency"], "lines": lines,
            "seats": seats, "seat_price": extra_seat_price, "entitlements": sorted(chosen),
            "net_zar": str(net.quantize(Decimal("0.01"))), "vat_zar": str(vat), "total_zar": str(total.quantize(Decimal("0.01"))),
            "amount_cents": int(total * 100), "monthly_net_zar": str(net / months), "vat_rate": str(vat_rate)}
