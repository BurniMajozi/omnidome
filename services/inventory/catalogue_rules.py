"""Pure catalogue rules: economics, launch readiness and dependency checks.

No database access here, so the same rules run in the API (launch cannot be bypassed from a client) and in
unit tests. A "product view" is a plain dict: the catalogue columns plus a ``definition`` dict.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional

NUMBER_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,23}$")
DEFAULT_NOTICE_DAYS = 7
NATURES = ("Digital service", "Physical item", "Professional service")
USAGES = ("Customer-facing", "Internal consumable", "Company-owned asset")

STANDARD_TESTS = {
    "Digital service": ["Provisioning & activation", "Speed / throughput", "Billing & invoice line",
                        "Customer portal order journey", "Cancellation & termination"],
    "Physical item": ["Fulfilment & stock reservation", "Serial & warranty record", "Billing & invoice line"],
    "Professional service": ["Scheduling & job completion", "Billing & invoice line"],
}


def _d(v: Any) -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else 0))
    except Exception:
        return Decimal(0)


def normalise_number(raw: str) -> str:
    return (raw or "").strip().upper()


def number_is_valid(raw: str) -> bool:
    return bool(NUMBER_RE.match(normalise_number(raw)))


def ean13_check_digit(first12: str) -> int:
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(first12))
    return (10 - total % 10) % 10


def ean13_valid(code: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", code or "")) and ean13_check_digit(code[:12]) == int(code[12])


def norm_name(s: str) -> str:
    """Test names compare without case, spaces or punctuation, so 'Fulfilment & stock reservation,' still matches."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def add_business_days(start: date, n: int) -> date:
    """Weekends excluded; public holidays are not modelled (a tenant calendar is future work)."""
    d, k = start, 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d


def _parse_date(v: Any) -> Optional[date]:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


# ── economics ────────────────────────────────────────────────────────────────

def preferred_supplier_id(d: dict) -> Optional[str]:
    pref = next((s for s in (d.get("sources") or []) if s.get("preferred")), None)
    return str(pref["supplier_id"]) if pref else None


def effective_costs(d: dict, supplier_id: Optional[str] = None, names: Optional[dict] = None) -> list[dict]:
    """The cost lines that apply when the product is bought from ``supplier_id`` (default: the preferred supplier).

    Shared lines (no supplier) always apply; a line assigned to a supplier applies only to that supplier's scenario;
    the purchase cost is the chosen source's own price. The stored automatic line is ignored here and rebuilt, so
    every supplier scenario is computed the same way."""
    sources = d.get("sources") or []
    sid = supplier_id or preferred_supplier_id(d)
    lines = []
    for c in d.get("costs") or []:
        if c.get("auto"):
            continue
        assigned = c.get("supplier_id")
        if assigned and sid and str(assigned) != sid:
            continue
        lines.append(c)
    src = next((s for s in sources if str(s["supplier_id"]) == sid), None) if sid else None
    if src is not None:
        lines.insert(0, {"name": "Purchase cost", "supplier": (names or {}).get(sid) or sid, "supplier_id": sid,
                         "amount": src.get("unit_cost") or 0, "cadence": src.get("cadence") or "Once-off", "auto": True})
    return lines


def offer_of(d: dict) -> dict:
    o = d.get("offer") or {}
    return {"mode": o.get("mode") or "sold", "returnable": bool(o.get("returnable")), "life_months": int(o.get("life_months") or 0),
            "residual_value": _d(o.get("residual_value")), "rental_monthly": _d(o.get("rental_monthly"))}


def is_sold(d: dict) -> bool:
    return offer_of(d)["mode"] == "sold"


