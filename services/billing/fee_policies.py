"""Early-termination / claw-back fee engine.

Part 1 (pure, no DB): policy schema + `calculate_fee` + `apply_waiver_to_breakdown`. Decimal-exact, ZAR,
VAT-aware and deterministic: the same policy + inputs always give the same breakdown and `inputs_hash`.
Part 2 (DB orchestration): policy selection, contract snapshots, persisted calculations, waivers,
invoicing, and the cancellation hooks. Routes live in routes/fee_policies.py.

Money conventions
  * Every amount is a Decimal rounded ROUND_HALF_UP to cents. Component owed = total x remaining / term
    (multiply first, round once per line), so R1500/R500/R1000 over 24 months, 14 remaining gives
    875.00 + 291.67 + 583.33 = 1750.00.
  * "basis" amounts follow vat.treatment: exclusive -> basis is net, VAT added per line; inclusive ->
    basis is gross, VAT extracted per line. Invoice and calculation totals therefore always agree.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("billing.fee_policies")

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")

BUILTIN_TRIGGERS = ("cancellation", "downgrade", "plan_change", "relocation", "suspension_abuse", "device_buyout")
CONDITIONS = ("new", "good", "fair", "damaged", "missing_parts", "missing")
DEFAULT_CONDITION_PCT = {"new": "100", "good": "90", "fair": "60", "damaged": "25", "missing_parts": "0", "missing": "0"}
TIER_ORDER = {"none": 0, "clerk": 1, "admin": 2}
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_:\-]{0,59}$")


def q2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def D(x: Any, default: str = "0") -> Decimal:
    if x is None or x == "":
        return Decimal(default)
    return x if isinstance(x, Decimal) else Decimal(str(x))


# ===========================================================================
# Policy schema (validated at the API boundary; stored as JSON)
# ===========================================================================

class ComponentIn(BaseModel):
    code: str
    label: Optional[str] = None
    # Fallback when the subscription has no contract snapshot carrying this component (a snapshot always wins).
    amount_source: Literal["snapshot", "fixed", "catalog"] = "snapshot"
    fixed_amount: Optional[Decimal] = Field(default=None, ge=0)
    recoverable: bool = True

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG.match(v):
            raise ValueError("component code must be a lowercase slug")
        return v


class MonthRule(BaseModel):
    # whole_months: elapsed = completed calendar months. prorated_days: elapsed includes the fraction
    # of the current month (days into the month / days in the month).
    mode: Literal["whole_months", "prorated_days"] = "whole_months"
    # whole_months only. up: a started month still counts as remaining (customer pays for it);
    # down: a started month counts as elapsed.
    remaining_rounding: Literal["up", "down"] = "up"


class WaiverRule(BaseModel):
    reason_code: str
    label: Optional[str] = None
    waive_percent: Decimal = Field(default=Decimal("100"), gt=0, le=100)
    # none: engine applies it automatically when the calculation carries this reason_code
    # clerk/admin: eligible only; applied through POST /calculations/{id}/waive by that tier or higher
    required_tier: Literal["none", "clerk", "admin"] = "admin"
    evidence_required: bool = False

    @field_validator("reason_code")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG.match(v):
            raise ValueError("reason_code must be a lowercase slug")
        return v


class RouterCredit(BaseModel):
    enabled: bool = False
    # offset_router_component: a returned router (not missing) wipes the router line.
    # credit_value_by_condition: credit = router line x condition_pct[condition] / 100.
    mode: Literal["offset_router_component", "credit_value_by_condition"] = "offset_router_component"
    router_component_code: str = "router"
    condition_pct: dict[str, Decimal] = Field(default_factory=lambda: {k: Decimal(v) for k, v in DEFAULT_CONDITION_PCT.items()})

    @field_validator("condition_pct")
    @classmethod
    def _pct(cls, v: dict) -> dict:
        for k, p in v.items():
            if p < 0 or p > 100:
                raise ValueError(f"condition_pct[{k}] must be 0..100")
        return v


class VatRule(BaseModel):
    rate: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    treatment: Literal["exclusive", "inclusive"] = "exclusive"


class PolicyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    trigger_types: list[str] = Field(default_factory=lambda: ["cancellation"])
    applies_to_plans: list[str] = Field(default_factory=list)  # plan ids or plan names; empty = all plans
    is_default: bool = False
    is_active: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    term_months: int = Field(default=24, ge=1, le=120)
    components: list[ComponentIn] = Field(default_factory=list)
    method: Literal["straight_line", "declining", "flat", "percent_of_remaining_rental"] = "straight_line"
    flat_percent: Decimal = Field(default=Decimal("100"), ge=0, le=100)          # method=flat
    rental_percent: Decimal = Field(default=Decimal("100"), ge=0, le=100)        # method=percent_of_remaining_rental
    month_rule: MonthRule = Field(default_factory=MonthRule)
    min_fee_zar: Optional[Decimal] = Field(default=None, ge=0)
    max_fee_zar: Optional[Decimal] = Field(default=None, ge=0)
    grace_period_days: int = Field(default=0, ge=0, le=365)   # cooling-off after term_start: no fee
    waivers: list[WaiverRule] = Field(default_factory=list)
    auto_approve_waiver_limit_zar: Decimal = Field(default=Decimal("0"), ge=0)  # gross; above it needs admin
    allow_self_approval: bool = False
    router_credit: RouterCredit = Field(default_factory=RouterCredit)
    vat: VatRule = Field(default_factory=VatRule)
    outstanding_balance: Literal["include", "exclude"] = "exclude"
    auto_invoice: bool = False
    auto_invoice_stage: Literal["initiate", "proceed"] = "proceed"
    invoice_due_days: int = Field(default=14, ge=0, le=365)
    # amount_source='catalog': {component_code: {plan_id | plan_name | "default": amount}}
    catalog_amounts: dict[str, dict[str, Decimal]] = Field(default_factory=dict)

    @field_validator("trigger_types")
    @classmethod
    def _triggers(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = t.strip().lower()
            if not _SLUG.match(t):
                raise ValueError(f"invalid trigger '{t}'")
            out.append(t)
        if not out:
            raise ValueError("at least one trigger type is required")
        return out

    def model_post_init(self, __context: Any) -> None:
        codes = [c.code for c in self.components]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate component codes")
        if self.method != "percent_of_remaining_rental" and not self.components:
            raise ValueError("components are required unless method is percent_of_remaining_rental")
        for c in self.components:
            if c.amount_source == "fixed" and c.fixed_amount is None:
                raise ValueError(f"component '{c.code}' uses fixed amounts but has no fixed_amount")
        if self.min_fee_zar is not None and self.max_fee_zar is not None and self.min_fee_zar > self.max_fee_zar:
            raise ValueError("min_fee_zar cannot exceed max_fee_zar")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to is before effective_from")


# Fields persisted as dedicated columns; everything else lives in the `config` JSON.
POLICY_COLUMN_FIELDS = ("name", "description", "trigger_types", "applies_to_plans", "is_default", "is_active",
                        "effective_from", "effective_to", "term_months")


def policy_config_from_input(p: PolicyIn) -> dict:
    cfg = p.model_dump(mode="json")
    for f in POLICY_COLUMN_FIELDS:
        cfg.pop(f, None)
    return cfg


def policy_to_engine(row: Any) -> dict:
    """Flat dict the pure engine consumes, from a FeePolicy row."""
    d = dict(row.config or {})
    d.update(id=str(row.id), policy_key=str(row.policy_key), version=row.version, name=row.name,
             term_months=row.term_months, trigger_types=list(row.trigger_types or []),
             applies_to_plans=list(row.applies_to_plans or []))
    return d


# ===========================================================================
# Part 1: pure engine
# ===========================================================================

def add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    m += 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def whole_months_between(start: date, end: date) -> int:
    if end < start:
        return 0
    m = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        last = monthrange(end.year, end.month)[1]
        if not (end.day == last and start.day > last):
            m -= 1
    return max(m, 0)


def month_position(term_start: date, effective: date, term: int, rule: dict) -> dict:
    """Months elapsed / remaining at `effective` under the policy's month rule."""
    mode = rule.get("mode", "whole_months")
    rounding = rule.get("remaining_rounding", "up")
    whole = whole_months_between(term_start, effective)
    partial_days = 0
    frac = Decimal("0")
    if effective >= term_start and whole < term:
        anchor = add_months(term_start, whole)
        nxt = add_months(term_start, whole + 1)
        partial_days = max((effective - anchor).days, 0)
        span = (nxt - anchor).days
        frac = Decimal(partial_days) / Decimal(span)
    if mode == "prorated_days":
        elapsed = Decimal(whole) + frac
    else:
        elapsed = Decimal(whole) + (Decimal(1) if (partial_days > 0 and rounding == "down") else Decimal(0))
    elapsed = min(elapsed, Decimal(term))
    remaining = Decimal(term) - elapsed
    return {"elapsed": elapsed, "remaining": remaining, "whole_months_elapsed": whole,
            "partial_days": partial_days, "mode": mode, "remaining_rounding": rounding}


