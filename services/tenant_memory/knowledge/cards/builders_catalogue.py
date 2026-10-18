"""Knowledge cards for the product catalogue (module `inventory`), so agents and RAG chat can answer questions
about what we sell, how it is described and priced, what it includes, and where it is in its launch.

Index policy (deliberate): selling price, customer fees, specs, inclusions, customer-visible document titles, policy
references, competitor research and launch/ICASA status are indexed. Cost lines, supplier names, margins and
economics are NEVER read (margin is finance-only), and neither are internal-only documents or evidence files.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from services.tenant_memory.knowledge.cards.base import Card, allowed_fields, frontmatter, pick
from services.tenant_memory.knowledge.cards.builders_ext import _d, _s, _yn, jsonish
from services.tenant_memory.knowledge.kdata import IMPORTANCE, Edge

CATALOGUE_FIELDS = ("id", "product_number", "name", "category", "range", "family", "nature", "usage", "status", "owner",
                    "launched_at", "definition", "source_refs", "updated_at")
LIFECYCLE = {"draft": "Draft (in development)", "in_review": "In review", "active": "Active (launched)", "archived": "Archived"}


def _price(d: dict) -> str:
    try:
        p = float(d.get("price") or 0)
    except (TypeError, ValueError):
        return "not set"
    if p <= 0:
        return "not set"
    return f"R{p:,.2f} excluding tax" + (" per month" if d.get("recurring", True) else " once-off")


def catalogue_product_card(row: dict, names: dict[str, tuple[str, str]], as_of: Optional[datetime],
                           supplier_names: Optional[dict[str, str]] = None) -> Card:
    """``names`` maps component product id -> (product_number, name) for readable inclusions."""
    r = pick(row, allowed_fields("catalogue_product", CATALOGUE_FIELDS))
    d = jsonish(r.get("definition")) or {}
    pid = str(r["id"])
    status = str(r.get("status") or "draft")
    title = d.get("customer_name") or r.get("name")
    lines = [f"# Product: {_s(title, 160)} ({_s(r.get('product_number'), 40)})", "",
             f"- Internal name: {_s(r.get('name'), 160)}" if d.get("customer_name") else "",
             f"- Lifecycle: {LIFECYCLE.get(status, status)}",
             f"- Category: {_s(r.get('category'), 80) or 'unclassified'} > Range: {_s(r.get('range'), 80) or 'unclassified'}",
             f"- Service family: {_s(r.get('family'), 80) or 'unclassified'}",
             f"- Nature: {_s(r.get('nature'), 40)}; usage: {_s(r.get('usage'), 40)}",
             f"- Selling price: {_price(d)}"]
    if d.get("recurring", True) and d.get("term"):
        lines.append(f"- Contract term: {int(d['term'])} months")
    if d.get("down") or d.get("up"):
        lines.append(f"- Speed: {d.get('down') or '?'} / {d.get('up') or '?'} Mbps (download / upload)")
    if r.get("nature") == "Physical item" and d.get("stock") not in (None, "", "None"):
        lines.append(f"- Stock tracking: {_s(d.get('stock'), 30)}; unit: {_s(d.get('unit'), 30)}")
    lines = [x for x in lines if x != ""]
    if d.get("description"):
        lines += ["", "## Description", _s(d["description"], 1200)]

    comps = d.get("components") or []
    edges: list[Edge] = []
    if comps:
        lines += ["", "## Includes"]
        for c in comps:
            cid = str(c.get("product_id"))
            num, nm = names.get(cid, ("", "an unavailable product"))
            lines.append(f"- {int(c.get('qty') or 1)} x {_s(nm, 120)}" + (f" ({_s(num, 40)})" if num else "") + " at no customer charge")
            edges.append(Edge("catalogue_product", pid, "catalogue_product", cid, "includes"))

    refs = jsonish(r.get("source_refs")) or []
    if refs:
        # Names only. Supplier prices, lead times and performance scores are not part of the product knowledge.
        lines += ["", "## Suppliers"] + [f"- {_s((supplier_names or {}).get(str(x.get('supplier_id'))) or 'a listed supplier', 100)}" + (" (preferred)" if x.get("preferred") else "") for x in refs]

    fees = [f for f in (d.get("fees") or []) if f.get("enabled")]
    if fees:
        lines += ["", "## Customer fees"]
        for f in fees:
            amt = "R0" if f.get("mode") in ("Included", "Waived") else f"R{float(f.get('amount') or 0):,.2f}"
            lines.append(f"- {_s(f.get('name'), 60)}: {amt} ({_s(f.get('cadence'), 20).lower()}; {_s(f.get('mode'), 20).lower()})")

    docs = [x for x in (d.get("documents") or []) if x.get("visibility") == "Customer portal"]
    media = [x for x in (d.get("media") or []) if x.get("visibility") == "Customer portal"]
    if docs or media or d.get("policy_refs"):
        lines += ["", "## Customer-facing material"]
        for x in docs:
            lines.append(f"- {_s(x.get('category'), 40)}: {_s(x.get('name'), 100)} (version {_s(x.get('version'), 10)}"
                         + ("; customer acceptance required" if x.get("acceptance") else "") + ")")
        if media:
            lines.append(f"- {len(media)} product picture(s)/media on the customer portal")
        for ref in d.get("policy_refs") or []:
            lines.append(f"- Linked fee/terms policy: {_s(ref, 80)}")

    research = (d.get("research") or {}).get("rows") or []
    if research:
        lines += ["", "## Competitor research (manually recorded)"]
        for c in research[:12]:
            price = f"R{float(c['price']):,.2f}" if c.get("price") not in (None, "") else "price not recorded"
            lines.append(f"- {_s(c.get('name'), 60)}: {_s(c.get('offer'), 80)}, {price}"
                         + (f", {_s(c.get('spec'), 60)}" if c.get("spec") else "") + (f" (checked {_s(c.get('date'), 12)})" if c.get("date") else ""))

    market = (d.get("research") or {}).get("market") or {}
    if market.get("summary"):
        # Web-derived and model-written: indexed as a clearly labelled, short, untrusted note (never as instructions).
        domains = sorted({_s(s.get("domain"), 60) for s in (market.get("sources") or []) if s.get("domain")})[:8]
        lines += ["", "## Market research (AI-assisted summary of public web pages, unverified)",
                  _s(market["summary"], 700), f"Checked {_d(market.get('checked_at'))}" + (f"; sources: {', '.join(domains)}" if domains else "")]

    rd = d.get("readiness") or {}
    tests = rd.get("tests") or []
    ic = rd.get("icasa") or {}
    lines += ["", "## Launch readiness"]
    if rd.get("tests_required", True):
        passed = sum(1 for t in tests if t.get("result") == "Pass")
        lines.append(f"- Internal testing: {passed} of {len(tests)} recorded tests passed")
    else:
        lines.append("- Internal testing: skipped by decision (reason recorded)")
    icasa_required = ic.get("required")
    if icasa_required is None:                    # null = default for this nature/usage
        icasa_required = r.get("nature") == "Digital service" and r.get("usage") == "Customer-facing"
    if icasa_required:
        for i in ic.get("items") or []:
            state = "acknowledged by ICASA" if i.get("ack") else "lodged" if i.get("lodged") else "not yet lodged"
            window = f", promotion {_d(i.get('promo_start'))} to {_d(i.get('promo_end'))}" if i.get("kind") == "Promotion" else ""
            lines.append(f"- ICASA {str(i.get('kind') or '').lower()} notification: {state}; effective {_d(i.get('effective'))}{window}")
        if not (ic.get("items") or []):
            lines.append("- ICASA lodgment: required, not started")
    else:
        lines.append("- ICASA lodgment: not required (reason recorded)")
    if r.get("launched_at"):
        lines.append(f"- Launched: {_d(r['launched_at'])}")
    kpis = (d.get("research") or {}).get("kpis") or []
    if kpis:
        lines.append("- Tracked KPIs: " + ", ".join(_s(k, 30) for k in kpis))

    tags = ["catalogue", "product", status, str(r.get("nature") or "").lower().replace(" ", "-")]
    md = frontmatter("catalogue_product", pid, "inventory", as_of, tags,
                     {"product_number": r.get("product_number"), "status": status}) + "\n".join(lines) + "\n"
    return Card("catalogue_product", pid, "inventory", f"Product: {_s(title, 100)} ({_s(r.get('product_number'), 40)})", md, as_of,
                [t for t in tags if t], IMPORTANCE["high"] if status == "active" else IMPORTANCE["normal"],
                {"deep_link": f"/dashboard?module=products&product={pid}", "product_number": r.get("product_number")}, edges)