def economics(pid: str, catalogue: dict[str, dict], _seen: Optional[frozenset] = None, supplier_id: Optional[str] = None,
              names: Optional[dict] = None) -> dict:
    """Direct-cost economics of one product, recursing through included components.

    ``catalogue`` maps product id -> product view. A missing or cyclic component makes the cost sheet incomplete;
    a missing cost is never treated as zero. ``supplier_id`` prices the product as bought from that supplier."""
    seen = (_seen or frozenset()) | {pid}
    p = catalogue.get(pid)
    if p is None:
        return {"complete": False, "monthly": Decimal(0), "upfront": Decimal(0)}
    d = p.get("definition") or {}
    costs = effective_costs(d, supplier_id, names)
    complete = bool(costs) and all(c.get("name") and c.get("supplier") for c in costs)
    monthly = upfront = Decimal(0)
    for c in costs:
        if c.get("cadence") == "Monthly":
            monthly += _d(c.get("amount"))
        else:
            upfront += _d(c.get("amount"))
    for comp in d.get("components") or []:
        cid = str(comp.get("product_id"))
        if cid in seen:
            complete = False
            continue
        e = economics(cid, catalogue, seen)
        qty = int(comp.get("qty") or 1)
        complete = complete and e["complete"]
        monthly += e["monthly"] * qty
        upfront += e["upfront"] * qty
    off = offer_of(d)
    amortisation = Decimal(0)
    if off["mode"] != "sold":
        # Not sold: nothing is billed for the item itself. What it costs the business is spread over its life, or, for a
        # returnable giveaway with no life, reduced by what we expect to get back.
        own_up = sum((_d(c.get("amount")) for c in costs if c.get("cadence") != "Monthly"), Decimal(0))
        own_up_children = upfront - own_up
        if off["mode"] == "rented_in":
            monthly += off["rental_monthly"]
        elif off["life_months"] > 0:
            amortisation = max(Decimal(0), own_up - off["residual_value"]) / off["life_months"]
            upfront = own_up_children
            monthly += amortisation
        elif off["returnable"]:
            upfront = max(Decimal(0), upfront - off["residual_value"])
    fee_once = fee_monthly = Decimal(0)
    for f in d.get("fees") or []:
        if f.get("enabled") and f.get("mode") == "Charge":
            if f.get("cadence") == "Once-off":
                fee_once += _d(f.get("amount"))
            elif f.get("cadence") == "Monthly":
                fee_monthly += _d(f.get("amount"))
    recurring = bool(d.get("recurring", True))
    price = _d(d.get("price")) if off["mode"] == "sold" else Decimal(0)
    if off["mode"] != "sold":
        fee_once = fee_monthly = Decimal(0)
    horizon = max(1, int(d.get("term") or 24)) if recurring else 1
    revenue = (price + fee_monthly) * horizon + fee_once if recurring else price + fee_once
    cost = monthly * horizon + upfront
    out = {"complete": complete, "monthly": monthly, "upfront": upfront, "horizon": horizon,
           "revenue": revenue, "cost": cost, "profit": revenue - cost,
           "margin_pct": (None if revenue == 0 else round((revenue - cost) / revenue * 100, 2))}
    if off["mode"] != "sold":
        out["amortisation_monthly"] = amortisation
        out["amortisation_yearly"] = amortisation * 12
    return out


CHANNELS = ("Online storefront", "Field sales", "Call centre", "Partner / reseller", "Retail store")


def channel_commission(cfg: dict, d: dict, e: dict) -> Decimal:
    """What one sale through a channel costs in commission.

    percent: of the contract value (default), of the first month, or of the once-off charges; fixed: a flat amount per sale."""
    value = _d(cfg.get("value"))
    kind = cfg.get("commission_type") or "none"
    if kind == "fixed":
        return value
    if kind != "percent":
        return Decimal(0)
    recurring = bool(d.get("recurring", True))
    price = _d(d.get("price"))
    fees = [f for f in d.get("fees") or [] if f.get("enabled") and f.get("mode") == "Charge"]
    fee_once = sum((_d(f.get("amount")) for f in fees if f.get("cadence") == "Once-off"), Decimal(0))
    fee_monthly = sum((_d(f.get("amount")) for f in fees if f.get("cadence") == "Monthly"), Decimal(0))
    contract = e.get("revenue", Decimal(0))
    first_month = price + fee_monthly + fee_once if recurring else contract
    once_off = fee_once if recurring else contract
    basis = {"contract": contract, "first_month": first_month, "once_off": once_off}.get(cfg.get("basis") or "contract", contract)
    return (basis * value / Decimal(100)).quantize(Decimal("0.01"))