def _fmt(d: Decimal) -> str:
    """Compact decimal text: 14, 13.5, 291.67."""
    s = format(d.normalize(), "f")
    return s if "." not in s else s.rstrip("0").rstrip(".")


def vat_split(amount: Decimal, rate: Decimal, treatment: str) -> tuple[Decimal, Decimal, Decimal]:
    """(net, vat, gross) of a basis amount."""
    if treatment == "inclusive":
        net = q2(amount / (Decimal(1) + rate)) if rate else amount
        return net, amount - net, amount
    vat = q2(amount * rate)
    return amount, vat, amount + vat


def _line(code: str, label: str, kind: str, basis: Decimal, vat_rule: dict, **extra: Any) -> dict:
    net, vat, gross = vat_split(basis, D(vat_rule.get("rate", "0.15")), vat_rule.get("treatment", "exclusive"))
    return {"code": code, "label": label, "kind": kind, "amount": basis, "net": net, "vat": vat, "gross": gross, **extra}


def resolve_component_amount(comp: dict, snapshot_amounts: dict, catalog: dict, plan_keys: list[str]) -> tuple[Decimal, str, Optional[str]]:
    """(amount, source_used, flag). snapshot -> fixed -> catalog fallback chain; flag when degraded."""
    code = comp["code"]
    src = comp.get("amount_source", "snapshot")
    fixed = comp.get("fixed_amount")
    cat = (catalog or {}).get(code) or {}
    cat_amount = next((cat[k] for k in [*plan_keys, "default"] if k and k in cat), None)
    # The contract snapshot always wins when it carries the component: that is what makes a customer's
    # liability immune to later price changes. amount_source only decides the fallback without one.
    if code in snapshot_amounts:
        return D(snapshot_amounts[code]), "snapshot", None
    if src == "snapshot":
        if fixed is not None:
            return D(fixed), "fixed", f"component_{code}_not_in_snapshot_used_fixed"
        if cat_amount is not None:
            return D(cat_amount), "catalog", f"component_{code}_not_in_snapshot_used_catalog"
        return ZERO, "unresolved", f"component_{code}_amount_unresolved"
    if src == "fixed":
        return D(fixed), "fixed", None
    if cat_amount is not None:
        return D(cat_amount), "catalog", None
    if fixed is not None:
        return D(fixed), "fixed", f"component_{code}_not_in_catalog_used_fixed"
    return ZERO, "unresolved", f"component_{code}_amount_unresolved"


def _recompute_totals(bd: dict) -> None:
    lines = bd["lines"]
    net = sum((l["net"] for l in lines), ZERO)
    vat = sum((l["vat"] for l in lines), ZERO)
    gross = sum((l["gross"] for l in lines), ZERO)
    waived = -sum((l["gross"] for l in lines if l["kind"] == "waiver"), ZERO)
    before = gross + waived
    bd["totals"] = {
        "fee_net": net, "fee_vat": vat, "fee_total": gross,
        "waived_total": waived, "total_before_waiver": before,
    }
    out = bd.get("outstanding_balance") or ZERO
    bd["totals"]["outstanding_balance"] = out
    bd["totals"]["total_payable"] = gross + out


def _waiver_line(vat_rule: dict, due_gross: Decimal, waive_gross: Decimal, code: str, label: str, **extra: Any) -> dict:
    rate = D(vat_rule.get("rate", "0.15"))
    vat = q2(waive_gross * rate / (Decimal(1) + rate)) if rate else ZERO
    return {"code": code, "label": label, "kind": "waiver", "amount": -(waive_gross if vat_rule.get("treatment") == "inclusive" else waive_gross - vat),
            "net": -(waive_gross - vat), "vat": -vat, "gross": -waive_gross, **extra}


