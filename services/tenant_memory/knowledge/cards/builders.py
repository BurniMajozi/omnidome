"""Card builders: pure functions turning already-fetched rows into deterministic markdown cards.

Rules every builder follows:
  * only fields on its allow-list reach the output (see base.NEVER_INDEX / allowed_fields);
  * free text is scrubbed (emails, phones, ID/card/bank numbers, credentials) and clipped;
  * output depends only on the input rows (stable ordering, no clock) so the content hash is stable;
  * relationships are emitted as Edge objects (foreign keys) for the graph layer.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Optional

from services.tenant_memory.knowledge.cards.base import (
    Card, allowed_fields, fmt_dt, frontmatter, initial_name, link, money, pick,
)
from services.tenant_memory.knowledge.kdata import IMPORTANCE, Edge
from services.tenant_memory.knowledge.textutil import clip, scrub

CUSTOMER_FIELDS = ("id", "first_name", "last_name", "status", "province", "account_number", "rica_verified",
                   "company_id", "created_at", "updated_at")
LEAD_FIELDS = ("id", "source", "first_name", "last_name", "coverage_area", "interested_package", "status",
               "notes", "converted_customer_id", "converted_at", "created_at", "updated_at")
DEAL_FIELDS = ("id", "contact_id", "lead_id", "name", "stage_name", "probability", "value_zar", "status", "close_date",
               "closed_at", "close_reason", "notes", "created_at", "updated_at")
TICKET_FIELDS = ("id", "customer_id", "subject", "description", "priority", "status", "category", "is_fcr",
                 "resolution_notes", "resolved_at", "created_at", "updated_at")
CAMPAIGN_FIELDS = ("id", "name", "channel", "status", "description", "budget_zar", "start_date", "end_date",
                   "audience_segment_id", "total_sent", "total_delivered", "total_opened", "total_clicked",
                   "total_conversions", "updated_at")


def _rate(num: int, den: int) -> str:
    return f"{100.0 * num / den:.1f}%" if den else "n/a"


def _ago(v: Any) -> str:
    return fmt_dt(v) or "unknown date"


# ── CRM ────────────────────────────────────────────────────────────────────

def customer_card(row: dict, subscriptions: list[dict], balance: dict, tickets: list[dict], tags: list[str],
                  as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("customer", CUSTOMER_FIELDS))
    cid = str(r["id"])
    name = initial_name(r.get("first_name"), r.get("last_name"))
    lines = [f"# Customer {name}", "",
             "## Profile",
             f"- Status: {r.get('status') or 'unknown'}",
             f"- Province: {r.get('province') or 'not recorded'}",
             f"- RICA verified: {'yes' if r.get('rica_verified') else 'no'}",
             f"- Customer since: {_ago(r.get('created_at'))}"]
    if r.get("account_number"):
        lines.append(f"- Account number: {r['account_number']}")
    edges: list[Edge] = []
    if r.get("company_id"):
        lines.append(f"- Company: {link('company', str(r['company_id']))}")
        edges.append(Edge("customer", cid, "company", str(r["company_id"]), "member_of", 1.0, as_of))
    lines += ["", "## Subscriptions"]
    if not subscriptions:
        lines.append("- None on record.")
    for s in sorted(subscriptions, key=lambda s: (str(s.get("status")), str(s.get("plan")), str(s.get("id")))):
        lines.append(f"- {s.get('plan')} ({s.get('status')}), {money(s.get('base_price_zar'))} per {s.get('billing_interval') or 'month'}"
                     + (f", segment {s['segment']}" if s.get("segment") else "")
                     + (f", period ends {fmt_dt(s.get('current_period_end'))}" if s.get("current_period_end") else "")
                     + f" {link('subscription', str(s['id']))}")
        edges.append(Edge("customer", cid, "subscription", str(s["id"]), "has_subscription", 1.0, as_of))
    lines += ["", "## Balance (as of this card)",
              f"- Open invoices: {int(balance.get('open_invoices') or 0)}",
              f"- Outstanding: {money(balance.get('outstanding_zar'))}",
              f"- Overdue invoices: {int(balance.get('overdue_invoices') or 0)}"]
    lines += ["", "## Recent support tickets"]
    if not tickets:
        lines.append("- None.")
    for t in sorted(tickets, key=lambda t: (str(t.get("created_at")), str(t.get("id"))), reverse=True)[:3]:
        lines.append(f"- {_ago(t.get('created_at'))} [{t.get('status')}/{t.get('priority')}] "
                     f"{clip(scrub(t.get('subject')), 120)} {link('ticket', str(t['id']))}")
        edges.append(Edge("customer", cid, "ticket", str(t["id"]), "raised", 1.0, as_of))
    if tags:
        lines += ["", "## Tags", "- " + ", ".join(sorted(set(tags)))]
    md = frontmatter("customer", cid, "crm", as_of, ["customer", str(r.get("status") or "unknown").lower()],
                     {"customer_id": cid}) + "\n".join(lines) + "\n"
    imp = IMPORTANCE["high"] if int(balance.get("overdue_invoices") or 0) > 0 else IMPORTANCE["normal"]
    return Card("customer", cid, "crm", f"Customer {name}", md, as_of, ["customer"], imp,
                {"deep_link": f"/dashboard/crm?customer={cid}"}, edges)


def lead_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("lead", LEAD_FIELDS))
    lid = str(r["id"])
    name = initial_name(r.get("first_name"), r.get("last_name"))
    lines = [f"# Lead {name}", "",
             f"- Status: {r.get('status') or 'new'}",
             f"- Source: {r.get('source') or 'unknown'}",
             f"- Coverage area: {r.get('coverage_area') or 'not recorded'}",
             f"- Interested in: {r.get('interested_package') or 'not specified'}",
             f"- Created: {_ago(r.get('created_at'))}"]
    edges = []
    if r.get("converted_customer_id"):
        lines.append(f"- Converted to {link('customer', str(r['converted_customer_id']))} on {_ago(r.get('converted_at'))}")
        edges.append(Edge("lead", lid, "customer", str(r["converted_customer_id"]), "converted_to", 1.0, as_of))
    if r.get("notes"):
        lines += ["", "## Notes", clip(scrub(r["notes"]), 600)]
    md = frontmatter("lead", lid, "crm", as_of, ["lead", str(r.get("status") or "new").lower()], {"lead_id": lid}) + "\n".join(lines) + "\n"
    return Card("lead", lid, "crm", f"Lead {name}", md, as_of, ["lead"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/crm?lead={lid}"}, edges)


# ── Sales ──────────────────────────────────────────────────────────────────

def deal_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("deal", DEAL_FIELDS))
    did = str(r["id"])
    lines = [f"# Deal: {clip(scrub(r.get('name')), 120)}", "",
             f"- Stage: {r.get('stage_name') or 'unknown'} ({r.get('probability') if r.get('probability') is not None else '?'}% probability)",
             f"- Status: {r.get('status')}",
             f"- Value: {money(r.get('value_zar'))}",
             f"- Created: {_ago(r.get('created_at'))}"]
    if r.get("close_date"):
        lines.append(f"- Expected close: {fmt_dt(r['close_date'])}")
    if r.get("closed_at"):
        lines.append(f"- Closed: {fmt_dt(r['closed_at'])}" + (f" ({clip(scrub(r.get('close_reason')), 160)})" if r.get("close_reason") else ""))
    edges = []
    if r.get("lead_id"):
        lines.append(f"- From lead {link('lead', str(r['lead_id']))}")
        edges.append(Edge("deal", did, "lead", str(r["lead_id"]), "originated_from", 1.0, as_of))
    if r.get("contact_id"):
        # sales.deals.contact_id is a contact id; it equals the CRM customer id for converted customers.
        edges.append(Edge("deal", did, "customer", str(r["contact_id"]), "for_contact", 0.7, as_of))
    if r.get("notes"):
        lines += ["", "## Notes", clip(scrub(r["notes"]), 600)]
    md = frontmatter("deal", did, "sales", as_of, ["deal", str(r.get("status") or "").lower()], {"deal_id": did}) + "\n".join(lines) + "\n"
    imp = IMPORTANCE["high"] if str(r.get("status")).upper() == "OPEN" and float(r.get("value_zar") or 0) >= 50000 else IMPORTANCE["normal"]
    return Card("deal", did, "sales", f"Deal {clip(scrub(r.get('name')), 80)}", md, as_of, ["deal"], imp,
                {"deep_link": f"/dashboard/sales?deal={did}"}, edges)


def pipeline_digest(pipeline_id: str, pipeline_name: str, stages: list[dict], as_of: Optional[datetime]) -> Card:
    """stages: [{name, sort_order, probability, open_deals, open_value_zar}] plus won/lost totals under key 'totals'."""
    ordered = sorted((s for s in stages if "name" in s), key=lambda s: (s.get("sort_order") or 0, s["name"]))
    totals = next((s for s in stages if s.get("totals")), {}).get("totals", {})
    lines = [f"# Sales pipeline: {clip(scrub(pipeline_name), 80)}", "", "## Open deals by stage (as of this card)"]
    for s in ordered:
        lines.append(f"- {s['name']}: {int(s.get('open_deals') or 0)} deals, {money(s.get('open_value_zar'))}")
    lines += ["", "## Outcomes", f"- Won: {int(totals.get('won', 0))} deals, {money(totals.get('won_value_zar'))}",
              f"- Lost: {int(totals.get('lost', 0))} deals, {money(totals.get('lost_value_zar'))}"]
    md = frontmatter("pipeline", pipeline_id, "sales", as_of, ["pipeline", "digest"], {"pipeline_id": pipeline_id}) + "\n".join(lines) + "\n"
    return Card("pipeline", pipeline_id, "sales", f"Pipeline {clip(pipeline_name, 80)}", md, as_of, ["pipeline", "digest"],
                IMPORTANCE["normal"], {"deep_link": "/dashboard/sales"})


# ── Billing ────────────────────────────────────────────────────────────────

def billing_digest(month: str, segment: str, agg: dict, as_of: Optional[datetime]) -> Card:
    """One invoice/payment digest per (month, customer segment). `agg` is computed in SQL by the source."""
    sid = f"{month}:{segment}"
    lines = [f"# Billing digest {month}, segment {segment}", "",
             "Figures are a snapshot as of the card date; use governed queries for reporting numbers.", "",
             "## Invoicing",
             f"- Invoices issued: {int(agg.get('invoices') or 0)}",
             f"- Invoiced total: {money(agg.get('invoiced_zar'))} (VAT {money(agg.get('vat_zar'))})",
             f"- Paid in full: {int(agg.get('paid') or 0)}  |  Partially paid: {int(agg.get('partial') or 0)}  |  Unpaid: {int(agg.get('unpaid') or 0)}",
             f"- Overdue invoices: {int(agg.get('overdue') or 0)} worth {money(agg.get('overdue_zar'))}",
             "", "## Collections",
             f"- Payments received: {int(agg.get('payments') or 0)} totalling {money(agg.get('collected_zar'))}",
             f"- Collection rate on invoiced value: {_rate(int(float(agg.get('collected_zar') or 0)), int(float(agg.get('invoiced_zar') or 0)))}"]
    methods = agg.get("methods") or {}
    if methods:
        lines.append("- By method: " + ", ".join(f"{k} {v}" for k, v in sorted(methods.items())))
    md = frontmatter("billing_digest", sid, "billing", as_of, ["billing", "digest", month, f"segment-{segment}"],
                     {"month": month, "segment": segment}) + "\n".join(lines) + "\n"
    return Card("billing_digest", sid, "billing", f"Billing digest {month} ({segment})", md, as_of,
                ["billing", "digest"], IMPORTANCE["normal"], {"deep_link": "/dashboard/billing", "month": month})


# ── Support ────────────────────────────────────────────────────────────────

def ticket_card(row: dict, replies: list[dict], as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("ticket", TICKET_FIELDS))
    tid = str(r["id"])
    lines = [f"# Ticket: {clip(scrub(r.get('subject')), 140)}", "",
             f"- Status: {r.get('status')}  |  Priority: {r.get('priority')}  |  Category: {r.get('category') or 'uncategorised'}",
             f"- Opened: {_ago(r.get('created_at'))}"
             + (f"  |  Resolved: {fmt_dt(r['resolved_at'])}" if r.get("resolved_at") else ""),
             f"- First-contact resolution: {'yes' if r.get('is_fcr') else 'no'}"]
    edges = []
    if r.get("customer_id"):
        lines.append(f"- Customer: {link('customer', str(r['customer_id']))}")
        edges.append(Edge("ticket", tid, "customer", str(r["customer_id"]), "raised_by", 1.0, as_of))
    if r.get("description"):
        lines += ["", "## Description", clip(scrub(r["description"]), 700)]
    public = [x for x in replies if not x.get("is_private")]
    if public:
        lines += ["", "## Conversation (public replies)"]
        for x in sorted(public, key=lambda x: (str(x.get("created_at")), str(x.get("id"))))[:6]:
            lines.append(f"- {_ago(x.get('created_at'))} {x.get('author_type')}: {clip(scrub(x.get('message')), 280)}")
    if r.get("resolution_notes"):
        lines += ["", "## Resolution", clip(scrub(r["resolution_notes"]), 500)]
    md = frontmatter("ticket", tid, "support", as_of, ["ticket", str(r.get("status") or "").lower(), str(r.get("category") or "general").lower()],
                     {"ticket_id": tid}) + "\n".join(lines) + "\n"
    imp = IMPORTANCE["high"] if str(r.get("priority")).upper() in {"HIGH", "URGENT"} else IMPORTANCE["normal"]
    return Card("ticket", tid, "support", f"Ticket {clip(scrub(r.get('subject')), 80)}", md, as_of, ["ticket"], imp,
                {"deep_link": f"/dashboard/support?ticket={tid}"}, edges)


# ── Marketing ──────────────────────────────────────────────────────────────

def campaign_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("campaign", CAMPAIGN_FIELDS))
    cid = str(r["id"])
    sent, deliv = int(r.get("total_sent") or 0), int(r.get("total_delivered") or 0)
    opened, clicked, conv = int(r.get("total_opened") or 0), int(r.get("total_clicked") or 0), int(r.get("total_conversions") or 0)
    lines = [f"# Campaign: {clip(scrub(r.get('name')), 120)}", "",
             f"- Channel: {r.get('channel')}  |  Status: {r.get('status')}",
             f"- Budget: {money(r.get('budget_zar'))}",
             f"- Window: {fmt_dt(r.get('start_date')) or 'open'} to {fmt_dt(r.get('end_date')) or 'open'}",
             "", "## Performance (as of this card)",
             f"- Sent {sent}, delivered {deliv} ({_rate(deliv, sent)}), opened {opened} ({_rate(opened, deliv)}), "
             f"clicked {clicked} ({_rate(clicked, deliv)}), conversions {conv} ({_rate(conv, deliv)})"]
    edges = []
    if r.get("audience_segment_id"):
        lines.append(f"- Audience: {link('audience_segment', str(r['audience_segment_id']))}")
        edges.append(Edge("campaign", cid, "audience_segment", str(r["audience_segment_id"]), "targets", 1.0, as_of))
    if r.get("description"):
        lines += ["", "## Brief", clip(scrub(r["description"]), 600)]
    md = frontmatter("campaign", cid, "marketing", as_of, ["campaign", str(r.get("channel") or "").lower()], {"campaign_id": cid}) + "\n".join(lines) + "\n"
    return Card("campaign", cid, "marketing", f"Campaign {clip(scrub(r.get('name')), 80)}", md, as_of, ["campaign"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/marketing?campaign={cid}"}, edges)


def social_digest(platform: str, month: str, rows: list[dict], as_of: Optional[datetime]) -> Card:
    """rows: social_analytics rows (metric_date, followers, impressions, reach, engagement_rate, likes_total, ...) for one platform+month."""
    ordered = sorted(rows, key=lambda r: str(r.get("metric_date")))
    sid = f"{platform}:{month}"
    lines = [f"# Social analytics {platform}, {month}", "", "Daily snapshots aggregated; use governed queries for reporting numbers.", ""]
    if ordered:
        first, last = ordered[0], ordered[-1]
        eng = [float(r["engagement_rate"]) for r in ordered if r.get("engagement_rate") is not None]
        lines += [f"- Snapshots: {len(ordered)} days ({fmt_dt(first.get('metric_date'))} to {fmt_dt(last.get('metric_date'))})",
                  f"- Followers: {int(first.get('followers') or 0)} at start, {int(last.get('followers') or 0)} at end "
                  f"({int(last.get('followers') or 0) - int(first.get('followers') or 0):+d})",
                  f"- Impressions: {sum(int(r.get('impressions') or 0) for r in ordered)}, reach: {sum(int(r.get('reach') or 0) for r in ordered)}",
                  f"- Likes {sum(int(r.get('likes_total') or 0) for r in ordered)}, comments {sum(int(r.get('comments_total') or 0) for r in ordered)}, "
                  f"shares {sum(int(r.get('shares_total') or 0) for r in ordered)}",
                  f"- Average engagement rate: {(sum(eng) / len(eng)):.4f}" if eng else "- Average engagement rate: n/a"]
    md = frontmatter("social_digest", sid, "marketing", as_of, ["social", "digest", platform.lower(), month],
                     {"platform": platform, "month": month}) + "\n".join(lines) + "\n"
    return Card("social_digest", sid, "marketing", f"Social {platform} {month}", md, as_of, ["social", "digest"],
                IMPORTANCE["normal"], {"deep_link": "/dashboard/marketing", "month": month})


# ── BI Studio research / competitors / campaign analysis ───────────────────

def research_card(run: dict, as_of: Optional[datetime]) -> Card:
    rid = str(run["id"])
    rep = run.get("report") or {}
    srcs = {str(s.get("id", i + 1)): s for i, s in enumerate(run.get("sources") or []) if isinstance(s, dict)}
    lines = [f"# Research: {clip(scrub(run.get('question')), 160)}", "", "## Summary", clip(rep.get("summary") or "No supported summary.", 1500), ""]
    if rep.get("key_findings"):
        lines.append("## Key findings")
        for f in rep["key_findings"][:10]:
            ids = ", ".join(f"[{i}]" for i in f.get("source_ids") or [])
            lines.append(f"- {clip(f.get('claim'), 300)} {ids}")
    if rep.get("limitations"):
        lines += ["", "## Limitations"] + [f"- {clip(x, 200)}" for x in rep["limitations"][:6]]
    if srcs:
        lines += ["", "## Sources"]
        for k, s in sorted(srcs.items()):
            lines.append(f"- [{k}] {clip(s.get('title') or s.get('url') or '', 120)} - {s.get('url', '')}")
    md = frontmatter("research", rid, "analytics", as_of, ["research", "bi-studio"], {"run_id": rid}) + "\n".join(lines) + "\n"
    return Card("research", rid, "analytics", f"Research {clip(scrub(run.get('question')), 90)}", md, as_of,
                ["research", "bi-studio"], IMPORTANCE["high"], {"deep_link": f"/dashboard?section=analytics&sub=research&research={rid}",
                                                              "cited_urls": [s.get("url") for s in srcs.values() if s.get("url")][:10]})


def competitor_card(comp: dict, snapshot: Optional[dict], changes: list[dict], as_of: Optional[datetime]) -> Card:
    cid = str(comp["id"])
    lines = [f"# Competitor: {clip(comp.get('name'), 100)}", "", f"- Website: {comp.get('website')}",
             f"- Last scanned: {fmt_dt(comp.get('last_scanned_at')) or 'never'} (status {comp.get('last_status') or comp.get('scan_status')})"]
    if snapshot:
        lines += ["", f"## Latest plans (snapshot {fmt_dt(snapshot.get('scanned_at'))})"]
        for p in (snapshot.get("plans") or [])[:12]:
            if isinstance(p, dict):
                lines.append(f"- {clip(str(p.get('name') or p.get('plan') or 'plan'), 80)}: {clip(str(p.get('price') or p.get('monthly_price') or ''), 40)} "
                             f"{clip(str(p.get('speed') or ''), 40)} {('(' + p['source_url'] + ')') if p.get('source_url') else ''}".rstrip())
        promos = [p for p in (snapshot.get("promotions") or []) if isinstance(p, dict)]
        if promos:
            lines += ["", "## Promotions"]
            for p in promos[:8]:
                lines.append(f"- {clip(str(p.get('title') or p.get('name') or p.get('description') or ''), 160)} {('(' + p['source_url'] + ')') if p.get('source_url') else ''}".rstrip())
        pages = [p.get("url") for p in (snapshot.get("pages") or []) if isinstance(p, dict) and p.get("url")]
        if pages:
            lines += ["", "Source pages: " + ", ".join(pages[:5])]
    if changes:
        lines += ["", "## Recent changes"]
        for ch in sorted(changes, key=lambda c: str(c.get("detected_at")), reverse=True)[:10]:
            lines.append(f"- {fmt_dt(ch.get('detected_at'))} {ch.get('change_type')}: {clip(ch.get('subject'), 120)} "
                         f"{clip(str(ch.get('old_value') or ''), 40)} -> {clip(str(ch.get('new_value') or ''), 40)}"
                         + (f" ({ch['pct_change']:+.1f}%)" if ch.get("pct_change") is not None else "")
                         + (f" {ch['source_url']}" if ch.get("source_url") else ""))
    md = frontmatter("competitor", cid, "analytics", as_of, ["competitor", "bi-studio"], {"competitor_id": cid}) + "\n".join(lines) + "\n"
    return Card("competitor", cid, "analytics", f"Competitor {clip(comp.get('name'), 80)}", md, as_of, ["competitor", "bi-studio"],
                IMPORTANCE["high"], {"deep_link": f"/dashboard?section=analytics&sub=competitors&competitor={cid}", "website": comp.get("website")})


def campaign_analysis_card(a: dict, as_of: Optional[datetime]) -> Card:
    aid = str(a["id"])
    agg = a.get("aggregate") or {}
    overall = agg.get("overall") or {}
    split = overall.get("split") or {}
    lines = [f"# Campaign analysis: {clip(scrub(a.get('name')), 120)}", "", f"- Subject: {clip(scrub(a.get('subject')), 160)}",
             f"- Items analysed: {int(a.get('item_count') or 0)} (last run {fmt_dt(a.get('last_run_at')) or 'never'})"]
    edges = []
    if overall.get("label"):
        lines.append(f"- Overall sentiment: {overall['label']} (avg {overall.get('avg_score')}); "
                     + ", ".join(f"{k} {split.get(k, {}).get('count', 0)}" for k in ("positive", "neutral", "negative")))
    for title, key in (("Most praised themes", "top_praised_themes"), ("Most complained-about themes", "top_complained_themes")):
        th = agg.get(key) or []
        if th:
            lines += ["", f"## {title}"] + [f"- {t.get('theme')} ({t.get('count')} mentions, avg {t.get('avg_score')})" for t in th[:5]]
            ex = [e for t in th[:3] for e in (t.get("examples") or [])[:1]]
            for e in ex:
                lines.append(f"  - e.g. \"{clip(scrub(e.get('excerpt')), 160)}\" ({e.get('domain')}) {e.get('url', '')}")
    if a.get("limitations"):
        lines += ["", "## Limitations"] + [f"- {clip(str(x), 200)}" for x in a["limitations"][:5]]
    if a.get("own_campaign_id"):
        edges.append(Edge("campaign_analysis", aid, "campaign", str(a["own_campaign_id"]), "analyses", 1.0, as_of))
    if a.get("competitor_id"):
        edges.append(Edge("campaign_analysis", aid, "competitor", str(a["competitor_id"]), "analyses", 1.0, as_of))
    md = frontmatter("campaign_analysis", aid, "analytics", as_of, ["campaign-analysis", "sentiment", "bi-studio"], {"analysis_id": aid}) + "\n".join(lines) + "\n"
    return Card("campaign_analysis", aid, "analytics", f"Campaign analysis {clip(scrub(a.get('name')), 80)}", md, as_of,
                ["campaign-analysis", "bi-studio"], IMPORTANCE["high"], {"deep_link": f"/dashboard?section=analytics&sub=campaign-analysis&analysis={aid}"}, edges)


# ── Tenant memory + OKF skills ─────────────────────────────────────────────

def memory_entry_card(e: dict, as_of: Optional[datetime]) -> Card:
    eid = str(e["id"])
    imp = IMPORTANCE.get(str(e.get("importance") or "normal"), 0.5)
    lines = [f"# {clip(scrub(e.get('title')), 160)}", "",
             f"- Recorded: {fmt_dt(e.get('occurred_at'))}  |  Source: {e.get('source_type')}"
             + (f"  |  Scope: {e['scope_key']}" if e.get("scope_key") else ""), ""]
    if e.get("summary"):
        lines += [clip(scrub(e["summary"]), 600), ""]
    lines.append(scrub(e.get("content") or "")[:6000])
    tags = ["memory", "episodic", *[str(t) for t in (e.get("tags") or [])]]
    md = frontmatter("memory_entry", eid, e.get("module") or "memory", as_of, tags,
                     {"entry_id": eid, "memory_tier": "episodic"}) + "\n".join(lines) + "\n"
    edges = []
    sk = str(e.get("scope_key") or "")
    if ":" in sk:
        kind, ident = sk.split(":", 1)
        if kind in {"customer", "lead", "ticket", "deal", "campaign", "invoice", "subscription"} and ident:
            edges.append(Edge("memory_entry", eid, kind, ident, "about", 0.8, as_of))
    vis = e.get("visibility") or "tenant"
    return Card("memory_entry", eid, e.get("module") or "memory", clip(scrub(e.get("title")), 120), md, as_of, tags, imp,
                {"deep_link": f"/dashboard/admin?memory={eid}"}, edges, visibility=vis if vis in ("private", "team", "tenant", "system") else "tenant",
                required_roles=[] if vis != "team" else None)


def memory_summary_card(s: dict, as_of: Optional[datetime]) -> Card:
    sid = f"{s.get('scope_key')}"
    lines = [f"# Summary: {clip(scrub(s.get('title')), 160)}", "", f"- Scope: {s.get('scope_key')}  |  Updated: {fmt_dt(s.get('updated_at'))}",
             f"- Built from {len(s.get('source_entry_ids') or [])} memory entries", "", scrub(s.get("summary") or "")[:6000]]
    md = frontmatter("memory_summary", sid, s.get("module") or "memory", as_of, ["memory", "semantic", "summary"],
                     {"scope_key": s.get("scope_key"), "memory_tier": "semantic"}) + "\n".join(lines) + "\n"
    return Card("memory_summary", sid, s.get("module") or "memory", clip(scrub(s.get("title")), 120), md, as_of,
                ["memory", "semantic"], IMPORTANCE["high"], {"deep_link": "/dashboard/admin"}, required_roles=[], visibility="tenant")


def skill_card(sk: dict, as_of: Optional[datetime]) -> Card:
    """Procedural memory: embeds what a skill is FOR (description, triggers, tools, safety), never its instructions."""
    kid = str(sk["id"])
    scope = sk.get("scope") or "tenant"
    triggers = [clip(scrub(t), 80) for t in (sk.get("triggers") or [])[:12]]
    lines = [f"# Skill: {sk.get('skill_name')} v{sk.get('version')}", "",
             f"- Category: {sk.get('category')}  |  Scope: {scope}  |  Safety: {sk.get('safety_class') or 'read_only'}",
             f"- Available to: {', '.join(sk.get('target_agent_types') or []) or 'all agents'}",
             f"- Tools: {', '.join(sk.get('tools_required') or []) or 'none'}"]
    if triggers:
        lines.append(f"- Triggers: {'; '.join(triggers)}")
    lines += ["", "## When to use it", clip(scrub(sk.get("description")), 1200)]
    tags = ["skill", "procedural", str(sk.get("category") or "")] + [str(t) for t in (sk.get("tags") or [])[:6]]
    md = frontmatter("skill", kid, "memory", as_of, tags,
                     {"skill_name": sk.get("skill_name"), "memory_tier": "procedural", "scope": scope,
                      "slug": sk.get("slug")}) + "\n".join(lines) + "\n"
    roles = [str(r) for r in (sk.get("visibility_roles") or [])] if scope == "team" else []
    return Card("skill", kid, "memory", f"Skill {sk.get('skill_name')}", md, as_of, ["skill", "procedural"], IMPORTANCE["normal"],
                {"deep_link": "/dashboard/admin?tab=skills", "skill_name": sk.get("skill_name"), "slug": sk.get("slug"),
                 "scope": scope}, required_roles=roles, visibility="team" if roles else "tenant")


# ── Metric facts (deterministic numbers, rendered as context cards) ────────

def _period_label(start: Any, end: Any, grain: Optional[str]) -> str:
    s, e = fmt_dt(start), fmt_dt(end)
    try:
        if grain == "month" or (s[8:] == "01" and s[:7] == e[:7]):
            return datetime.strptime(s[:7], "%Y-%m").strftime("%B %Y")
    except ValueError:
        pass
    return s if s == e else f"{s} to {e}"


def _fmt_value(value: Any, unit: str) -> str:
    v = float(value)
    if unit in ("ZAR", "R", "currency"):
        return money(v)
    if unit in ("percent", "%"):
        return f"{v:.1f}%"
    return f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"


def metric_fact_card(f: dict, prior: Optional[dict], as_of: Optional[datetime]) -> Card:
    """One short card per fact. The card is context; the number's authority is source_query.
    `prior` is the previous period's fact for the same metric/dimensions/kind, if any."""
    fid = str(f["id"])
    label = f.get("label") or str(f["metric_key"]).replace("_", " ").capitalize()
    period = _period_label(f.get("period_start"), f.get("period_end"), f.get("grain"))
    unit = f.get("unit") or "count"
    kind = f.get("kind") or "actual"
    dims = f.get("dimensions") or {}
    dim_txt = ", ".join(f"{k}={v}" for k, v in sorted(dims.items()))
    head = f"{label}, {period}: {_fmt_value(f['value'], unit)}"
    if kind == "forecast":
        head += " (forecast"
        if f.get("lower_bound") is not None and f.get("upper_bound") is not None:
            lvl = f"{int(round(float(f['interval_level']) * 100))}% " if f.get("interval_level") else ""
            head += f", {lvl}interval {_fmt_value(f['lower_bound'], unit)} to {_fmt_value(f['upper_bound'], unit)}"
        head += ")"
    elif kind == "target":
        head += " (target)"
    delta = ""
    if prior is not None and float(prior["value"]) != 0:
        pct = 100.0 * (float(f["value"]) - float(prior["value"])) / abs(float(prior["value"]))
        delta = f", {pct:+.1f}% vs {_period_label(prior.get('period_start'), prior.get('period_end'), prior.get('grain'))}"
    lines = [f"# {head}{delta}", "", f"- Metric: {f['metric_key']}  |  Kind: {kind}  |  Unit: {unit}"]
    if dim_txt:
        lines.append(f"- Scope: {dim_txt}")
    lines.append(f"- Method: {f.get('method')}" + (f"  |  Confidence: {float(f['confidence']):.2f}" if f.get("confidence") is not None else ""))
    if kind == "forecast":
        lines.append(f"- Model: {f.get('model_name')} {f.get('model_version')}")
    sq = f.get("source_query") or {}
    if sq:
        meas = ", ".join(sq.get("measures") or [])
        lines.append(f"- Source query: dataset {sq.get('dataset')}, measures [{meas}]"
                     + (f", query key {f['source_query_key']}" if f.get("source_query_key") else ""))
    lines += ["", "Snapshot as of the card date. Re-run the referenced governed query for the exact, current value."]
    md = frontmatter("metric_fact", fid, "analytics", as_of, ["metric", f["metric_key"], kind],
                     {"metric_key": f["metric_key"], "kind": kind, "period_start": fmt_dt(f.get("period_start")),
                      "period_end": fmt_dt(f.get("period_end")), "query_key": f.get("source_query_key")}) + "\n".join(lines) + "\n"
    return Card("metric_fact", fid, "analytics", f"{label} {period}", md, as_of, ["metric", kind],
                IMPORTANCE["high"] if kind != "actual" else IMPORTANCE["normal"],
                {"deep_link": "/dashboard/analytics", "metric_key": f["metric_key"], "query_key": f.get("source_query_key"),
                 "source_query": sq or None, "value": float(f["value"]), "unit": unit})