def margin_matrix(pid: str, catalogue: dict[str, dict], names: Optional[dict] = None) -> dict:
    """Profit and margin for every supplier the product can be bought from, and through every sales channel.

    Rows are suppliers (one row with supplier_id null when no suppliers are listed); ``channels`` holds the margin after
    that channel's commission. Direct costs only, same basis as ``economics``."""
    p = catalogue.get(pid) or {}
    d = p.get("definition") or {}
    channels = [c for c in d.get("channels") or [] if c.get("enabled", True)]
    sources = d.get("sources") or []
    rows = []
    for s in (sources or [None]):
        sid = str(s["supplier_id"]) if s else None
        e = economics(pid, catalogue, supplier_id=sid, names=names)
        revenue, profit = e.get("revenue", Decimal(0)), e.get("profit", Decimal(0))
        row = {"supplier_id": sid, "name": (names or {}).get(sid) if sid else None, "preferred": bool(s and s.get("preferred")),
               "unit_cost": float(_d(s.get("unit_cost"))) if s else None, "cadence": (s or {}).get("cadence"),
               "complete": e["complete"], "revenue": float(revenue), "cost": float(e.get("cost", 0)), "profit": float(profit),
               "margin_pct": None if not revenue else round(float(profit / revenue * 100), 2), "channels": {}}
        for ch in channels:
            comm = channel_commission(ch, d, e)
            after = profit - comm
            row["channels"][ch["channel"]] = {"commission": float(comm), "profit": float(after),
                                              "margin_pct": None if not revenue else round(float(after / revenue * 100), 2)}
        rows.append(row)
    return {"channels": [{"channel": c["channel"], "commission_type": c.get("commission_type", "none"), "value": float(_d(c.get("value"))),
                          "basis": c.get("basis", "contract"), "tier_name": c.get("tier_name", "")} for c in channels],
            "suppliers": rows}


def would_cycle(parent_id: str, child_id: str, catalogue: dict[str, dict]) -> bool:
    """True if making ``child_id`` a component of ``parent_id`` creates a loop (or self-inclusion)."""
    def reaches(frm: str, target: str, seen: set) -> bool:
        if frm == target:
            return True
        if frm in seen:
            return False
        seen.add(frm)
        p = catalogue.get(frm)
        return bool(p) and any(reaches(str(c.get("product_id")), target, seen)
                               for c in (p.get("definition") or {}).get("components") or [])
    return reaches(child_id, parent_id, set())


# ── launch readiness ─────────────────────────────────────────────────────────

def standard_tests(nature: str) -> list[str]:
    return STANDARD_TESTS.get(nature, STANDARD_TESTS["Professional service"])


def default_icasa_required(nature: str, usage: str) -> bool:
    return nature == "Digital service" and usage == "Customer-facing"


def icasa_item_issues(item: dict, notice_days: int) -> list[str]:
    issues = []
    if not (item.get("objectives") or "").strip():
        issues.append("objectives")
    if not (item.get("reasons") or "").strip():
        issues.append("reasons")
    effective = _parse_date(item.get("effective"))
    if not effective:
        issues.append("effective date")
    if item.get("kind") == "Promotion":
        start, end = _parse_date(item.get("promo_start")), _parse_date(item.get("promo_end"))
        if not start or not end or end < start:
            issues.append("promotion period")
    lodged = _parse_date(item.get("lodged"))
    if not lodged:
        issues.append("lodgment date")
    if not (item.get("ref") or "").strip():
        issues.append("ICASA reference / proof")
    if lodged and effective:
        earliest = add_business_days(lodged, notice_days)
        if effective < earliest:
            issues.append(f"notice period (earliest {earliest.isoformat()})")
    return issues