def calculate_fee(policy: dict, inputs: dict) -> dict:
    """Pure fee calculation. `policy` is policy_to_engine(); `inputs`:

      term_start (date), term_months (int, from snapshot), components {code: amount}, monthly_rental_zar,
      plan_keys [ids/names], effective_date (date), trigger, reason_code, router_returned (bool),
      router_condition, outstanding_balance_zar, snapshot_present (bool)
    """
    flags: list[str] = []
    vat_rule = policy.get("vat") or {"rate": "0.15", "treatment": "exclusive"}
    method = policy.get("method", "straight_line")
    term = int(inputs.get("term_months") or policy["term_months"])
    term_start: date = inputs["term_start"]
    effective: date = inputs["effective_date"]
    if not inputs.get("snapshot_present", True):
        flags.append("snapshot_missing")
    if effective < term_start:
        flags.append("effective_before_term_start")

    pos = month_position(term_start, effective, term, policy.get("month_rule") or {})
    elapsed, remaining = pos["elapsed"], pos["remaining"]
    term_d = Decimal(term)
    lines: list[dict] = []
    snapshot_amounts = inputs.get("components") or {}
    catalog = policy.get("catalog_amounts") or {}
    plan_keys = [k for k in (inputs.get("plan_keys") or []) if k]

    if remaining <= 0:
        flags.append("term_completed")

    def unamortised_text(total: Decimal) -> str:
        return f"{total:.2f} x {_fmt(remaining)}/{term}"

    if method == "percent_of_remaining_rental":
        rental = D(inputs.get("monthly_rental_zar"))
        pct = D(policy.get("rental_percent", "100"))
        owed = q2(rental * remaining * pct / HUNDRED) if remaining > 0 else ZERO
        lines.append(_line(
            "remaining_rental", "Remaining rental", "component", owed, vat_rule,
            total_amount=rental, source="rental", recoverable=True, monthly_amortisation=rental,
            months_elapsed=elapsed, months_remaining=remaining, unamortised_fraction=None,
            formula=f"{rental:.2f}/month x {_fmt(remaining)} remaining months x {_fmt(pct)}% = {owed:.2f}"))
    else:
        for comp in policy.get("components") or []:
            total, source, flag = resolve_component_amount(comp, snapshot_amounts, catalog, plan_keys)
            if flag:
                flags.append(flag)
            label = comp.get("label") or comp["code"].replace("_", " ").title()
            monthly = q2(total / term_d)
            if not comp.get("recoverable", True):
                owed, frac, formula = ZERO, None, f"{label} is marked not recoverable"
            elif remaining <= 0:
                owed, frac, formula = ZERO, Decimal(0), f"{unamortised_text(total)} = 0.00 (term completed)"
            elif method == "declining":
                frac = remaining * (remaining + 1) / (term_d * (term_d + 1))
                owed = q2(total * frac)
                formula = (f"{total:.2f} x ({_fmt(remaining)} x ({_fmt(remaining)}+1)) / ({term} x ({term}+1))"
                           f" = {owed:.2f} (declining, sum-of-digits)")
            elif method == "flat":
                pct = D(policy.get("flat_percent", "100"))
                frac = pct / HUNDRED
                owed = q2(total * frac)
                formula = f"{total:.2f} x {_fmt(pct)}% = {owed:.2f} (flat while term remains)"
            else:
                frac = remaining / term_d
                owed = q2(total * remaining / term_d)
                formula = f"{total:.2f} x {_fmt(remaining)}/{term} = {owed:.2f}"
            lines.append(_line(
                comp["code"], label, "component", owed, vat_rule, total_amount=total, source=source,
                recoverable=bool(comp.get("recoverable", True)), monthly_amortisation=monthly,
                months_elapsed=elapsed, months_remaining=remaining, unamortised_fraction=frac, formula=formula))

    # --- router return credit -------------------------------------------------------------------
    rc = policy.get("router_credit") or {}
    router_credit_info: dict = {"enabled": bool(rc.get("enabled")), "applied": False}
    if rc.get("enabled"):
        code = rc.get("router_component_code", "router")
        rline = next((l for l in lines if l["kind"] == "component" and l["code"] == code), None)
        returned = bool(inputs.get("router_returned"))
        cond = (inputs.get("router_condition") or "").strip().lower() or None
        router_credit_info.update(mode=rc.get("mode"), returned=returned, condition=cond, router_component_code=code)
        if rline is None:
            flags.append("router_credit_no_router_component")
        elif returned and rline["amount"] > 0:
            if rc.get("mode") == "credit_value_by_condition":
                pcts = {**{k: Decimal(v) for k, v in DEFAULT_CONDITION_PCT.items()}, **{k: D(v) for k, v in (rc.get("condition_pct") or {}).items()}}
                if cond is None:
                    flags.append("router_condition_unknown_no_credit")
                    pct = Decimal(0)
                else:
                    pct = pcts.get(cond, Decimal(0))
                    if cond not in pcts:
                        flags.append("router_condition_unrecognised_no_credit")
            else:
                pct = Decimal(0) if cond in ("missing", "missing_parts") else HUNDRED
            credit = q2(rline["amount"] * pct / HUNDRED)
            if credit > 0:
                lines.append(_line(
                    "router_credit", "Router return credit", "router_credit", -credit, vat_rule,
                    formula=f"{rline['amount']:.2f} x {_fmt(pct)}% ({cond or 'returned'}) = {credit:.2f} credited"))
                router_credit_info.update(applied=True, credit_pct=pct, credit_basis_amount=credit)
        elif not returned:
            router_credit_info["note"] = "router not returned; no credit"

    # --- min / max cap (basis amounts, before waivers) --------------------------------------------
    subtotal = sum((l["amount"] for l in lines), ZERO)
    max_fee, min_fee = policy.get("max_fee_zar"), policy.get("min_fee_zar")
    if max_fee is not None and subtotal > D(max_fee):
        adj = D(max_fee) - subtotal
        lines.append(_line("cap_adjustment", "Maximum fee cap", "cap_adjustment", adj, vat_rule,
                           formula=f"{subtotal:.2f} capped at {D(max_fee):.2f}"))
        flags.append("max_fee_applied")
    elif min_fee is not None and 0 < subtotal < D(min_fee):
        adj = D(min_fee) - subtotal
        lines.append(_line("min_adjustment", "Minimum fee", "min_adjustment", adj, vat_rule,
                           formula=f"{subtotal:.2f} raised to minimum {D(min_fee):.2f}"))
        flags.append("min_fee_applied")

    bd: dict = {
        "term_months": term, "term_start": term_start, "effective_date": effective, "trigger": inputs.get("trigger"),
        "method": method, "months_elapsed": elapsed, "months_remaining": remaining,
        "month_position": pos, "lines": lines, "router_credit": router_credit_info,
        "vat": {"rate": D(vat_rule.get("rate", "0.15")), "treatment": vat_rule.get("treatment", "exclusive")},
        "outstanding_balance": D(inputs.get("outstanding_balance_zar")) if policy.get("outstanding_balance") == "include" else ZERO,
        "outstanding_balance_policy": policy.get("outstanding_balance", "exclude"),
        "waiver_eligibility": [],
    }
    _recompute_totals(bd)

    # --- grace period (cooling-off) and automatic waivers -----------------------------------------
    due = bd["totals"]["fee_total"]
    grace = int(policy.get("grace_period_days") or 0)
    days_since = (effective - term_start).days
    if due > 0 and grace > 0 and days_since <= grace:
        lines.append(_waiver_line(vat_rule, due, due, "grace_period", f"Grace period ({grace} days from term start)",
                                  reason_code="grace_period", applied_by="engine", percent=HUNDRED))
        flags.append("grace_period_applied")
        _recompute_totals(bd)
    reason = (inputs.get("reason_code") or "").strip().lower() or None
    for rule in policy.get("waivers") or []:
        if reason is None or rule["reason_code"] != reason:
            continue
        due_now = bd["totals"]["fee_total"]
        pct = D(rule.get("waive_percent", "100"))
        indicative = q2(due_now * pct / HUNDRED)
        entry = {"reason_code": rule["reason_code"], "label": rule.get("label"), "percent": pct,
                 "required_tier": rule.get("required_tier", "admin"), "evidence_required": bool(rule.get("evidence_required")),
                 "indicative_gross": indicative, "applied": False}
        if rule.get("required_tier") == "none" and indicative > 0:
            lines.append(_waiver_line(vat_rule, due_now, indicative, f"waiver_{rule['reason_code']}",
                                      rule.get("label") or f"Waiver: {rule['reason_code']}", reason_code=rule["reason_code"],
                                      applied_by="engine", percent=pct))
            entry["applied"] = True
            flags.append(f"waiver_applied_{rule['reason_code']}")
            _recompute_totals(bd)
        bd["waiver_eligibility"].append(entry)

    bd["flags"] = flags
    bd["formula"] = _formula_text(bd)
    return bd


