"""Panel registry for the insights engine: what each panel's briefing looks at.

`metric_keys` are names from services/fno_intelligence/metric_catalog.py (a test checks them against the catalog when it
is importable). `deep_link` is where a recommendation without a more specific link sends the user.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ALIASES = {"service": "support", "talent": "hr", "call-center": "call_center", "callcenter": "call_center",
           "bi": "analytics", "bi_studio": "analytics", "dashboard": "overview", "executive": "overview"}


@dataclass(frozen=True)
class PanelSpec:
    module: str                    # canonical (matches knowledge PANELS keys, plus "overview")
    label: str
    deep_link: str
    query: str                     # retrieval hint for the module's cards
    metric_keys: tuple = ()
    skill_hint: str = ""           # what to look for among the tenant's skills (feature-detected)
    personal_links: tuple = ()     # link prefixes of the caller's own items that belong to this panel
    knowledge_modules: tuple = ()  # module filter for card retrieval (empty = everything the caller may read)


_K = {
    "inv": "billing.revenue_invoiced.month", "col": "billing.revenue_collected.month", "cash": "billing.cash_received.month",
    "aging": "billing.outstanding_by_aging", "newc": "crm.new_customers.month", "act": "network.services_activated.month",
    "canc": "billing.cancellations.month", "mrr": "billing.mrr_by_plan", "leads": "sales.leads_created.month",
    "lwon": "sales.leads_won.month", "dwon": "sales.deals_won.month", "vwon": "sales.won_value.month",
    "pipe": "sales.pipeline_value_by_stage", "tix": "support.tickets_opened.week", "res": "support.avg_resolution_hours.week",
    "sla": "network.sla_breaches.month", "sends": "marketing.campaign_sends.month", "conv": "marketing.campaign_conversions.month",
}

PANELS: dict[str, PanelSpec] = {p.module: p for p in [
    PanelSpec("overview", "Executive overview", "/dashboard", "company performance revenue pipeline customers churn support network risks",
              (_K["inv"], _K["cash"], _K["mrr"], _K["newc"], _K["dwon"], _K["pipe"], _K["tix"], _K["sla"]),
              "weekly KPI brief executive summary", ("/dashboard",), ()),
    PanelSpec("sales", "Sales", "/dashboard?section=sales", "sales pipeline deals leads won lost stage conversion follow-up",
              (_K["leads"], _K["lwon"], _K["dwon"], _K["vwon"], _K["pipe"]), "pipeline review brief", ("/dashboard/sales",), ("sales",)),
    PanelSpec("billing", "Billing & Collection", "/dashboard?section=billing", "invoices payments collections arrears aging debit orders",
              (_K["inv"], _K["col"], _K["cash"], _K["aging"], _K["mrr"]), "collections brief", ("/dashboard/billing",), ("billing",)),
    PanelSpec("crm", "CRM", "/dashboard?section=crm", "customers accounts health segments interactions onboarding",
              (_K["newc"], _K["canc"], _K["mrr"]), "customer health brief", ("/dashboard/crm",), ("crm",)),
    PanelSpec("retention", "Retention & Churn", "/dashboard?section=retention", "churn cancellations at-risk customers win-back save offers",
              (_K["canc"], _K["mrr"], _K["newc"], _K["tix"]), "churn review brief", ("/dashboard/retention",), ("retention", "crm")),
    PanelSpec("support", "Service & Support", "/dashboard?section=service", "tickets escalations SLA resolution complaints backlog",
              (_K["tix"], _K["res"], _K["sla"]), "support brief", ("/dashboard/service",), ("support",)),
    PanelSpec("marketing", "Marketing", "/dashboard?section=marketing", "campaigns audiences leads conversions social channels",
              (_K["sends"], _K["conv"], _K["leads"]), "campaign performance brief", ("/dashboard/marketing",), ("marketing",)),
    PanelSpec("finance", "Finance & FP&A", "/dashboard?section=finance", "revenue cash budget ebit forecast variance payables",
              (_K["inv"], _K["col"], _K["cash"], _K["aging"], _K["mrr"]), "finance brief", ("/dashboard/finance",), ("finance", "billing")),
    PanelSpec("network", "Network Operations", "/dashboard?section=network", "network outages devices sla breaches capacity activations",
              (_K["act"], _K["sla"]), "network health brief", ("/dashboard/network",), ("network", "iot")),
    PanelSpec("call_center", "Call Center", "/dashboard?section=call-center", "call queues agents handle time service level abandon",
              (_K["tix"],), "call centre brief", ("/dashboard/call-center",), ("call_center",)),
    PanelSpec("inventory", "Inventory", "/dashboard?section=inventory", "stock reorder suppliers purchase orders warehouse",
              (), "inventory brief", ("/dashboard/inventory",), ("inventory",)),
    PanelSpec("iot", "IoT & Devices", "/dashboard?section=iot", "devices online alerts battery firmware telemetry",
              (), "device health brief", ("/dashboard/iot",), ("iot", "network")),
    PanelSpec("compliance", "Compliance", "/dashboard?section=compliance", "compliance audits policies risks incidents POPIA",
              (), "compliance brief", ("/dashboard/compliance",), ("compliance",)),
    PanelSpec("hr", "Staff Dome (Talent)", "/dashboard?section=talent", "staff headcount leave payroll performance objectives wellbeing",
              (), "people brief", ("/dashboard/talent",), ("hr",)),
    PanelSpec("analytics", "BI Studio", "/dashboard?section=analytics", "reports decks datasets dashboards forecasts",
              (_K["inv"], _K["dwon"]), "weekly KPI brief", ("/dashboard/analytics",), ("analytics",)),
    PanelSpec("products", "Products", "/dashboard?section=products", "plans catalog pricing bundles packages",
              (_K["mrr"],), "product brief", ("/dashboard/products",), ("products",)),
]}


def canonical(module: Optional[str]) -> str:
    m = (module or "").strip().lower().replace(" ", "_")
    return ALIASES.get(m, m)


def spec_for(module: Optional[str]) -> Optional[PanelSpec]:
    return PANELS.get(canonical(module))