def launch_checks(p: dict, catalogue: dict[str, dict]) -> list[dict]:
    """Every gate on the Launch action. Returns [{key, label, ok, detail}]; launch requires all ok."""
    d = p.get("definition") or {}
    r = d.get("readiness") or {}
    out: list[dict] = []

    def add(key: str, label: str, ok: bool, detail: str = "") -> None:
        out.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    add("definition", "Product definition and description", bool((p.get("name") or "").strip() and (d.get("description") or "").strip()))
    add("classification", "Category, range and service family chosen", bool(p.get("category") and p.get("range") and p.get("family")))
    pid = str(p.get("id"))
    e = economics(pid, {**catalogue, pid: p})
    add("costs", "Cost sheet complete", e["complete"])
    price = _d(d.get("price"))
    customer_facing = p.get("usage") == "Customer-facing"
    sold = is_sold(d)
    if sold:
        add("price", "Selling price set", price > 0 or (not d.get("recurring", True) and not customer_facing))
    else:
        off = offer_of(d)
        if off["mode"] == "rented_in":
            add("price", "Monthly rent set", off["rental_monthly"] > 0, "" if off["rental_monthly"] > 0 else "Enter the monthly rent paid to the owner")
        elif off["residual_value"] > 0 and off["life_months"] == 0 and not off["returnable"]:
            add("price", "Value recovery explained", False, "A residual value needs an amortisation life, or mark the item as returnable")
        else:
            add("price", "Not sold: no selling price needed", True)

    bad_comp = []
    for comp in d.get("components") or []:
        c = catalogue.get(str(comp.get("product_id")))
        if c is None or c.get("status") != "active":
            bad_comp.append(str(comp.get("product_id")))
        elif would_cycle(pid, str(comp.get("product_id")), {**catalogue, pid: p}):
            bad_comp.append(str(comp.get("product_id")))
    add("components", "Included products are launched and valid", not bad_comp,
        "Not launched or invalid: " + ", ".join(bad_comp) if bad_comp else "")

    if p.get("nature") == "Physical item" and (d.get("stock") or "None") != "None" and offer_of(d)["mode"] in ("sold", "given"):
        has = any(s.get("preferred") for s in d.get("sources") or [])
        add("sourcing", "A supplier is set for this stock item", has,
            "" if has else "Add at least one supplier source (in Sourcing & costs) so stock can buy it")
    if r.get("tests_required", True):
        tests = r.get("tests") or []
        plan = standard_tests(p.get("nature") or "")

        def done(name: str) -> bool:
            return any(norm_name(t.get("name")) == norm_name(name) and (t.get("result") == "Pass" or (t.get("result") == "Waived" and (t.get("notes") or "").strip()))
                       and (t.get("tester") or "").strip() and t.get("date") for t in tests)

        bad = [t for t in tests if t.get("result") in ("Fail", "Pending")
               or (t.get("result") == "Pass" and not ((t.get("tester") or "").strip() and t.get("date")))]
        missing = [n for n in plan if not done(n)]
        add("testing", "Internal testing passed", not missing and not bad,
            ("Missing: " + ", ".join(missing)) if missing else (f"{len(bad)} test(s) failed, pending or without tester/date" if bad else ""))
    else:
        reason = (r.get("tests_exempt_reason") or "").strip()
        add("testing", "Internal testing skipped" + (" (reason recorded)" if sold else ""), bool(reason) or not sold,
            "" if (reason or not sold) else "Record why testing is not needed")

    ic = r.get("icasa") or {}
    required = ic.get("required")
    if required is None:                      # null means "use the default for this nature/usage"
        required = default_icasa_required(p.get("nature") or "", p.get("usage") or "")
    notice = int(ic.get("notice") or DEFAULT_NOTICE_DAYS)
    items = ic.get("items") or []
    if required:
        prods = [i for i in items if i.get("kind") == "Product"]
        issues = icasa_item_issues(prods[0], notice) if prods else ["product tariff lodgment"]
        add("icasa_product", "ICASA product lodgment", not issues, ("Needs: " + ", ".join(issues)) if issues else "")
        for i in (x for x in items if x.get("kind") == "Promotion"):
            q = icasa_item_issues(i, notice)
            add("icasa_promotion", "ICASA promotion lodgment", not q, ("Needs: " + ", ".join(q)) if q else "")
    else:
        reason = (ic.get("exempt_reason") or "").strip()
        ok = bool(reason) or not sold
        add("icasa", "ICASA lodgment not required" + (" (reason recorded)" if sold else ""), ok, "" if ok else "Record why no lodgment is needed")
    return out


def launch_effective_date(p: dict) -> Optional[str]:
    d = p.get("definition") or {}
    ic = (d.get("readiness") or {}).get("icasa") or {}
    required = ic.get("required")
    if required is None:
        required = default_icasa_required(p.get("nature") or "", p.get("usage") or "")
    if required:
        for i in ic.get("items") or []:
            if i.get("kind") == "Product" and i.get("effective"):
                return str(i["effective"])[:10]
    return d.get("launch_date") or None


# Fields that change the commercial terms of an active product; these need a revision, not a plain PATCH.
COMMERCIAL_FIELDS = ("price", "recurring", "term", "costs", "components", "fees", "supplier", "offer")
ACTIVE_LOCKED_COLUMNS = ("category", "range", "family", "nature", "usage")


def commercial_changes(old: dict, new: dict) -> list[str]:
    return [k for k in COMMERCIAL_FIELDS if (old or {}).get(k) != (new or {}).get(k)]


def referenced_by(pid: str, catalogue: Iterable[dict]) -> list[dict]:
    """Non-archived products that include ``pid``."""
    return [c for c in catalogue if c.get("status") != "archived" and str(c.get("id")) != pid
            and any(str(x.get("product_id")) == pid for x in (c.get("definition") or {}).get("components") or [])]