def apply_waiver_to_breakdown(bd: dict, vat_rule: dict, *, code: str, label: str, reason_code: str,
                              percent: Optional[Decimal] = None, amount_gross: Optional[Decimal] = None,
                              applied_by: Optional[str] = None) -> dict:
    """Append a manual waiver line (percent of what is currently due, or a gross amount). Returns the line."""
    due = bd["totals"]["fee_total"]
    if due <= 0:
        raise ValueError("nothing left to waive")
    if (percent is None) == (amount_gross is None):
        raise ValueError("give exactly one of percent or amount")
    waive = q2(due * percent / HUNDRED) if percent is not None else q2(amount_gross)
    if waive <= 0:
        raise ValueError("waiver amount must be positive")
    if waive > due:
        raise ValueError(f"waiver {waive:.2f} exceeds the {due:.2f} still due")
    pct = percent if percent is not None else q2(waive / due * HUNDRED)
    line = _waiver_line(vat_rule, due, waive, code, label, reason_code=reason_code, applied_by=applied_by or "manual", percent=pct)
    bd["lines"].append(line)
    _recompute_totals(bd)
    return line


def _formula_text(bd: dict) -> str:
    parts = []
    for l in bd["lines"]:
        if l["kind"] == "component":
            parts.append(f"{l['label']}: {l['formula']}")
        else:
            parts.append(f"{l['label']}: {l['amount']:.2f}")
    t = bd["totals"]
    parts.append(f"Subtotal {t['fee_net']:.2f} + VAT {t['fee_vat']:.2f} = {t['fee_total']:.2f}")
    return "; ".join(parts)


