"""Card builders for the broad-coverage sources (compliance, HR, network/IoT/RICA, inventory, finance, call centre,
support KB, lifecycle/journeys, retention, portal builder, marketing segments).

Same rules as builders.py: pure functions of already-fetched rows (no clock, stable ordering), per-builder allow-lists
(`KNOWLEDGE_FIELDS_<SOURCE>` can only narrow), NEVER_INDEX columns never read, free text scrubbed and clipped, people shown
as initials or not at all, relationships emitted as Edge objects for the graph.

What is deliberately NOT read anywhere in this module (see docs/knowledge-layer.md): salaries/payroll, employee ID/tax numbers,
bank details, medical/leave data, named performance ratings, disciplinary/exit data, supplier contact details, customer
addresses, device credentials/serials/MACs/IPs, RICA ID numbers and personal fields, raw e-mail bodies, form-submission payloads.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable, Optional

from services.tenant_memory.knowledge.cards.base import (
    Card, allowed_fields, fmt_dt, frontmatter, link, money, pick,
)
from services.tenant_memory.knowledge.kdata import IMPORTANCE, Edge
from services.tenant_memory.knowledge.textutil import clip, scrub

DOC_MAX_CHARS = 40000          # a single long document stops here; the card says so
SECTION_CHARS = 1500           # sections are built to fit one chunk (CHUNK_CHARS default 1800)


# ── shared helpers ────────────────────────────────────────────────────────

def _s(v: Any, n: int = 300) -> str:
    return clip(scrub(None if v is None else str(v)), n)


def jsonish(v: Any) -> Any:
    """JSON columns may arrive as already-parsed objects or as strings depending on the driver."""
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except ValueError:
            return None
    return v


def _n(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _f(v: Any, nd: int = 1) -> str:
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "n/a"


def _d(v: Any) -> str:
    return fmt_dt(v) or "not set"


def _yn(v: Any) -> str:
    return "yes" if v else "no"


def _short_name(v: Any) -> str:
    """'Thandi Mokoena' -> 'Thandi M.' (staff names appear only as initials)."""
    parts = str(v or "").split()
    if not parts:
        return "Unnamed"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."


def _month(v: Any) -> str:
    return fmt_dt(v)[:7]


def sectionize(text: str, size: int = SECTION_CHARS, cap: int = DOC_MAX_CHARS) -> list[str]:
    """Split long text into '## Section N' blocks on paragraph boundaries. Legal wording is kept as written
    (scrubbed of personal identifiers only, never summarised or clipped except by the overall cap)."""
    body = scrub((text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    truncated = len(body) > cap
    body = body[:cap]
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    sections: list[str] = []
    cur = ""
    for p in paras:
        while len(p) > size:                         # an over-long paragraph is cut at a space where possible
            cut = p.rfind(" ", 0, size) or size
            cut = cut if cut > size // 2 else size
            if cur:
                sections.append(cur)
                cur = ""
            sections.append(p[:cut].strip())
            p = p[cut:].strip()
        if cur and len(cur) + len(p) + 2 > size:
            sections.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        sections.append(cur)
    out = [f"## Section {i}\n{sec}" for i, sec in enumerate(sections, 1)]
    if truncated:
        out.append("## Note\nThe document continues beyond the indexed limit; open the original for the remainder.")
    return out


def _with_sections(lines: list[str], sections: list[str]) -> list[str]:
    """Blank line before every section so chunk_markdown splits on section boundaries."""
    for sec in sections:
        lines += ["", sec]
    return lines


def digest_card(stype: str, sid: str, module: str, title: str, as_of: Optional[datetime], tags: list[str],
                sections: list[tuple[str, list[str]]], *, importance: float = 0.5, access_key: Optional[str] = None,
                edges: Optional[list[Edge]] = None, deep_link: str = "", extra: Optional[dict] = None,
                visibility: Optional[str] = None, required_roles: Optional[list[str]] = None) -> Card:
    lines = [f"# {title}", ""]
    for head, body in sections:
        lines.append(f"## {head}")
        lines += body if body else ["- None."]
        lines.append("")
    md = frontmatter(stype, sid, module, as_of, [stype, *tags], extra) + "\n".join(lines).rstrip() + "\n"
    return Card(stype, sid, module, title, md, as_of, [stype, *tags], importance, {"deep_link": deep_link} if deep_link else {},
                edges or [], access_key=access_key, visibility=visibility, required_roles=required_roles)


# ═══ Compliance (module compliance; role-tagged compliance/legal/risk + admins) ═══════════════════════════════════

COMPLIANCE_DOC_FIELDS = ("id", "title", "document_type", "mime_type", "contract_id", "ocr_text", "financial_summary", "tags",
                         "version", "is_confidential", "created_at", "updated_at")
COMPLIANCE_OBLIGATION_FIELDS = ("id", "category", "title", "description", "regulatory_reference", "frequency", "due_date", "status",
                                "responsible_department", "evidence_required", "notes", "updated_at")
CIPC_FIELDS = ("id", "filing_type", "financial_year_end", "status", "due_date", "filed_date", "fee_amount", "fee_paid",
               "notes", "updated_at")
TAX_RETURN_FIELDS = ("id", "tax_type", "period_start", "period_end", "status", "amount_payable", "amount_refund",
                     "submission_date", "sars_assessment_date", "payment_date", "notes", "updated_at")
TAX_REG_FIELDS = ("id", "tax_type", "status", "registered_date", "last_filed", "next_due", "notes", "updated_at")
EMP201_FIELDS = ("id", "period", "status", "due_date", "employee_count", "gross_remuneration", "paye", "uif_employee",
                 "uif_employer", "sdl", "total_liability", "rates_verified", "filed_at", "ts")
BREACH_FIELDS = ("id", "title", "category", "severity", "status", "identified_date", "reported_date", "resolved_date", "description",
                 "root_cause", "corrective_action", "icasa_notified", "popi_commission_notified", "financial_impact", "updated_at")


def compliance_document_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("compliance_document", COMPLIANCE_DOC_FIELDS))
    did = str(r["id"])
    lines = [f"# Compliance document: {_s(r.get('title'), 160)}", "",
             f"- Type: {r.get('document_type') or 'other'}",
             f"- Version: {r.get('version') or 'n/a'}",
             f"- Confidential: {_yn(r.get('is_confidential'))}",
             f"- Added: {_d(r.get('created_at'))}"]
    if r.get("tags"):
        lines.append(f"- Tags: {_s(r['tags'], 160)}")
    if r.get("contract_id"):
        lines.append(f"- Linked contract record: {r['contract_id']}")
    if r.get("financial_summary"):
        lines += ["", "## Financial summary", _s(r["financial_summary"], 800)]
    text = r.get("ocr_text")
    _with_sections(lines, sectionize(text) if text else ["## Text\nNo extracted text is available for this document."])
    md = frontmatter("compliance_document", did, "compliance", as_of,
                     ["compliance", "document", str(r.get("document_type") or "other").lower()], {"document_id": did}) + "\n".join(lines) + "\n"
    imp = IMPORTANCE["high"] if str(r.get("document_type") or "") in ("policy", "contract") else IMPORTANCE["normal"]
    return Card("compliance_document", did, "compliance", f"Compliance document: {_s(r.get('title'), 100)}", md, as_of,
                ["compliance", "document"], imp, {"deep_link": f"/dashboard/compliance?document={did}"})


def compliance_obligation_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("compliance_obligation", COMPLIANCE_OBLIGATION_FIELDS))
    oid = str(r["id"])
    lines = [f"# Obligation: {_s(r.get('title'), 160)}", "",
             f"- Category: {r.get('category')}", f"- Status: {r.get('status')}", f"- Frequency: {r.get('frequency') or 'n/a'}",
             f"- Due: {_d(r.get('due_date'))}", f"- Department: {_s(r.get('responsible_department'), 80) or 'unassigned'}"]
    if r.get("regulatory_reference"):
        lines.append(f"- Regulatory reference: {_s(r['regulatory_reference'], 200)}")
    for key, head in (("description", "Description"), ("evidence_required", "Evidence required"), ("notes", "Notes")):
        if r.get(key):
            lines += ["", f"## {head}", _s(r[key], 900)]
    md = frontmatter("compliance_obligation", oid, "compliance", as_of, ["compliance", "obligation", str(r.get("status") or "").lower()],
                     {"obligation_id": oid}) + "\n".join(lines) + "\n"
    late = str(r.get("status") or "").lower() in ("non_compliant", "overdue", "at_risk")
    return Card("compliance_obligation", oid, "compliance", f"Obligation: {_s(r.get('title'), 100)}", md, as_of, ["compliance", "obligation"],
                IMPORTANCE["high"] if late else IMPORTANCE["normal"], {"deep_link": f"/dashboard/compliance?obligation={oid}"})


def cipc_filing_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("cipc_filing", CIPC_FIELDS))
    fid = str(r["id"])
    lines = [f"# CIPC filing: {_s(r.get('filing_type'), 100)}", "",
             f"- Financial year end: {_d(r.get('financial_year_end'))}", f"- Status: {r.get('status')}",
             f"- Due: {_d(r.get('due_date'))}", f"- Filed: {_d(r.get('filed_date'))}",
             f"- Fee: {money(r.get('fee_amount'))} ({'paid' if r.get('fee_paid') else 'unpaid'})"]
    if r.get("notes"):
        lines += ["", "## Notes", _s(r["notes"], 600)]
    md = frontmatter("cipc_filing", fid, "compliance", as_of, ["compliance", "filing", "cipc", str(r.get("status") or "").lower()],
                     {"filing_id": fid}) + "\n".join(lines) + "\n"
    return Card("cipc_filing", fid, "compliance", f"CIPC filing: {_s(r.get('filing_type'), 80)}", md, as_of, ["compliance", "cipc"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/compliance?cipc={fid}"})


def tax_return_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("tax_return", TAX_RETURN_FIELDS))
    rid = str(r["id"])
    lines = [f"# Tax return: {r.get('tax_type')} {_d(r.get('period_start'))} to {_d(r.get('period_end'))}", "",
             f"- Status: {r.get('status')}", f"- Amount payable: {money(r.get('amount_payable'))}",
             f"- Refund due: {money(r.get('amount_refund'))}", f"- Submitted: {_d(r.get('submission_date'))}",
             f"- SARS assessment: {_d(r.get('sars_assessment_date'))}", f"- Paid: {_d(r.get('payment_date'))}"]
    if r.get("notes"):
        lines += ["", "## Notes", _s(r["notes"], 600)]
    md = frontmatter("tax_return", rid, "compliance", as_of, ["compliance", "tax", "filing", str(r.get("tax_type") or "").lower()],
                     {"filing_id": rid}) + "\n".join(lines) + "\n"
    return Card("tax_return", rid, "compliance", f"Tax return {r.get('tax_type')} {_month(r.get('period_end'))}", md, as_of,
                ["compliance", "tax"], IMPORTANCE["normal"], {"deep_link": f"/dashboard/compliance?tax_return={rid}"})


def tax_registration_card(row: dict, as_of: Optional[datetime]) -> Card:
    """Registration and SARS reference numbers are deliberately not read: they identify the taxpayer."""
    r = pick(row, allowed_fields("tax_registration", TAX_REG_FIELDS))
    rid = str(r["id"])
    lines = [f"# Tax registration: {r.get('tax_type')}", "", f"- Status: {r.get('status')}",
             f"- Registered: {_d(r.get('registered_date'))}", f"- Last filed: {_d(r.get('last_filed'))}", f"- Next due: {_d(r.get('next_due'))}"]
    if r.get("notes"):
        lines += ["", "## Notes", _s(r["notes"], 400)]
    md = frontmatter("tax_registration", rid, "compliance", as_of, ["compliance", "tax", str(r.get("tax_type") or "").lower()],
                     {"registration_id": rid}) + "\n".join(lines) + "\n"
    return Card("tax_registration", rid, "compliance", f"Tax registration: {r.get('tax_type')}", md, as_of, ["compliance", "tax"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/compliance?tax_registration={rid}"})


def emp201_card(row: dict, as_of: Optional[datetime]) -> Card:
    """Company-level payroll-tax totals for a period. PRN, receipt references, preparer and payroll-run ids are not read."""
    r = pick(row, allowed_fields("emp201", EMP201_FIELDS))
    eid = str(r["id"])
    lines = [f"# EMP201 {r.get('period')}", "", f"- Status: {r.get('status')}", f"- Due: {_d(r.get('due_date'))}",
             f"- Filed: {_d(r.get('filed_at'))}", f"- Employees: {_n(r.get('employee_count'))}",
             f"- Gross remuneration: {money(r.get('gross_remuneration'))}", f"- PAYE: {money(r.get('paye'))}",
             f"- UIF (employee + employer): {money(r.get('uif_employee'))} + {money(r.get('uif_employer'))}",
             f"- SDL: {money(r.get('sdl'))}", f"- Total liability: {money(r.get('total_liability'))}",
             f"- Statutory rates verified: {_yn(r.get('rates_verified'))}"]
    md = frontmatter("emp201", eid, "compliance", as_of, ["compliance", "emp201", "payroll_tax", str(r.get("status") or "").lower()],
                     {"period": r.get("period")}) + "\n".join(lines) + "\n"
    return Card("emp201", eid, "compliance", f"EMP201 {r.get('period')}", md, as_of, ["compliance", "emp201"], IMPORTANCE["normal"],
                {"deep_link": "/dashboard/compliance?tab=emp201"}, access_key="compliance.payroll_tax")


def breach_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("breach", BREACH_FIELDS))
    bid = str(r["id"])
    lines = [f"# Compliance breach: {_s(r.get('title'), 160)}", "",
             f"- Category: {r.get('category')}", f"- Severity: {r.get('severity') or 'unrated'}", f"- Status: {r.get('status')}",
             f"- Identified: {_d(r.get('identified_date'))}", f"- Reported: {_d(r.get('reported_date'))}", f"- Resolved: {_d(r.get('resolved_date'))}",
             f"- Regulator (ICASA) notified: {_yn(r.get('icasa_notified'))}",
             f"- Information Regulator notified: {_yn(r.get('popi_commission_notified'))}",
             f"- Financial impact: {money(r.get('financial_impact'))}"]
    for key, head in (("description", "Description"), ("root_cause", "Root cause"), ("corrective_action", "Corrective action")):
        if r.get(key):
            lines += ["", f"## {head}", _s(r[key], 900)]
    md = frontmatter("compliance_breach", bid, "compliance", as_of, ["compliance", "breach", str(r.get("severity") or "").lower()],
                     {"breach_id": bid}) + "\n".join(lines) + "\n"
    sev = str(r.get("severity") or "").lower()
    return Card("compliance_breach", bid, "compliance", f"Compliance breach: {_s(r.get('title'), 100)}", md, as_of, ["compliance", "breach"],
                IMPORTANCE["critical"] if sev in ("critical", "high") else IMPORTANCE["high"], {"deep_link": f"/dashboard/compliance?breach={bid}"})


def consent_digest_card(rows: list[dict], as_of: Optional[datetime]) -> Card:
    """POPIA consent register digest per purpose. Data-subject names/ids are never read; only counts."""
    lines = []
    for r in sorted(rows, key=lambda r: str(r.get("purpose"))):
        lines.append(f"- {_s(r.get('purpose'), 120) or 'unspecified purpose'}: {_n(r.get('total'))} records, {_n(r.get('granted'))} granted, "
                     f"{_n(r.get('withdrawn'))} withdrawn, {_n(r.get('expired'))} expired")
    tot = sum(_n(r.get("total")) for r in rows)
    return digest_card("consent_digest", "popia-consents", "compliance", "POPIA consent register digest", as_of, ["compliance", "popia", "consent"],
                       [("Records by purpose", lines), ("Totals", [f"- {tot} consent records across {len(rows)} purposes."])],
                       deep_link="/dashboard/compliance?tab=popi")


# ═══ HR (module hr; role-tagged hr/hr_manager/hr_admin + admins; org facts only) ═══════════════════════════════════

TRAINING_FIELDS = ("id", "title", "description", "category", "duration_hours", "mandatory", "status", "updated_at")
COMPANY_KPI_FIELDS = ("id", "fiscal_year", "sales_budget_zar", "sales_actual_zar", "cost_budget_zar", "cost_actual_zar", "profit_budget_zar",
                      "profit_actual_zar", "values_weight_pct", "values_description", "updated_at")


def hr_org_digest_card(rows: list[dict], as_of: Optional[datetime]) -> Card:
    """Headcount per department and role title for active staff. No names, no contact or identity data, no pay."""
    by_dept: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_dept[str(r.get("department") or "Unassigned")].append(r)
    sections = []
    for dept in sorted(by_dept):
        items = sorted(by_dept[dept], key=lambda r: str(r.get("job_title") or ""))
        total = sum(_n(r.get("headcount")) for r in items)
        body = [f"- {_s(r.get('job_title'), 80) or 'Untitled role'}: {_n(r.get('headcount'))}" for r in items]
        sections.append((f"{_s(dept, 80)} ({total} active)", body))
    total_all = sum(_n(r.get("headcount")) for r in rows)
    return digest_card("hr_org", "org-structure", "hr", "Organisation structure: departments and role titles", as_of, ["hr", "org"],
                       [("Summary", [f"- {total_all} active staff across {len(by_dept)} departments."])] + sections,
                       deep_link="/dashboard/hr")


def training_course_card(row: dict, stats: dict, as_of: Optional[datetime]) -> Card:
    """Course facts plus aggregate uptake. Individual enrolments, progress and scores are never read."""
    r = pick(row, allowed_fields("training_course", TRAINING_FIELDS))
    cid = str(r["id"])
    enrolled, done = _n(stats.get("enrolled")), _n(stats.get("completed"))
    lines = [f"# Training course: {_s(r.get('title'), 160)}", "", f"- Category: {r.get('category') or 'general'}",
             f"- Duration: {_f(r.get('duration_hours'))} hours", f"- Mandatory: {_yn(r.get('mandatory'))}", f"- Status: {r.get('status') or 'active'}",
             f"- Enrolled: {enrolled}; completed: {done}"]
    if r.get("description"):
        lines += ["", "## Description", _s(r["description"], 800)]
    md = frontmatter("training_course", cid, "hr", as_of, ["hr", "training", str(r.get("category") or "general").lower()],
                     {"course_id": cid}) + "\n".join(lines) + "\n"
    return Card("training_course", cid, "hr", f"Training course: {_s(r.get('title'), 100)}", md, as_of, ["hr", "training"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/hr?course={cid}"})


def company_kpi_card(row: dict, as_of: Optional[datetime]) -> Card:
    """Company-level objectives for a fiscal year (budget vs actual). Individual KPI sheets/reviews are not indexed."""
    r = pick(row, allowed_fields("company_kpi", COMPANY_KPI_FIELDS))
    kid = str(r["id"])
    lines = [f"# Company KPI objectives FY{r.get('fiscal_year')}", "",
             f"- Sales: budget {money(r.get('sales_budget_zar'))}, actual {money(r.get('sales_actual_zar'))}",
             f"- Cost: budget {money(r.get('cost_budget_zar'))}, actual {money(r.get('cost_actual_zar'))}",
             f"- Profit: budget {money(r.get('profit_budget_zar'))}, actual {money(r.get('profit_actual_zar'))}",
             f"- Weight of company values in individual scorecards: {_f(r.get('values_weight_pct'))}%"]
    if r.get("values_description"):
        lines += ["", "## Company values", _s(r["values_description"], 800)]
    md = frontmatter("company_kpi", kid, "hr", as_of, ["hr", "kpi", "objectives"], {"fiscal_year": r.get("fiscal_year")}) + "\n".join(lines) + "\n"
    return Card("company_kpi", kid, "hr", f"Company KPI objectives FY{r.get('fiscal_year')}", md, as_of, ["hr", "kpi"], IMPORTANCE["high"],
                {"deep_link": "/dashboard/hr?tab=kpi"})


# ═══ Network / IoT / RICA (module network; tenant-visible operational context) ════════════════════════════════════

NETWORK_SERVICE_FIELDS = ("id", "customer_id", "service_reference", "description", "status", "technology", "fno_provider",
                          "download_speed_mbps", "upload_speed_mbps", "speed_profile_name", "city", "province", "activated_at",
                          "suspended_at", "terminated_at", "updated_at")


def network_service_card(row: dict, as_of: Optional[datetime]) -> Card:
    """Street address, GPS, FNO order/account ids and the ONT serial are not read."""
    r = pick(row, allowed_fields("network_service", NETWORK_SERVICE_FIELDS))
    sid = str(r["id"])
    ref = _s(r.get("service_reference"), 60)
    lines = [f"# Network service {ref or sid[:8]}", "", f"- Status: {r.get('status')}", f"- Technology: {r.get('technology') or 'n/a'}",
             f"- FNO provider: {r.get('fno_provider') or 'n/a'}",
             f"- Speed: {_f(r.get('download_speed_mbps'), 0)}/{_f(r.get('upload_speed_mbps'), 0)} Mbps"
             + (f" (profile {_s(r.get('speed_profile_name'), 60)})" if r.get("speed_profile_name") else ""),
             f"- Location: {_s(r.get('city'), 60) or 'n/a'}, {_s(r.get('province'), 60) or 'n/a'}",
             f"- Activated: {_d(r.get('activated_at'))}"]
    if r.get("suspended_at"):
        lines.append(f"- Suspended: {_d(r['suspended_at'])}")
    if r.get("terminated_at"):
        lines.append(f"- Terminated: {_d(r['terminated_at'])}")
    edges = []
    if r.get("customer_id"):
        lines.append(f"- Customer: {link('customer', str(r['customer_id']))}")
        edges.append(Edge("network_service", sid, "customer", str(r["customer_id"]), "serves", 1.0, as_of))
    if r.get("description"):
        lines += ["", "## Notes", _s(r["description"], 400)]
    md = frontmatter("network_service", sid, "network", as_of, ["network", "service", str(r.get("status") or "").lower()],
                     {"service_id": sid}) + "\n".join(lines) + "\n"
    return Card("network_service", sid, "network", f"Network service {ref or sid[:8]}", md, as_of, ["network", "service"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/network?service={sid}"}, edges)


def sla_digest_card(month: str, breaches: list[dict], fno: list[dict], as_of: Optional[datetime]) -> Card:
    lines = [f"- {_s(r.get('metric_type'), 60)} / {r.get('severity') or 'n/a'}: {_n(r.get('breaches'))} breaches "
             f"({_n(r.get('resolved'))} resolved), avg duration {_f((r.get('avg_seconds') or 0) / 60.0)} min"
             for r in sorted(breaches, key=lambda r: (str(r.get("metric_type")), str(r.get("severity"))))]
    fl = [f"- {_s(r.get('fno_provider'), 60)} / {_s(r.get('metric'), 60)}: {_n(r.get('breach_count'))} of {_n(r.get('measurements'))} "
          f"measurements breached, penalties {money(r.get('penalty_zar'))}"
          for r in sorted(fno, key=lambda r: (str(r.get("fno_provider")), str(r.get("metric"))))]
    return digest_card("sla_digest", month, "network", f"SLA breach digest {month}", as_of, ["network", "sla", month],
                       [("Customer-service SLA breaches", lines), ("FNO SLA measurements", fl)], deep_link="/dashboard/network?tab=sla",
                       importance=IMPORTANCE["high"] if any(_n(r.get("breaches")) for r in breaches) else IMPORTANCE["normal"])


def incident_digest_card(month: str, rows: list[dict], as_of: Optional[datetime]) -> Card:
    lines = [f"- {_s(r.get('trigger_type'), 60)} / {r.get('severity') or 'n/a'}: {_n(r.get('notifications'))} notifications "
             f"({_n(r.get('failed'))} failed to send)" for r in sorted(rows, key=lambda r: (str(r.get("trigger_type")), str(r.get("severity"))))]
    return digest_card("incident_digest", month, "network", f"Network incident and notification digest {month}", as_of,
                       ["network", "incident", month], [("Notifications raised by trigger", lines)], deep_link="/dashboard/network?tab=alerts")


def fleet_digest_card(net: list[dict], iot: list[dict], as_of: Optional[datetime]) -> Card:
    """Counts by type/manufacturer/model/status. Serial numbers, MACs, IPs, firmware strings and credentials are not read."""
    nl = [f"- {_s(r.get('device_type'), 40)} {_s(r.get('manufacturer'), 40)} {_s(r.get('model'), 40)} [{r.get('status')}]: {_n(r.get('devices'))}"
          f" ({_n(r.get('silent_24h'))} not seen in 24h)" for r in sorted(net, key=lambda r: tuple(str(r.get(k)) for k in ("device_type", "manufacturer", "model", "status")))]
    il = [f"- {_s(r.get('device_type'), 40)} [{r.get('status')}]: {_n(r.get('devices'))} ({_n(r.get('silent_24h'))} not seen in 24h)"
          for r in sorted(iot, key=lambda r: (str(r.get("device_type")), str(r.get("status"))))]
    return digest_card("fleet_digest", "devices", "network", "Network and IoT device fleet digest", as_of, ["network", "iot", "fleet"],
                       [("Network devices (CPE/ONT/routers)", nl), ("IoT devices", il)], deep_link="/dashboard/network?tab=devices")


def rica_digest_card(month: str, rows: list[dict], flows: list[dict], as_of: Optional[datetime]) -> Card:
    """RICA verification outcomes by month. No ID numbers, names, addresses, job ids or response payloads."""
    lines = [f"- {_s(r.get('verification_type'), 40) or 'verification'} [{r.get('status')}]: {_n(r.get('verifications'))}"
             for r in sorted(rows, key=lambda r: (str(r.get("verification_type")), str(r.get("status"))))]
    fl = [f"- [{r.get('status')}] ({_s(r.get('trigger_source'), 40) or 'n/a'}): {_n(r.get('flows'))}"
          for r in sorted(flows, key=lambda r: (str(r.get("status")), str(r.get("trigger_source"))))]
    return digest_card("rica_digest", month, "network", f"RICA registration digest {month}", as_of, ["network", "rica", month],
                       [("Verification jobs", lines), ("Customer RICA flows", fl)], deep_link="/dashboard/compliance?tab=rica")


# ═══ Inventory (module inventory) ═══════════════════════════════════════════════════════════════════════════════

PRODUCT_FIELDS = ("id", "sku", "name", "description", "unit_of_measure", "rrp", "is_active", "is_serialized", "category_name",
                  "service_type_name", "range_name", "updated_at")
PACKAGE_FIELDS = ("id", "sku", "name", "description", "package_type", "rrp", "is_active", "is_sellable_standalone", "version",
                  "effective_from", "effective_to", "category_name", "service_type_name", "updated_at")
PO_FIELDS = ("id", "supplier_id", "supplier_name", "warehouse_name", "po_number", "status", "subtotal_zar", "tax_zar", "total_zar",
             "order_date", "expected_delivery", "received_at", "currency", "approval_mode", "rejection_reason", "cancelled_at", "notes", "updated_at")
SUPPLIER_FIELDS = ("id", "code", "name", "payment_terms", "lead_time_days", "is_active", "updated_at")


def product_card(row: dict, as_of: Optional[datetime]) -> Optional[Card]:
    """Catalogue card. Cost price, markup, barcode, weight and preferred supplier are not read (margin is finance-only)."""
    r = pick(row, allowed_fields("product", PRODUCT_FIELDS))
    pid = str(r["id"])
    lines = [f"# Product: {_s(r.get('name'), 160)}", "", f"- SKU: {_s(r.get('sku'), 60)}", f"- Category: {_s(r.get('category_name'), 80) or 'uncategorised'}",
             f"- Service type: {_s(r.get('service_type_name'), 80) or 'n/a'}", f"- Range: {_s(r.get('range_name'), 80) or 'n/a'}",
             f"- Recommended retail price: {money(r.get('rrp'))}", f"- Unit: {r.get('unit_of_measure') or 'each'}",
             f"- Serialised: {_yn(r.get('is_serialized'))}", f"- Active: {_yn(r.get('is_active'))}"]
    if r.get("description"):
        lines += ["", "## Description", _s(r["description"], 800)]
    md = frontmatter("product", pid, "inventory", as_of, ["inventory", "product", "active" if r.get("is_active") else "inactive"],
                     {"product_id": pid, "sku": r.get("sku")}) + "\n".join(lines) + "\n"
    return Card("product", pid, "inventory", f"Product: {_s(r.get('name'), 100)}", md, as_of, ["inventory", "product"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/inventory?product={pid}"})


def package_card(row: dict, items: list[dict], as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("package", PACKAGE_FIELDS))
    pid = str(r["id"])
    lines = [f"# Package: {_s(r.get('name'), 160)}", "", f"- SKU: {_s(r.get('sku'), 60)}", f"- Type: {r.get('package_type') or 'n/a'}",
             f"- Category: {_s(r.get('category_name'), 80) or 'n/a'}", f"- Service type: {_s(r.get('service_type_name'), 80) or 'n/a'}",
             f"- Recommended retail price: {money(r.get('rrp'))}", f"- Active: {_yn(r.get('is_active'))}",
             f"- Sellable on its own: {_yn(r.get('is_sellable_standalone'))}", f"- Effective: {_d(r.get('effective_from'))} to {_d(r.get('effective_to'))}",
             "", "## Contents"]
    edges = []
    for it in sorted(items, key=lambda i: (_n(i.get("sort_order")), str(i.get("product_id")))):
        lines.append(f"- {_n(it.get('quantity'))} x {_s(it.get('product_name'), 100)} {link('product', str(it['product_id']))}"
                     + ("" if it.get("is_required") else " (optional)"))
        edges.append(Edge("package", pid, "product", str(it["product_id"]), "contains", 1.0, as_of))
    if not items:
        lines.append("- No items.")
    if r.get("description"):
        lines += ["", "## Description", _s(r["description"], 600)]
    md = frontmatter("package", pid, "inventory", as_of, ["inventory", "package"], {"package_id": pid}) + "\n".join(lines) + "\n"
    return Card("package", pid, "inventory", f"Package: {_s(r.get('name'), 100)}", md, as_of, ["inventory", "package"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/inventory?package={pid}"}, edges)


def warehouse_stock_card(wh: dict, summary: dict, low: list[dict], as_of: Optional[datetime]) -> Card:
    wid = str(wh["id"])
    lines = [f"- Products stocked: {_n(summary.get('products'))}", f"- Stock on hand (units): {_n(summary.get('soh'))}",
             f"- In transit: {_n(summary.get('sit'))}", f"- Allocated: {_n(summary.get('allocated'))}",
             f"- Products at or below reorder point: {_n(summary.get('below_reorder'))}"]
    ll = [f"- {_s(r.get('name'), 80)} ({_s(r.get('sku'), 40)}): on hand {_n(r.get('soh'))}, reorder point {_n(r.get('reorder_point'))} "
          f"{link('product', str(r['product_id']))}" for r in sorted(low, key=lambda r: (_n(r.get("soh")) - _n(r.get("reorder_point")), str(r.get("product_id"))))[:15]]
    edges = [Edge("stock_digest", wid, "product", str(r["product_id"]), "low_stock", 0.5, as_of) for r in low[:15]]
    return digest_card("stock_digest", wid, "inventory", f"Stock levels: {_s(wh.get('name'), 80)}", as_of, ["inventory", "stock", "warehouse"],
                       [("Warehouse", [f"- {_s(wh.get('name'), 80)} ({_s(wh.get('code'), 20)}), {'external/partner' if wh.get('is_external') else 'own'} location"]),
                        ("Levels (as of this card)", lines), ("Lowest stock vs reorder point", ll)],
                       importance=IMPORTANCE["high"] if _n(summary.get("below_reorder")) else IMPORTANCE["normal"],
                       deep_link=f"/dashboard/inventory?warehouse={wid}", edges=edges)


def stock_movement_digest_card(month: str, rows: list[dict], as_of: Optional[datetime]) -> Card:
    lines = [f"- {_s(r.get('movement_type'), 40)}: {_n(r.get('movements'))} movements, {_n(r.get('units'))} units"
             for r in sorted(rows, key=lambda r: str(r.get("movement_type")))]
    return digest_card("stock_movement_digest", month, "inventory", f"Stock movements {month}", as_of, ["inventory", "stock", "movements", month],
                       [("Movements by type", lines)], deep_link="/dashboard/inventory?tab=movements")


def purchase_order_card(row: dict, items: list[dict], as_of: Optional[datetime]) -> Card:
    """Supplier contact details, approver/creator ids, e-mail send metadata and approval hashes are not read."""
    r = pick(row, allowed_fields("purchase_order", PO_FIELDS))
    pid = str(r["id"])
    lines = [f"# Purchase order {_s(r.get('po_number'), 40)}", "", f"- Status: {r.get('status')}",
             f"- Supplier: {_s(r.get('supplier_name'), 100)}" + (f" {link('supplier', str(r['supplier_id']))}" if r.get("supplier_id") else ""),
             f"- Deliver to: {_s(r.get('warehouse_name'), 80) or 'n/a'}", f"- Ordered: {_d(r.get('order_date'))}",
             f"- Expected delivery: {_d(r.get('expected_delivery'))}", f"- Received: {_d(r.get('received_at'))}",
             f"- Total: {money(r.get('total_zar'))} (excl. tax {money(r.get('subtotal_zar'))}, tax {money(r.get('tax_zar'))}) {r.get('currency') or 'ZAR'}",
             f"- Approval mode: {r.get('approval_mode') or 'n/a'}"]
    if r.get("cancelled_at"):
        lines.append(f"- Cancelled: {_d(r['cancelled_at'])}")
    if r.get("rejection_reason"):
        lines.append(f"- Rejection reason: {_s(r['rejection_reason'], 300)}")
    lines += ["", "## Items"]
    edges = []
    if r.get("supplier_id"):
        edges.append(Edge("purchase_order", pid, "supplier", str(r["supplier_id"]), "ordered_from", 1.0, as_of))
    for it in sorted(items, key=lambda i: (str(i.get("product_name")), str(i.get("product_id")))):
        lines.append(f"- {_s(it.get('product_name'), 100)}: ordered {_n(it.get('quantity_ordered'))}, received {_n(it.get('quantity_received'))} "
                     f"at {money(it.get('unit_cost_zar'))} {link('product', str(it['product_id']))}")
        edges.append(Edge("purchase_order", pid, "product", str(it["product_id"]), "orders", 1.0, as_of))
    if not items:
        lines.append("- No lines.")
    if r.get("notes"):
        lines += ["", "## Notes", _s(r["notes"], 400)]
    md = frontmatter("purchase_order", pid, "inventory", as_of, ["inventory", "purchase_order", str(r.get("status") or "").lower()],
                     {"po_number": r.get("po_number")}) + "\n".join(lines) + "\n"
    return Card("purchase_order", pid, "inventory", f"Purchase order {_s(r.get('po_number'), 40)}", md, as_of, ["inventory", "purchase_order"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/inventory?po={pid}"}, edges, access_key="inventory.procurement")


def supplier_card(row: dict, stats: dict, as_of: Optional[datetime]) -> Card:
    """Contact person, e-mail, phone, address, tax id, spend limit and notes (may hold bank details) are not read."""
    r = pick(row, allowed_fields("supplier", SUPPLIER_FIELDS))
    sid = str(r["id"])
    lines = [f"# Supplier: {_s(r.get('name'), 160)}", "", f"- Code: {_s(r.get('code'), 40)}", f"- Active: {_yn(r.get('is_active'))}",
             f"- Payment terms: {_s(r.get('payment_terms'), 100) or 'n/a'}", f"- Lead time: {_n(r.get('lead_time_days'))} days",
             f"- Purchase orders: {_n(stats.get('pos'))} ({_n(stats.get('open_pos'))} open), total ordered {money(stats.get('total_zar'))}"]
    md = frontmatter("supplier", sid, "inventory", as_of, ["inventory", "supplier"], {"supplier_id": sid}) + "\n".join(lines) + "\n"
    return Card("supplier", sid, "inventory", f"Supplier: {_s(r.get('name'), 100)}", md, as_of, ["inventory", "supplier"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/inventory?supplier={sid}"}, access_key="inventory.procurement")


# ═══ Finance & billing level cards (role-tagged finance / billing) ════════════════════════════════════════════════

INVOICE_FIELDS = ("id", "customer_id", "subscription_id", "number", "status", "subtotal_zar", "vat_zar", "total_zar", "amount_paid_zar",
                  "due_date", "billing_period_start", "billing_period_end", "credit_note_of", "created_at", "updated_at")
SUBSCRIPTION_FIELDS = ("id", "customer_id", "plan", "segment", "status", "billing_interval", "base_price_zar", "quantity",
                       "current_period_start", "current_period_end", "trial_ends_at", "cancelled_at", "cancel_at_period_end", "created_at", "updated_at")
ARRANGEMENT_FIELDS = ("id", "customer_id", "total_owed_zar", "installment_zar", "installments_count", "installments_paid", "status",
                      "next_due_date", "created_at", "updated_at")


def invoice_card(row: dict, lines_: list[dict], as_of: Optional[datetime]) -> Card:
    """Customer-safe: number, amounts, dates, line items. Free-text notes, payment refs and Paystack data are not read."""
    r = pick(row, allowed_fields("invoice", INVOICE_FIELDS))
    iid = str(r["id"])
    outstanding = (r.get("total_zar") or 0) - (r.get("amount_paid_zar") or 0)
    lines = [f"# Invoice {_s(r.get('number'), 40)}", "", f"- Status: {r.get('status')}", f"- Total: {money(r.get('total_zar'))} "
             f"(subtotal {money(r.get('subtotal_zar'))}, VAT {money(r.get('vat_zar'))})", f"- Paid: {money(r.get('amount_paid_zar'))}; outstanding {money(outstanding)}",
             f"- Due: {_d(r.get('due_date'))}", f"- Billing period: {_d(r.get('billing_period_start'))} to {_d(r.get('billing_period_end'))}",
             f"- Issued: {_d(r.get('created_at'))}"]
    edges = []
    if r.get("customer_id"):
        lines.append(f"- Customer: {link('customer', str(r['customer_id']))}")
        edges.append(Edge("invoice", iid, "customer", str(r["customer_id"]), "billed_to", 1.0, as_of))
    if r.get("subscription_id"):
        lines.append(f"- Subscription: {link('subscription', str(r['subscription_id']))}")
        edges.append(Edge("invoice", iid, "subscription", str(r["subscription_id"]), "for_subscription", 1.0, as_of))
    if r.get("credit_note_of"):
        lines.append(f"- Credit note against {link('invoice', str(r['credit_note_of']))}")
        edges.append(Edge("invoice", iid, "invoice", str(r["credit_note_of"]), "credits", 1.0, as_of))
    lines += ["", "## Lines"]
    for ln in sorted(lines_, key=lambda l: (str(l.get("line_type")), str(l.get("product_name")), str(l.get("description")), str(l.get("id")))):
        lines.append(f"- {_s(ln.get('product_name') or ln.get('description'), 100)} x{_f(ln.get('quantity'), 0)}: {money(ln.get('total_zar'))}"
                     + (f" ({ln.get('line_type')})" if ln.get("line_type") else ""))
    if not lines_:
        lines.append("- No itemised lines.")
    md = frontmatter("invoice", iid, "billing", as_of, ["billing", "invoice", str(r.get("status") or "").lower()],
                     {"invoice_id": iid, "customer_id": r.get("customer_id")}) + "\n".join(lines) + "\n"
    overdue = str(r.get("status") or "").lower() == "overdue"
    return Card("invoice", iid, "billing", f"Invoice {_s(r.get('number'), 40)}", md, as_of, ["billing", "invoice"],
                IMPORTANCE["high"] if overdue else IMPORTANCE["normal"], {"deep_link": f"/dashboard/billing?invoice={iid}"}, edges)


def subscription_card(row: dict, as_of: Optional[datetime]) -> Card:
    """Plan and period facts only; Paystack codes/tokens and metadata are not read."""
    r = pick(row, allowed_fields("subscription", SUBSCRIPTION_FIELDS))
    sid = str(r["id"])
    lines = [f"# Subscription: {_s(r.get('plan'), 100)}", "", f"- Status: {r.get('status')}", f"- Segment: {r.get('segment') or 'n/a'}",
             f"- Price: {money(r.get('base_price_zar'))} per {r.get('billing_interval') or 'month'} x {_n(r.get('quantity')) or 1}",
             f"- Current period: {_d(r.get('current_period_start'))} to {_d(r.get('current_period_end'))}", f"- Started: {_d(r.get('created_at'))}"]
    if r.get("trial_ends_at"):
        lines.append(f"- Trial ends: {_d(r['trial_ends_at'])}")
    if r.get("cancelled_at"):
        lines.append(f"- Cancelled: {_d(r['cancelled_at'])}")
    if r.get("cancel_at_period_end"):
        lines.append("- Set to cancel at period end.")
    edges = []
    if r.get("customer_id"):
        lines.append(f"- Customer: {link('customer', str(r['customer_id']))}")
        edges.append(Edge("subscription", sid, "customer", str(r["customer_id"]), "owned_by", 1.0, as_of))
    md = frontmatter("subscription", sid, "billing", as_of, ["billing", "subscription", str(r.get("status") or "").lower()],
                     {"subscription_id": sid}) + "\n".join(lines) + "\n"
    return Card("subscription", sid, "billing", f"Subscription: {_s(r.get('plan'), 80)}", md, as_of, ["billing", "subscription"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/billing?subscription={sid}"}, edges)


def payment_arrangement_card(row: dict, as_of: Optional[datetime]) -> Card:
    r = pick(row, allowed_fields("payment_arrangement", ARRANGEMENT_FIELDS))
    aid = str(r["id"])
    lines = [f"# Payment arrangement", "", f"- Status: {r.get('status')}", f"- Total owed: {money(r.get('total_owed_zar'))}",
             f"- Instalment: {money(r.get('installment_zar'))} x {_n(r.get('installments_count'))} ({_n(r.get('installments_paid'))} paid)",
             f"- Next due: {_d(r.get('next_due_date'))}", f"- Agreed: {_d(r.get('created_at'))}"]
    edges = []
    if r.get("customer_id"):
        lines.append(f"- Customer: {link('customer', str(r['customer_id']))}")
        edges.append(Edge("payment_arrangement", aid, "customer", str(r["customer_id"]), "arranged_for", 1.0, as_of))
    md = frontmatter("payment_arrangement", aid, "billing", as_of, ["billing", "arrangement", "collections", str(r.get("status") or "").lower()],
                     {"arrangement_id": aid}) + "\n".join(lines) + "\n"
    return Card("payment_arrangement", aid, "billing", "Payment arrangement", md, as_of, ["billing", "arrangement"], IMPORTANCE["high"],
                {"deep_link": f"/dashboard/billing?arrangement={aid}"}, edges)


def dunning_digest_card(month: str, rows: list[dict], as_of: Optional[datetime]) -> Card:
    lines = [f"- {_s(r.get('action_type'), 40)} step {_n(r.get('step'))}: {_n(r.get('actions'))} actions, {_n(r.get('executed'))} executed, "
             f"{_n(r.get('failed'))} with errors" for r in sorted(rows, key=lambda r: (str(r.get("action_type")), _n(r.get("step"))))]
    return digest_card("dunning_digest", month, "billing", f"Dunning and collections digest {month}", as_of, ["billing", "dunning", "collections", month],
                       [("Actions", lines)], deep_link="/dashboard/billing?tab=collections")


def chart_of_accounts_card(rows: list[dict], as_of: Optional[datetime]) -> Card:
    lines = [f"- {_s(r.get('code'), 30)}: {_s(r.get('name'), 120)}" for r in sorted(rows, key=lambda r: str(r.get("code")))]
    return digest_card("chart_of_accounts", "chart", "finance", "Chart of accounts", as_of, ["finance", "accounts"],
                       [("Accounts", lines)], importance=IMPORTANCE["high"], deep_link="/dashboard/finance?tab=accounts")


def journal_digest_card(month: str, summary: dict, groups: list[dict], top: list[dict], as_of: Optional[datetime]) -> Card:
    """Posted journals for a month grouped by account group (first digit of the code) and top accounts."""
    g = [f"- Group {_s(r.get('grp'), 4)}xxx: debit {money(r.get('debit'))}, credit {money(r.get('credit'))}, {_n(r.get('lines'))} lines"
         for r in sorted(groups, key=lambda r: str(r.get("grp")))]
    t = [f"- {_s(r.get('account_code'), 30)} {_s(r.get('account_name'), 80)}: debit {money(r.get('debit'))}, credit {money(r.get('credit'))}"
         for r in sorted(top, key=lambda r: (-float(r.get("volume") or 0), str(r.get("account_code"))))[:12]]
    s = [f"- Posted entries: {_n(summary.get('posted'))}; unposted: {_n(summary.get('unposted'))}",
         f"- Posted debits {money(summary.get('debit'))}, credits {money(summary.get('credit'))}"]
    return digest_card("journal_digest", month, "finance", f"Journal digest {month}", as_of, ["finance", "journal", month],
                       [("Summary", s), ("By account group", g), ("Busiest accounts", t)], deep_link="/dashboard/finance?tab=journal")


# ═══ Call centre (module call_center; transcripts only with recorded consent) ═════════════════════════════════

CALL_FIELDS = ("id", "agent_name", "customer_id", "direction", "queue_name", "start_time", "end_time", "duration_seconds",
               "sentiment_score", "outcome", "notes", "recording_consent", "transcript", "has_transcript", "retention_ok", "updated_at")
TRANSCRIPT_OK = ("given", "not_required")


def call_session_card(row: dict, as_of: Optional[datetime]) -> Card:
    """Recording URLs, provider ids and phone numbers are never read. The transcript is scrubbed and only included
    when consent is given/not_required and the retention window has not passed; the live (partial) transcript is not used."""
    r = pick(row, allowed_fields("call_session", CALL_FIELDS))
    cid = str(r["id"])
    mins = _f((r.get("duration_seconds") or 0) / 60.0)
    lines = [f"# Call {_d(r.get('start_time'))} ({str(r.get('direction') or 'unknown').lower()})", "",
             f"- Agent: {_short_name(r.get('agent_name'))}", f"- Queue: {_s(r.get('queue_name'), 80) or 'n/a'}", f"- Duration: {mins} min",
             f"- Outcome: {r.get('outcome') or 'n/a'}", f"- Sentiment score: {_f(r.get('sentiment_score'), 2)}",
             f"- Recording consent: {r.get('recording_consent') or 'unknown'}"]
    edges = []
    if r.get("customer_id"):
        lines.append(f"- Customer: {link('customer', str(r['customer_id']))}")
        edges.append(Edge("call_session", cid, "customer", str(r["customer_id"]), "call_with", 1.0, as_of))
    if r.get("notes"):
        lines += ["", "## Agent notes", _s(r["notes"], 800)]
    consent = str(r.get("recording_consent") or "unknown").lower()
    if consent in TRANSCRIPT_OK and r.get("retention_ok", True) and r.get("transcript"):
        _with_sections(lines, sectionize(r["transcript"], cap=20000))
    elif r.get("transcript") or r.get("has_transcript"):
        lines +=["", "## Transcript", "Withheld: no recorded consent or retention period elapsed."]
    md = frontmatter("call_session", cid, "call_center", as_of, ["call_center", "call", str(r.get("outcome") or "unknown").lower()],
                     {"call_id": cid}) + "\n".join(lines) + "\n"
    return Card("call_session", cid, "call_center", f"Call {_d(r.get('start_time'))}", md, as_of, ["call_center", "call"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/call-center?call={cid}"}, edges)


def call_center_digest_card(queues: list[dict], agents: list[dict], months: list[dict], as_of: Optional[datetime]) -> Card:
    q = [f"- {_s(r.get('name'), 80)} ({str(r.get('direction') or '').lower()}, {r.get('routing_strategy') or 'n/a'}): status {r.get('status') or 'n/a'}, "
         f"queued {_n(r.get('queued_calls'))}, active {_n(r.get('active_calls'))}, avg wait {_n(r.get('avg_wait_seconds'))}s, abandoned {_n(r.get('abandoned_count'))}"
         for r in sorted(queues, key=lambda r: str(r.get("name")))]
    a = [f"- {_short_name(r.get('name'))}: {r.get('status') or 'n/a'}, CSAT {_f(r.get('csat_score'), 2)}, MTTR {_f(r.get('mttr_minutes'))} min, "
         f"sales today {_n(r.get('daily_sales'))}" for r in sorted(agents, key=lambda r: str(r.get("name")))]
    m = [f"- {r.get('month')} {str(r.get('direction') or '').lower()}: {_n(r.get('calls'))} calls, avg {_f((r.get('avg_seconds') or 0) / 60.0)} min, "
         f"avg sentiment {_f(r.get('avg_sentiment'), 2)}, {_n(r.get('resolved'))} resolved" for r in sorted(months, key=lambda r: (str(r.get("month")), str(r.get("direction"))))]
    return digest_card("call_center_digest", "performance", "call_center", "Call centre queue and agent performance", as_of, ["call_center", "performance"],
                       [("Queues", q), ("Agents", a), ("Monthly call volume", m)], deep_link="/dashboard/call-center")


# ═══ Support KB, lifecycle, retention, portal, marketing ═════════════════════════════════════════════════════════

def kb_article_card(row: dict, as_of: Optional[datetime]) -> Optional[Card]:
    if not row.get("is_published"):
        return None
    kid = str(row["id"])
    raw_tags = row.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [t for t in raw_tags.strip("{}").split(",") if t.strip()]
    tags = [str(t).strip('"') for t in raw_tags]
    lines = [f"# KB article: {_s(row.get('title'), 160)}", "", f"- Category: {_s(row.get('category'), 80) or 'general'}"]
    if tags:
        lines.append("- Tags: " + ", ".join(sorted(set(_s(t, 40) for t in tags))))
    _with_sections(lines, sectionize(row.get("content") or "", cap=20000))
    md = frontmatter("kb_article", kid, "support", as_of, ["support", "kb", *[t.lower() for t in tags][:6]], {"article_id": kid}) + "\n".join(lines) + "\n"
    return Card("kb_article", kid, "support", f"KB article: {_s(row.get('title'), 100)}", md, as_of, ["support", "kb"], IMPORTANCE["high"],
                {"deep_link": f"/dashboard/support?kb={kid}"})


def _params(p: Any) -> str:
    p = jsonish(p)
    if not isinstance(p, dict):
        return ""
    return ", ".join(f"{_s(k, 30)}={_s(v, 40)}" for k, v in sorted(p.items()) if isinstance(v, (str, int, float, bool)))[:300]


def journey_card(row: dict, as_of: Optional[datetime]) -> Card:
    jid = str(row["id"])
    shown, acc = _n(row.get("times_shown")), _n(row.get("times_accepted"))
    lines = [f"# Retention journey: {_s(row.get('name'), 120)}", "", f"- Status: {row.get('status')}", f"- Trigger: {_s(row.get('trigger_event'), 80)}",
             f"- Channel: {row.get('channel') or 'n/a'}", f"- Priority: {_n(row.get('priority'))}", f"- A/B testing: {_yn(row.get('ab_test_enabled'))}",
             f"- Triggered {_n(row.get('times_triggered'))}x, shown {shown}x, accepted {acc}x, rejected {_n(row.get('times_rejected'))}x "
             f"({100.0 * acc / shown:.1f}% acceptance)" if shown else f"- Triggered {_n(row.get('times_triggered'))}x, not yet shown.",
             f"- Revenue preserved: {money(row.get('revenue_preserved'))}"]
    edges = []
    for key, rel in (("offer_id", "uses_offer"), ("fallback_offer_id", "falls_back_to")):
        if row.get(key):
            lines.append(f"- {rel.replace('_', ' ').capitalize()}: {link('retention_offer', str(row[key]))}")
            edges.append(Edge("retention_journey", jid, "retention_offer", str(row[key]), rel, 1.0, as_of))
    if row.get("description"):
        lines += ["", "## Description", _s(row["description"], 600)]
    md = frontmatter("retention_journey", jid, "lifecycle", as_of, ["lifecycle", "journey", str(row.get("status") or "").lower()],
                     {"journey_id": jid}) + "\n".join(lines) + "\n"
    return Card("retention_journey", jid, "lifecycle", f"Retention journey: {_s(row.get('name'), 80)}", md, as_of, ["lifecycle", "journey"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/lifecycle?journey={jid}"}, edges)


def offer_card(row: dict, as_of: Optional[datetime]) -> Card:
    oid = str(row["id"])
    lines = [f"# Retention offer: {_s(row.get('name'), 120)}", "", f"- Type: {row.get('offer_type')}", f"- Status: {row.get('status')}",
             f"- Parameters: {_params(row.get('parameters')) or 'none'}", f"- Limit per customer: {_n(row.get('max_per_customer'))}; total cap: "
             f"{_n(row.get('max_total_redemptions')) or 'none'}", f"- Redeemed: {_n(row.get('total_redemptions'))}",
             f"- Estimated cost per use: {money(row.get('estimated_cost_per_use'))}"]
    if row.get("description"):
        lines += ["", "## Description", _s(row["description"], 600)]
    md = frontmatter("retention_offer", oid, "lifecycle", as_of, ["lifecycle", "offer", str(row.get("status") or "").lower()],
                     {"offer_id": oid}) + "\n".join(lines) + "\n"
    return Card("retention_offer", oid, "lifecycle", f"Retention offer: {_s(row.get('name'), 80)}", md, as_of, ["lifecycle", "offer"],
                IMPORTANCE["normal"], {"deep_link": f"/dashboard/lifecycle?offer={oid}"})


def lifecycle_summary_card(row: dict, as_of: Optional[datetime]) -> Card:
    sid = str(row["id"])
    key = f"{row.get('period_type')} {_d(row.get('period_date'))}"
    lines = [f"# Lifecycle summary {key}", "",
             f"- Funnel: {_n(row.get('total_leads'))} leads, {_n(row.get('total_prospects'))} prospects, {_n(row.get('total_customers'))} customers, "
             f"{_n(row.get('total_at_risk'))} at risk, {_n(row.get('total_churned'))} churned",
             f"- Movement: {_n(row.get('new_conversions'))} conversions, {_n(row.get('new_churns'))} churns, {_n(row.get('new_reactivations'))} reactivations, "
             f"{_n(row.get('risk_escalations'))} risk escalations",
             f"- MRR: start {money(row.get('mrr_at_start'))}, new {money(row.get('mrr_new'))}, churned {money(row.get('mrr_churned'))}, "
             f"reactivated {money(row.get('mrr_reactivated'))}, end {money(row.get('mrr_at_end'))}",
             f"- Retention: {_n(row.get('cancel_attempts'))} cancel attempts, {_n(row.get('offers_shown'))} offers shown, "
             f"{_n(row.get('offers_accepted'))} accepted, revenue preserved {money(row.get('revenue_preserved'))}"]
    md = frontmatter("lifecycle_summary", sid, "lifecycle", as_of, ["lifecycle", "summary", str(row.get("period_type") or "")],
                     {"period": _d(row.get("period_date"))}) + "\n".join(lines) + "\n"
    return Card("lifecycle_summary", sid, "lifecycle", f"Lifecycle summary {key}", md, as_of, ["lifecycle", "summary"], IMPORTANCE["normal"],
                {"deep_link": "/dashboard/lifecycle"})


def cancellation_digest_card(month: str, reasons: list[dict], workflows: list[dict], outcomes: list[dict], as_of: Optional[datetime]) -> Card:
    """Cancellation reasons, workflow states and offer outcomes per month. Customer ids, snapshots, router serials and
    FNO references are never read."""
    r = [f"- {_s(x.get('cancel_reason'), 80) or 'no reason given'} via {_s(x.get('source_channel'), 40) or 'n/a'}: {_n(x.get('events'))} cancel attempts"
         for x in sorted(reasons, key=lambda x: (-_n(x.get("events")), str(x.get("cancel_reason"))))]
    w = [f"- Workflow [{x.get('status')}]: {_n(x.get('workflows'))}; router return [{x.get('router_return_status') or 'n/a'}]; "
         f"early termination fees {money(x.get('etf_zar'))}" for x in sorted(workflows, key=lambda x: (str(x.get("status")), str(x.get("router_return_status"))))]
    o = [f"- Outcome [{x.get('outcome')}]: {_n(x.get('outcomes'))}, discount cost {money(x.get('discount_cost'))}, "
         f"monthly revenue before {money(x.get('rev_before'))} / after {money(x.get('rev_after'))}" for x in sorted(outcomes, key=lambda x: str(x.get("outcome")))]
    return digest_card("cancellation_digest", month, "lifecycle", f"Cancellation and retention outcomes {month}", as_of, ["lifecycle", "cancellation", month],
                       [("Cancel attempts by reason", r), ("Cancellation workflows", w), ("Offer outcomes", o)], deep_link="/dashboard/lifecycle?tab=cancellations")


def churn_batch_card(run: dict, levels: list[dict], reasons: list[dict], cases: list[dict], as_of: Optional[datetime]) -> Card:
    """Churn-risk batch digest: counts, reasons, and the top at-risk cases as customer links (no names, no contact data)."""
    rid = str(run["id"])
    lv = [f"- {x.get('risk_level')}: {_n(x.get('customers'))} customers, average churn probability {_f(100 * float(x.get('avg_prob') or 0))}%"
          for x in sorted(levels, key=lambda x: str(x.get("risk_level")))]
    rs = [f"- {_s(x.get('primary_reason'), 80) or 'unspecified'}: {_n(x.get('customers'))}" for x in sorted(reasons, key=lambda x: (-_n(x.get("customers")), str(x.get("primary_reason"))))[:8]]
    cs, edges = [], []
    for c in sorted(cases, key=lambda c: (-float(c.get("churn_probability") or 0), str(c.get("customer_id"))))[:15]:
        cs.append(f"- {link('customer', str(c['customer_id']))}: {c.get('risk_level')}, {_f(100 * float(c.get('churn_probability') or 0))}% probability, "
                  f"reason {_s(c.get('primary_reason'), 80) or 'unspecified'}, tenure {_n(c.get('tenure_months'))} months, spend {money(c.get('monthly_spend_zar'))}"
                  + (", flagged for retention" if c.get("flagged_for_retention") else ""))
        edges.append(Edge("churn_batch", rid, "customer", str(c["customer_id"]), "at_risk", float(c.get("churn_probability") or 0.5), as_of))
    head = [f"- Run {_d(run.get('started_at'))}: {_n(run.get('customers_scored'))} scored, {_n(run.get('critical_count'))} critical, "
            f"{_n(run.get('high_risk_count'))} high, {_n(run.get('medium_risk_count'))} medium, {_n(run.get('low_risk_count'))} low, {_n(run.get('loyal_count'))} loyal"]
    return digest_card("churn_batch", rid, "retention", f"Churn-risk batch {_d(run.get('started_at'))}", as_of, ["retention", "churn", _month(run.get("started_at"))],
                       [("Run", head), ("Risk levels", lv), ("Main reasons", rs), ("Highest-risk customers", cs)],
                       importance=IMPORTANCE["high"] if _n(run.get("critical_count")) else IMPORTANCE["normal"], edges=edges,
                       deep_link="/dashboard/retention", access_key="retention")


def _walk_text(node: Any, out: list[str], depth: int = 0) -> None:
    """Visible copy only: heading/subheading/body/cta label/item title+body+price. No URLs, images, CSS or JS."""
    if depth > 4:
        return
    if isinstance(node, dict):
        for k in ("heading", "subheading", "body", "cta_label", "title", "price", "alt"):
            v = node.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        for k in ("blocks", "items", "images"):
            _walk_text(node.get(k), out, depth + 1)
    elif isinstance(node, list):
        for it in node[:60]:
            _walk_text(it, out, depth + 1)


def portal_page_card(row: dict, content: Any, as_of: Optional[datetime]) -> Optional[Card]:
    """Published pages only; public copy. custom CSS/JS, share tokens and recipient e-mails are never read."""
    if str(row.get("status") or "") != "published":
        return None
    pid = str(row["id"])
    parts: list[str] = []
    content = jsonish(content)
    _walk_text(content if isinstance(content, (dict, list)) else {}, parts)
    lines = [f"# Portal page: {_s(row.get('title'), 160)}", "", f"- Slug: /{_s(row.get('slug'), 100)}", f"- Type: {row.get('page_type') or 'landing'}",
             f"- Published: {_d(row.get('published_at'))}", f"- Views: {_n(row.get('views'))}, conversions: {_n(row.get('conversions'))}"]
    if row.get("description"):
        lines += ["", "## Summary", _s(row["description"], 400)]
    lines += ["", "## Page copy"] + [f"- {_s(p, 400)}" for p in parts[:80]]
    md = frontmatter("portal_page", pid, "portal", as_of, ["portal", "public", str(row.get("page_type") or "landing")], {"page_id": pid}) + "\n".join(lines) + "\n"
    return Card("portal_page", pid, "portal", f"Portal page: {_s(row.get('title'), 100)}", md, as_of, ["portal", "public"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/portal?page={pid}"})


def portal_submissions_digest_card(month: str, rows: list[dict], as_of: Optional[datetime]) -> Card:
    """Counts of CONSENTED submissions per page/campaign source. The form payload, IP hash and consent text are never read."""
    lines = [f"- {_s(r.get('title'), 100)} ({_s(r.get('utm_source'), 40) or 'direct'}/{_s(r.get('utm_medium'), 40) or 'n/a'}/{_s(r.get('utm_campaign'), 60) or 'n/a'}): "
             f"{_n(r.get('submissions'))} consented submissions, {_n(r.get('converted'))} converted" for r in sorted(
                 rows, key=lambda r: (str(r.get("title")), str(r.get("utm_source")), str(r.get("utm_campaign"))))]
    edges = [Edge("portal_submissions_digest", month, "portal_page", str(r["page_id"]), "collected_on", 0.5, as_of) for r in rows if r.get("page_id")]
    return digest_card("portal_submissions_digest", month, "portal", f"Portal form submissions digest {month}", as_of, ["portal", "forms", month],
                       [("Consented submissions", lines)], deep_link="/dashboard/portal?tab=submissions", edges=edges)


def audience_segment_card(row: dict, as_of: Optional[datetime]) -> Card:
    sid = str(row["id"])
    rules = jsonish(row.get("rules"))
    rl: list[str] = []
    if isinstance(rules, dict):
        rl = [f"- {_s(k, 40)}: {_s(v if not isinstance(v, (dict, list)) else str(v), 120)}" for k, v in sorted(rules.items())][:20]
    elif isinstance(rules, list):
        rl = [f"- {_s(v, 160)}" for v in rules[:20]]
    lines = [f"# Audience segment: {_s(row.get('name'), 120)}", "", f"- Members: {_n(row.get('member_count'))}", f"- Created: {_d(row.get('created_at'))}"]
    if row.get("description"):
        lines += ["", "## Description", _s(row["description"], 500)]
    lines += ["", "## Rules"] + (rl or ["- No rules recorded."])
    md = frontmatter("audience_segment", sid, "marketing", as_of, ["marketing", "audience", "segment"], {"segment_id": sid}) + "\n".join(lines) + "\n"
    return Card("audience_segment", sid, "marketing", f"Audience segment: {_s(row.get('name'), 80)}", md, as_of, ["marketing", "audience"], IMPORTANCE["normal"],
                {"deep_link": f"/dashboard/marketing?segment={sid}"})


NEW_CARD_FIELD_SETS: dict[str, Iterable[str]] = {
    "compliance_document": COMPLIANCE_DOC_FIELDS, "compliance_obligation": COMPLIANCE_OBLIGATION_FIELDS, "cipc_filing": CIPC_FIELDS,
    "tax_return": TAX_RETURN_FIELDS, "tax_registration": TAX_REG_FIELDS, "emp201": EMP201_FIELDS, "breach": BREACH_FIELDS,
    "training_course": TRAINING_FIELDS, "company_kpi": COMPANY_KPI_FIELDS, "network_service": NETWORK_SERVICE_FIELDS,
    "product": PRODUCT_FIELDS, "package": PACKAGE_FIELDS, "purchase_order": PO_FIELDS, "supplier": SUPPLIER_FIELDS, "invoice": INVOICE_FIELDS,
    "subscription": SUBSCRIPTION_FIELDS, "payment_arrangement": ARRANGEMENT_FIELDS, "call_session": CALL_FIELDS,
}
