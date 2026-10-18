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

def economics(pid: str, catalogue: dict[str, dict], _seen: Optional[frozenset] = None) -> dict:
    """Direct-cost economics of one product, recursing through included components.

    ``catalogue`` maps product id -> product view. A missing or cyclic component makes the cost sheet incomplete;
    a missing cost is never treated as zero."""
    seen = (_seen or frozenset()) | {pid}
    p = catalogue.get(pid)
    if p is None:
        return {"complete": False, "monthly": Decimal(0), "upfront": Decimal(0)}
    d = p.get("definition") or {}
    costs = d.get("costs") or []
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
    fee_once = fee_monthly = Decimal(0)
    for f in d.get("fees") or []:
        if f.get("enabled") and f.get("mode") == "Charge":
            if f.get("cadence") == "Once-off":
                fee_once += _d(f.get("amount"))
            elif f.get("cadence") == "Monthly":
                fee_monthly += _d(f.get("amount"))
    recurring = bool(d.get("recurring", True))
    price = _d(d.get("price"))
    horizon = max(1, int(d.get("term") or 24)) if recurring else 1
    revenue = (price + fee_monthly) * horizon + fee_once if recurring else price + fee_once
    cost = monthly * horizon + upfront
    return {"complete": complete, "monthly": monthly, "upfront": upfront, "horizon": horizon,
            "revenue": revenue, "cost": cost, "profit": revenue - cost,
            "margin_pct": (None if revenue == 0 else round((revenue - cost) / revenue * 100, 2))}


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
    add("price", "Selling price set", price > 0 or (not d.get("recurring", True) and not customer_facing))

    bad_comp = []
    for comp in d.get("components") or []:
        c = catalogue.get(str(comp.get("product_id")))
        if c is None or c.get("status") != "active":
            bad_comp.append(str(comp.get("product_id")))
        elif would_cycle(pid, str(comp.get("product_id")), {**catalogue, pid: p}):
            bad_comp.append(str(comp.get("product_id")))
    add("components", "Included products are launched and valid", not bad_comp,
        "Not launched or invalid: " + ", ".join(bad_comp) if bad_comp else "")

    if p.get("nature") == "Physical item" and (d.get("stock") or "None") != "None":
        has = any(s.get("preferred") for s in d.get("sources") or [])
        add("sourcing", "A supplier is set for this stock item", has,
            "" if has else "Add at least one supplier source (in Sourcing & costs) so stock can buy it")
    if r.get("tests_required", True):
        tests = r.get("tests") or []
        plan = standard_tests(p.get("nature") or "")

        def done(name: str) -> bool:
            return any(t.get("name") == name and (t.get("result") == "Pass" or (t.get("result") == "Waived" and (t.get("notes") or "").strip()))
                       and (t.get("tester") or "").strip() and t.get("date") for t in tests)

        bad = [t for t in tests if t.get("result") in ("Fail", "Pending")
               or (t.get("result") == "Pass" and not ((t.get("tester") or "").strip() and t.get("date")))]
        missing = [n for n in plan if not done(n)]
        add("testing", "Internal testing passed", not missing and not bad,
            ("Missing: " + ", ".join(missing)) if missing else (f"{len(bad)} test(s) failed, pending or without tester/date" if bad else ""))
    else:
        reason = (r.get("tests_exempt_reason") or "").strip()
        add("testing", "Internal testing skipped (reason recorded)", bool(reason), "" if reason else "Record why testing is not needed")

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
        add("icasa", "ICASA lodgment not required (reason recorded)", bool(reason), "" if reason else "Record why no lodgment is needed")
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
COMMERCIAL_FIELDS = ("price", "recurring", "term", "costs", "components", "fees", "supplier")
ACTIVE_LOCKED_COLUMNS = ("category", "range", "family", "nature", "usage")


def commercial_changes(old: dict, new: dict) -> list[str]:
    return [k for k in COMMERCIAL_FIELDS if (old or {}).get(k) != (new or {}).get(k)]


def referenced_by(pid: str, catalogue: Iterable[dict]) -> list[dict]:
    """Non-archived products that include ``pid``."""
    return [c for c in catalogue if c.get("status") != "archived" and str(c.get("id")) != pid
            and any(str(x.get("product_id")) == pid for x in (c.get("definition") or {}).get("components") or [])]