def inputs_hash(policy: dict, inputs: dict) -> str:
    """Stable digest of everything that determines the calculation (outstanding balance excluded:
    it is informational and moves as the customer pays)."""
    payload = {
        "policy": [policy.get("id"), policy.get("version")],
        "trigger": inputs.get("trigger"),
        "term_start": inputs["term_start"].isoformat(),
        "term_months": int(inputs.get("term_months") or policy["term_months"]),
        "components": {k: str(D(v)) for k, v in sorted((inputs.get("components") or {}).items())},
        "monthly_rental_zar": str(D(inputs.get("monthly_rental_zar"))),
        "plan_keys": sorted(k for k in (inputs.get("plan_keys") or []) if k),
        "effective_date": inputs["effective_date"].isoformat(),
        "reason_code": (inputs.get("reason_code") or "").strip().lower() or None,
        "router_returned": bool(inputs.get("router_returned")),
        "router_condition": (inputs.get("router_condition") or "").strip().lower() or None,
        "snapshot_present": bool(inputs.get("snapshot_present", True)),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def jsonable(obj: Any) -> Any:
    """Decimals -> strings, dates -> ISO, recursively (for JSON columns and API responses)."""
    if isinstance(obj, Decimal):
        return format(obj, "f")
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


def breakdown_from_json(data: dict) -> dict:
    """Inverse of jsonable() for the fields the engine re-reads (used when a waiver is applied to a stored row)."""
    bd = json.loads(json.dumps(data))
    for l in bd["lines"]:
        for k in ("amount", "net", "vat", "gross"):
            l[k] = Decimal(l[k])
    t = bd["totals"]
    for k in list(t):
        t[k] = Decimal(t[k])
    bd["outstanding_balance"] = Decimal(bd.get("outstanding_balance") or "0")
    return bd


def approval_tier_needed(policy: dict, reason_code: str, waive_gross: Decimal) -> str:
    """Highest of: the reason's rule tier (unlisted/custom reasons need admin) and the amount-based tier
    (above auto_approve_waiver_limit_zar needs admin; at or below it a clerk may approve)."""
    rule = next((w for w in policy.get("waivers") or [] if w["reason_code"] == reason_code), None)
    rule_tier = (rule or {}).get("required_tier", "admin")
    amount_tier = "admin" if waive_gross > D(policy.get("auto_approve_waiver_limit_zar", "0")) else "clerk"
    if rule is None:
        rule_tier = "admin"
    # a 'none' rule is auto-applied by the engine; a manual call on it still needs a clerk at least
    return max((rule_tier, amount_tier, "clerk"), key=lambda t: TIER_ORDER[t])


# ===========================================================================
# Part 2: DB orchestration
# ===========================================================================

def audit(session: Any, tenant_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID, action: str,
          actor_id: Optional[uuid.UUID], details: Optional[dict] = None) -> None:
    from services.billing.models_fees import FeeAuditEvent
    session.add(FeeAuditEvent(tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id, action=action,
                              actor_id=actor_id, details=jsonable(details or {})))


def select_policy(session: Any, tenant_id: uuid.UUID, trigger: str, on: date,
                  plan_keys: list[str], policy_id: Optional[uuid.UUID] = None):
    """Policy for this trigger/date/plan: plan-specific beats generic, default beats non-default,
    then latest effective_from / version. None when the tenant has no applicable policy."""
    from services.billing.models_fees import FeePolicy
    q = session.query(FeePolicy).filter(FeePolicy.tenant_id == tenant_id)
    if policy_id:
        return q.filter(FeePolicy.id == policy_id).first()
    rows = q.filter(FeePolicy.is_active.is_(True), FeePolicy.effective_from <= on).all()
    keys = {k for k in plan_keys if k}
    best, best_rank = None, None
    for r in rows:
        if r.effective_to is not None and r.effective_to < on:
            continue
        if trigger not in (r.trigger_types or []):
            continue
        plans = set(r.applies_to_plans or [])
        if plans and not (plans & keys):
            continue
        rank = (1 if plans else 0, 1 if r.is_default else 0, r.effective_from, r.version)
        if best_rank is None or rank > best_rank:
            best, best_rank = r, rank
    return best


def current_snapshot(session: Any, tenant_id: uuid.UUID, subscription_id: uuid.UUID):
    from services.billing.models_fees import ContractFeeSnapshot
    return (session.query(ContractFeeSnapshot)
            .filter(ContractFeeSnapshot.tenant_id == tenant_id, ContractFeeSnapshot.subscription_id == subscription_id,
                    ContractFeeSnapshot.is_current.is_(True))
            .order_by(ContractFeeSnapshot.version.desc()).first())


def plan_keys_for(sub: Any) -> list[str]:
    return [str(sub.plan_id) if getattr(sub, "plan_id", None) else "", (sub.plan or "")]


def outstanding_balance(session: Any, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Decimal:
    from sqlalchemy import func
    from services.billing.models import Invoice
    val = session.query(func.coalesce(func.sum(Invoice.total_zar - Invoice.amount_paid_zar), 0)).filter(
        Invoice.tenant_id == tenant_id, Invoice.customer_id == customer_id,
        Invoice.status.in_(["sent", "overdue", "partially_paid"]), Invoice.credit_note_of.is_(None)).scalar()
    return q2(D(val))


def build_inputs(session: Any, tenant_id: uuid.UUID, sub: Any, snap: Any, policy: dict, *, trigger: str,
                 effective_date: date, reason_code: Optional[str], router_returned: bool,
                 router_condition: Optional[str]) -> dict:
    if snap is not None:
        comps = {c["code"]: D(c["amount"]) for c in snap.components or []}
        term_start, term_months, rental = snap.term_start, snap.term_months, snap.monthly_rental_zar
    else:
        comps = {}
        start = sub.billing_anchor or (sub.created_at.date() if sub.created_at else effective_date)
        term_start, term_months, rental = start, policy["term_months"], sub.base_price_zar
    return {
        "trigger": trigger, "term_start": term_start, "term_months": term_months, "components": comps,
        "monthly_rental_zar": rental, "plan_keys": plan_keys_for(sub), "effective_date": effective_date,
        "reason_code": reason_code, "router_returned": router_returned, "router_condition": router_condition,
        "outstanding_balance_zar": outstanding_balance(session, tenant_id, sub.customer_id),
        "snapshot_present": snap is not None,
    }


def _inputs_for_storage(inputs: dict) -> dict:
    return jsonable(inputs)


def calc_to_dict(c: Any) -> dict:
    return {
        "id": str(c.id), "tenant_id": str(c.tenant_id), "customer_id": str(c.customer_id),
        "subscription_id": str(c.subscription_id) if c.subscription_id else None,
        "snapshot_id": str(c.snapshot_id) if c.snapshot_id else None,
        "policy_id": str(c.policy_id), "policy_version": c.policy_version, "trigger": c.trigger,
        "subject_type": c.subject_type, "subject_id": str(c.subject_id),
        "cancellation_request_id": str(c.cancellation_request_id) if c.cancellation_request_id else None,
        "effective_date": c.effective_date.isoformat(), "reason_code": c.reason_code,
        "inputs_hash": c.inputs_hash, "inputs": c.inputs, "breakdown": c.breakdown, "flags": c.flags,
        "fee_net_zar": format(c.fee_net_zar, "f"), "fee_vat_zar": format(c.fee_vat_zar, "f"),
        "fee_total_zar": format(c.fee_total_zar, "f"), "outstanding_balance_zar": format(c.outstanding_balance_zar, "f"),
        "waived_total_zar": format(c.waived_total_zar, "f"), "amount_due_zar": format(c.amount_due_zar, "f"),
        "waivers": c.waivers, "status": c.status, "superseded_by": str(c.superseded_by) if c.superseded_by else None,
        "invoice_id": str(c.invoice_id) if c.invoice_id else None, "invoice_number": c.invoice_number,
        "legacy": c.legacy, "auto_calculated": c.auto_calculated,
        "created_by": str(c.created_by) if c.created_by else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _apply_result_to_row(row: Any, bd: dict) -> None:
    t = bd["totals"]
    row.fee_net_zar, row.fee_vat_zar, row.fee_total_zar = t["fee_net"], t["fee_vat"], t["fee_total"]  # after waivers
    row.waived_total_zar = t["waived_total"]
    row.amount_due_zar = t["fee_total"]
    row.outstanding_balance_zar = t["outstanding_balance"]


def persist_calculation(session: Any, *, tenant_id: uuid.UUID, sub: Any, snap: Any, policy_row: Any, trigger: str,
                        subject_type: str, subject_id: uuid.UUID, cancellation_request_id: Optional[uuid.UUID],
                        effective_date: date, reason_code: Optional[str], inputs: dict, bd: dict, digest: str,
                        actor_id: Optional[uuid.UUID], auto: bool = False) -> tuple[Any, bool]:
    """Idempotent on (tenant, trigger, subject, effective_date, inputs_hash). Returns (row, created).
    Creating a new row supersedes older un-invoiced rows for the same subject; re-hitting an earlier
    hash makes that row current again."""
    from services.billing.models_fees import FeeCalculation
    existing = session.query(FeeCalculation).filter(
        FeeCalculation.tenant_id == tenant_id, FeeCalculation.trigger == trigger,
        FeeCalculation.subject_type == subject_type, FeeCalculation.subject_id == subject_id,
        FeeCalculation.effective_date == effective_date, FeeCalculation.inputs_hash == digest).first()
    others = session.query(FeeCalculation).filter(
        FeeCalculation.tenant_id == tenant_id, FeeCalculation.subject_type == subject_type,
        FeeCalculation.subject_id == subject_id, FeeCalculation.trigger == trigger,
        FeeCalculation.status != "superseded")
    if existing is not None:
        if existing.status == "superseded":
            for o in others.all():
                if o.id != existing.id and o.status != "invoiced":
                    o.status, o.superseded_by = "superseded", existing.id
            existing.status = "waived" if existing.amount_due_zar <= 0 and existing.waived_total_zar > 0 else "calculated"
            existing.superseded_by = None
        return existing, False
    row = FeeCalculation(
        tenant_id=tenant_id, customer_id=sub.customer_id, subscription_id=sub.id,
        snapshot_id=snap.id if snap else None, policy_id=policy_row.id, policy_key=policy_row.policy_key,
        policy_version=policy_row.version, trigger=trigger, subject_type=subject_type, subject_id=subject_id,
        cancellation_request_id=cancellation_request_id, effective_date=effective_date, reason_code=reason_code,
        inputs=_inputs_for_storage(inputs), inputs_hash=digest, breakdown=jsonable(bd), flags=list(bd["flags"]),
        waivers=[], status="calculated", created_by=actor_id, auto_calculated=auto)
    _apply_result_to_row(row, bd)
    if row.amount_due_zar <= 0 and row.waived_total_zar > 0:
        row.status = "waived"
    session.add(row)
    session.flush()
    for o in others.all():
        if o.id != row.id and o.status != "invoiced":
            o.status, o.superseded_by = "superseded", row.id
    audit(session, tenant_id, "calculation", row.id, "calculated", actor_id,
          {"trigger": trigger, "policy_id": policy_row.id, "policy_version": policy_row.version,
           "inputs_hash": digest, "fee_total_zar": row.fee_total_zar, "flags": bd["flags"]})
    return row, True


def run_calculation(session: Any, *, tenant_id: uuid.UUID, sub: Any, trigger: str, effective_date: date,
                    reason_code: Optional[str], router_returned: bool, router_condition: Optional[str],
                    policy_id: Optional[uuid.UUID] = None) -> tuple[Any, dict, dict, str, Any, dict]:
    """Select policy + snapshot, build inputs and compute. Raises LookupError('no_policy') when none applies.
    Returns (policy_row, policy_dict, breakdown, inputs_hash, snapshot_or_None, inputs)."""
    plan_keys = plan_keys_for(sub)
    prow = select_policy(session, tenant_id, trigger, effective_date, plan_keys, policy_id)
    if prow is None:
        raise LookupError("no_policy")
    pol = policy_to_engine(prow)
    snap = current_snapshot(session, tenant_id, sub.id)
    inputs = build_inputs(session, tenant_id, sub, snap, pol, trigger=trigger, effective_date=effective_date,
                          reason_code=reason_code, router_returned=router_returned, router_condition=router_condition)
    bd = calculate_fee(pol, inputs)
    bd["policy"] = {"id": pol["id"], "policy_key": pol["policy_key"], "version": pol["version"], "name": pol["name"]}
    bd["inputs_hash"] = inputs_hash(pol, inputs)
    return prow, pol, bd, bd["inputs_hash"], snap, inputs


def can_self_approve(policy: dict) -> bool:
    return bool(policy.get("allow_self_approval"))


def waive_calculation(session: Any, calc: Any, policy: dict, *, reason_code: str, reason: str,
                      percent: Optional[Decimal], amount: Optional[Decimal], actor_id: uuid.UUID,
                      actor_tier: str) -> dict:
    """Apply a manual waiver. Raises PermissionError(msg) / ValueError(msg); caller maps to 403/400/409."""
    if calc.status == "invoiced":
        raise ValueError("calculation is already invoiced; issue a credit note instead")
    if calc.status == "superseded":
        raise ValueError("calculation was superseded by a newer one")
    bd = breakdown_from_json(calc.breakdown)
    vat_rule = {"rate": bd["vat"]["rate"], "treatment": bd["vat"]["treatment"]}
    due = bd["totals"]["fee_total"]
    if (percent is None) == (amount is None):
        raise ValueError("give exactly one of percent or amount_zar")
    waive_gross = q2(due * percent / HUNDRED) if percent is not None else q2(amount)
    if waive_gross <= 0 or waive_gross > due:
        raise ValueError(f"waiver must be between 0.01 and the {due:.2f} still due")
    needed = approval_tier_needed(policy, reason_code, waive_gross)
    if TIER_ORDER[actor_tier] < TIER_ORDER[needed]:
        raise PermissionError(f"this waiver ({waive_gross:.2f}, reason '{reason_code}') needs a billing {needed} approver")
    if (waive_gross > D(policy.get("auto_approve_waiver_limit_zar", "0")) and calc.created_by == actor_id
            and not can_self_approve(policy)):
        raise PermissionError("self-approval is not allowed: another approver must waive a fee you calculated")
    rule = next((w for w in policy.get("waivers") or [] if w["reason_code"] == reason_code), None)
    line = apply_waiver_to_breakdown(
        bd, vat_rule, code=f"waiver_{reason_code}", label=(rule or {}).get("label") or f"Waiver: {reason_code}",
        reason_code=reason_code, percent=percent, amount_gross=None if percent is not None else waive_gross,
        applied_by=str(actor_id))
    calc.breakdown = jsonable(bd)
    _apply_result_to_row(calc, bd)
    entry = {"id": str(uuid.uuid4()), "reason_code": reason_code, "reason": reason, "amount_gross": format(waive_gross, "f"),
             "percent": format(line["percent"], "f"), "approved_by": str(actor_id), "approver_tier": actor_tier,
             "required_tier": needed, "at": datetime.now(timezone.utc).isoformat()}
    calc.waivers = [*(calc.waivers or []), entry]
    if calc.amount_due_zar <= 0:
        calc.status = "waived"
    audit(session, calc.tenant_id, "calculation", calc.id, "waived", actor_id, entry)
    return entry


def invoice_calculation(session: Any, calc: Any, policy: dict, *, issue: bool, actor_id: Optional[uuid.UUID]):
    """Create the termination-fee invoice for a calculation. Idempotent: returns (invoice, created).
    Raises ValueError for nothing-to-invoice / superseded; LookupError carrying an existing sibling."""
    from services.billing import invoicing
    from services.billing.database import next_invoice_number
    from services.billing.models import Invoice, InvoiceLine
    from services.billing.models_fees import FeeCalculation

    if calc.invoice_id:
        return session.get(Invoice, calc.invoice_id), False
    if calc.status == "superseded":
        raise ValueError("calculation was superseded by a newer one; invoice the current calculation")
    sibling = session.query(FeeCalculation).filter(
        FeeCalculation.tenant_id == calc.tenant_id, FeeCalculation.subject_type == calc.subject_type,
        FeeCalculation.subject_id == calc.subject_id, FeeCalculation.trigger == calc.trigger,
        FeeCalculation.invoice_id.isnot(None), FeeCalculation.id != calc.id).first()
    if sibling is not None:
        raise LookupError(f"fee already invoiced for this subject via calculation {sibling.id}")
    bd = breakdown_from_json(calc.breakdown)
    totals = bd["totals"]
    if totals["fee_total"] <= 0:
        raise ValueError("nothing to invoice: the amount due is zero")
    inv = Invoice(
        tenant_id=calc.tenant_id, customer_id=calc.customer_id, subscription_id=calc.subscription_id,
        number=next_invoice_number(session, calc.tenant_id), status="sent" if issue else "draft",
        subtotal_zar=totals["fee_net"], vat_zar=totals["fee_vat"], total_zar=totals["fee_total"],
        due_date=date.today() + timedelta(days=int(policy.get("invoice_due_days", 14))),
        notes=f"Early termination / claw-back fee ({calc.trigger}); calculation {calc.id}; policy v{calc.policy_version}",
        line_items=[{"type": "termination_fee", "calculation_id": str(calc.id),
                     "cancellation_request_id": str(calc.cancellation_request_id) if calc.cancellation_request_id else None,
                     "description": l["label"], "total_zar": format(l["gross"], "f")} for l in bd["lines"]])
    session.add(inv)
    session.flush()
    for l in bd["lines"]:
        if l["net"] == 0 and l["vat"] == 0:
            continue
        session.add(InvoiceLine(
            invoice_id=inv.id, tenant_id=calc.tenant_id, description=l["label"][:500], quantity=1,
            unit_price_zar=l["net"], discount_zar=ZERO, vat_zar=l["vat"], total_zar=l["gross"],
            line_type="termination_fee"))
    calc.invoice_id, calc.invoice_number = inv.id, inv.number
    calc.status = "invoiced"
    if calc.termination_fee_id:
        from services.billing.models import TerminationFee
        tf = session.get(TerminationFee, calc.termination_fee_id)
        if tf is not None:
            tf.invoice_id = inv.id
    session.flush()
    if issue:
        invoicing.enqueue_issue(session, inv)
        invoicing.schedule_dunning(session, inv)
    audit(session, calc.tenant_id, "calculation", calc.id, "invoiced", actor_id,
          {"invoice_id": inv.id, "invoice_number": inv.number, "status": inv.status, "total_zar": inv.total_zar})
    return inv, True


# --- contract snapshots -------------------------------------------------------------------------------

def snapshot_digest(term_start: date, term_months: int, components: list[dict], rental: Decimal) -> str:
    payload = {"term_start": term_start.isoformat(), "term_months": term_months,
               "components": sorted(({"code": c["code"], "amount": str(D(c["amount"]))} for c in components), key=lambda c: c["code"]),
               "rental": str(D(rental))}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def create_snapshot(session: Any, *, tenant_id: uuid.UUID, sub: Any, term_start: date, term_months: int,
                    components: list[dict], monthly_rental: Decimal, policy_row: Any = None, source: str,
                    actor_id: Optional[uuid.UUID], notes: Optional[str] = None, supersede: bool = False):
    """Insert a new immutable snapshot version. Raises FileExistsError when one is current and not superseding."""
    from services.billing.models_fees import ContractFeeSnapshot
    cur = current_snapshot(session, tenant_id, sub.id)
    if cur is not None and not supersede:
        raise FileExistsError(str(cur.id))
    comps = [{"code": c["code"], "label": c.get("label"), "amount": format(q2(D(c["amount"])), "f"),
              "discount": format(q2(D(c.get("discount"))), "f")} for c in components]
    snap = ContractFeeSnapshot(
        tenant_id=tenant_id, subscription_id=sub.id, customer_id=sub.customer_id,
        version=(cur.version + 1) if cur else 1, is_current=True,
        policy_id=policy_row.id if policy_row else None, policy_version=policy_row.version if policy_row else None,
        term_start=term_start, term_months=term_months, components=comps, monthly_rental_zar=q2(D(monthly_rental)),
        discounts_zar=sum((D(c["discount"]) for c in comps), ZERO), plan_id=getattr(sub, "plan_id", None),
        plan_name=sub.plan, source=source, notes=notes,
        snapshot_hash=snapshot_digest(term_start, term_months, comps, monthly_rental), created_by=actor_id)
    if cur is not None:
        cur.is_current = False
    session.add(snap)
    session.flush()
    audit(session, tenant_id, "snapshot", snap.id, "created", actor_id,
          {"subscription_id": sub.id, "version": snap.version, "source": source, "hash": snap.snapshot_hash})
    return snap


def snapshot_to_dict(s: Any) -> dict:
    return {"id": str(s.id), "subscription_id": str(s.subscription_id), "customer_id": str(s.customer_id),
            "version": s.version, "is_current": s.is_current,
            "policy_id": str(s.policy_id) if s.policy_id else None, "policy_version": s.policy_version,
            "term_start": s.term_start.isoformat(), "term_months": s.term_months, "components": s.components,
            "monthly_rental_zar": format(s.monthly_rental_zar, "f"), "discounts_zar": format(s.discounts_zar, "f"),
            "plan_id": str(s.plan_id) if s.plan_id else None, "plan_name": s.plan_name, "source": s.source,
            "notes": s.notes, "snapshot_hash": s.snapshot_hash,
            "created_by": str(s.created_by) if s.created_by else None,
            "created_at": s.created_at.isoformat() if s.created_at else None}


def components_from_policy(policy: dict, plan_keys: list[str]) -> list[dict]:
    """Component amounts a policy can resolve without a snapshot (fixed / catalog sources)."""
    out = []
    for comp in policy.get("components") or []:
        if comp.get("amount_source") == "snapshot" and comp.get("fixed_amount") is None:
            continue
        amt, source, _flag = resolve_component_amount(
            {**comp, "amount_source": "fixed" if comp.get("amount_source") == "snapshot" else comp.get("amount_source")},
            {}, policy.get("catalog_amounts") or {}, plan_keys)
        if source != "unresolved":
            out.append({"code": comp["code"], "label": comp.get("label"), "amount": amt})
    return out


def auto_snapshot_for_subscription(session: Any, sub: Any, actor_id: Optional[uuid.UUID]) -> Optional[Any]:
    """Subscription-creation hook. Never raises: a missing policy or any failure just means no snapshot
    (the engine then flags snapshot_missing). Runs in a SAVEPOINT so it cannot poison the caller's transaction."""
    try:
        start = sub.billing_anchor or date.today()
        with session.begin_nested():
            prow = select_policy(session, sub.tenant_id, "cancellation", start, plan_keys_for(sub))
            if prow is None:
                return None
            pol = policy_to_engine(prow)
            comps = components_from_policy(pol, plan_keys_for(sub))
            if not comps:
                return None
            return create_snapshot(session, tenant_id=sub.tenant_id, sub=sub, term_start=start,
                                   term_months=prow.term_months, components=comps, monthly_rental=sub.base_price_zar,
                                   policy_row=prow, source="auto_create", actor_id=actor_id)
    except Exception:  # noqa: BLE001
        logger.warning("fee snapshot hook failed for subscription %s", getattr(sub, "id", None), exc_info=True)
        return None


# --- cancellation integration ----------------------------------------------------------------------

def reason_code_for(cancel_req: Any) -> Optional[str]:
    raw = (cancel_req.cancel_reason or "").strip().lower().replace(" ", "_")
    if raw and _SLUG.match(raw):
        return raw
    ct = (cancel_req.cancel_type or "").strip().lower()
    return ct or None


def sync_termination_fee_row(session: Any, cancel_req: Any, sub: Any, calc: Any, router_returned: bool = False) -> Any:
    """Keep the legacy TerminationFee row consistent with the engine result (one row per cancellation)."""
    from services.billing.models import TerminationFee
    bd = calc.breakdown
    lines = bd.get("lines", [])
    router_code = (bd.get("router_credit") or {}).get("router_component_code") or "router"
    router_net = sum((D(l["net"]) for l in lines if l["code"] in (router_code, "router_credit")), ZERO)
    net_due = q2(sum((D(l["net"]) for l in lines), ZERO))
    pre_waiver = D(calc.amount_due_zar) + D(calc.waived_total_zar)
    ratio = (D(calc.amount_due_zar) / pre_waiver) if pre_waiver > 0 else Decimal(0)
    router_charge = q2(router_net * ratio) if router_net > 0 else ZERO
    tf = session.query(TerminationFee).filter(TerminationFee.cancellation_request_id == cancel_req.id).first()
    if tf is None:
        tf = TerminationFee(tenant_id=cancel_req.tenant_id, customer_id=cancel_req.customer_id,
                            cancellation_request_id=cancel_req.id, subscription_id=cancel_req.subscription_id)
        session.add(tf)
    remaining = D(bd.get("months_remaining", "0"))
    term = int(bd.get("term_months") or 1)
    tf.monthly_rate_zar = sub.base_price_zar
    tf.remaining_months = int(remaining.to_integral_value(rounding="ROUND_CEILING"))
    tf.penalty_percentage = q2(min(remaining / Decimal(term) * HUNDRED, Decimal("999.99")))
    tf.router_charge_zar = router_charge
    tf.contract_etf_zar = max(net_due - router_charge, ZERO)
    tf.outstanding_balance_zar = D(calc.outstanding_balance_zar)
    tf.total_etf_zar = net_due + D(calc.outstanding_balance_zar)
    tf.router_returned = router_returned or bool((bd.get("router_credit") or {}).get("returned"))
    if calc.invoice_id:
        tf.invoice_id = calc.invoice_id
    session.flush()
    calc.termination_fee_id = tf.id
    return tf


def calculate_for_cancellation(session: Any, cancel_req: Any, sub: Any, *, actor_id: Optional[uuid.UUID],
                               router_returned: bool = False, router_condition: Optional[str] = None,
                               reason_code: Optional[str] = None, auto: bool = False):
    """Run (or re-run) the engine for a cancellation. Returns (calc, tf) or None when no policy applies."""
    effective = cancel_req.effective_date or date.today()
    reason = reason_code or reason_code_for(cancel_req)
    try:
        prow, pol, bd, digest, snap, inputs = run_calculation(
            session, tenant_id=cancel_req.tenant_id, sub=sub, trigger="cancellation", effective_date=effective,
            reason_code=reason, router_returned=router_returned, router_condition=router_condition)
    except LookupError:
        return None
    calc, _created = persist_calculation(
        session, tenant_id=cancel_req.tenant_id, sub=sub, snap=snap, policy_row=prow, trigger="cancellation",
        subject_type="cancellation", subject_id=cancel_req.id, cancellation_request_id=cancel_req.id,
        effective_date=effective, reason_code=reason, inputs=inputs, bd=bd, digest=digest, actor_id=actor_id, auto=auto)
    tf = sync_termination_fee_row(session, cancel_req, sub, calc)
    return calc, tf, pol


def current_cancellation_calc(session: Any, tenant_id: uuid.UUID, cancel_id: uuid.UUID):
    from services.billing.models_fees import FeeCalculation
    return (session.query(FeeCalculation)
            .filter(FeeCalculation.tenant_id == tenant_id, FeeCalculation.subject_type == "cancellation",
                    FeeCalculation.subject_id == cancel_id, FeeCalculation.status != "superseded")
            .order_by(FeeCalculation.created_at.desc()).first())
