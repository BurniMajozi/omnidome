"""Broad-coverage sources: card determinism, PII freedom, allow-lists, role tags, edges, watermark/tombstone behaviour,
SQL hygiene (explicit columns, tenant filters, no forbidden columns) and the KNOWLEDGE_SOURCES flags. No DB, no network."""
import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest

from services.tenant_memory.knowledge.cards import builders_ext as X
from services.tenant_memory.knowledge.cards import sources as S
from services.tenant_memory.knowledge.cards import sources_ext as E
from services.tenant_memory.knowledge.cards.base import allowed_fields
from services.tenant_memory.knowledge.config import get_settings
from services.tenant_memory.knowledge.embeddings import HashEmbedder
from services.tenant_memory.knowledge.indexer import Indexer, card_to_chunks
from services.tenant_memory.knowledge.kdata import AccessScope
from services.tenant_memory.knowledge.store_memory import MemoryStore

NOW = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
T = "11111111-1111-1111-1111-111111111111"
EMAIL, PHONE, SAID, PWD = "thandi@example.com", "0821234567", "8001015009087", "hunter2"
LEAKS = [EMAIL, PHONE, SAID, PWD]


def run(c):
    return asyncio.run(c)


def clean(card):
    for s in LEAKS:
        assert s not in card.markdown, s


def roles(card):
    return card.access()[1]


# ── compliance ──────────────────────────────────────────────────────────────

def doc_row(**kw):
    legal = ("1. The Customer shall pay all amounts due within 30 days of invoice.\n\n2. The Operator shall not be liable for indirect loss.\n\n"
             f"Contact {EMAIL} or {PHONE}. ID {SAID}. password: {PWD}")
    return {"id": 7, "title": "Master Services Agreement", "document_type": "contract", "mime_type": "application/pdf", "contract_id": 3,
            "ocr_text": legal, "financial_summary": "Annual value R120,000", "tags": "msa,legal", "version": "2", "is_confidential": True,
            "created_at": NOW, "updated_at": NOW, "file_path": "/secret/path.pdf", "uploaded_by": "Jane Smith", "extracted_data": '{"bank":"123"}', **kw}


def test_compliance_document_keeps_legal_text_scrubs_pii_and_is_role_tagged():
    a, b = X.compliance_document_card(doc_row(), NOW), X.compliance_document_card(doc_row(), NOW)
    assert a.markdown == b.markdown
    clean(a)
    assert "The Customer shall pay all amounts due within 30 days of invoice." in a.markdown       # legal wording kept as written
    for hidden in ("/secret/path.pdf", "Jane Smith", "bank"):
        assert hidden not in a.markdown
    assert "compliance" in roles(a) and a.access()[0] == "team"
    assert a.module == "compliance"


def test_long_document_is_split_into_sections_and_chunks():
    text = "\n\n".join(f"Clause {i}. " + ("The parties agree as set out herein. " * 12) for i in range(60))
    card = X.compliance_document_card(doc_row(ocr_text=text), NOW)
    assert card.markdown.count("## Section ") >= 5
    chunks = card_to_chunks(T, card, "m", 1800, 150)
    assert len(chunks) > 3 and all(len(c.markdown) <= 2100 for c in chunks)
    assert all(c.required_roles and c.visibility == "team" for c in chunks)
    huge = X.compliance_document_card(doc_row(ocr_text="word " * 30000), NOW)
    assert "continues beyond the indexed limit" in huge.markdown


def test_filings_do_not_expose_tax_or_reference_numbers():
    reg = X.tax_registration_card({"id": 1, "tax_type": "vat", "status": "active", "registered_date": NOW, "last_filed": NOW, "next_due": NOW,
                                   "registration_number": "4123456789", "sars_reference": "SARS-REF-99", "notes": f"call {PHONE}"}, NOW)
    assert "4123456789" not in reg.markdown and "SARS-REF-99" not in reg.markdown and PHONE not in reg.markdown
    ret = X.tax_return_card({"id": 2, "tax_type": "vat", "period_start": NOW, "period_end": NOW, "status": "submitted", "amount_payable": 1500,
                             "sars_reference": "SARS-REF-99", "filing_reference": "FIL-1"}, NOW)
    assert "FIL-1" not in ret.markdown and "R1,500.00" in ret.markdown
    cipc = X.cipc_filing_card({"id": 3, "filing_type": "Annual return", "status": "filed", "fee_amount": 100, "fee_paid": True,
                               "cipc_reference": "CIPC-9", "confirmation_number": "CONF-1"}, NOW)
    assert "CIPC-9" not in cipc.markdown and "CONF-1" not in cipc.markdown and "paid" in cipc.markdown


def test_emp201_is_company_totals_only_and_finance_visible():
    row = {"id": 9, "period": "2026-09", "status": "prepared", "due_date": NOW, "employee_count": 12, "gross_remuneration": 500000, "paye": 90000,
           "uif_employee": 5000, "uif_employer": 5000, "sdl": 5000, "total_liability": 105000, "rates_verified": True, "filed_at": None,
           "prn": "PRN-SECRET", "receipt_reference": "RCPT-1", "prepared_by": "u-1", "payroll_run_ids": "[1,2]"}
    c = X.emp201_card(row, NOW)
    for hidden in ("PRN-SECRET", "RCPT-1", "u-1", "[1,2]"):
        assert hidden not in c.markdown
    assert "R105,000.00" in c.markdown and {"finance", "compliance"} <= set(roles(c))


def test_consent_digest_has_counts_not_people():
    c = X.consent_digest_card([{"purpose": "Marketing e-mail", "total": 10, "granted": 7, "withdrawn": 2, "expired": 1}], NOW)
    assert "10 records, 7 granted, 2 withdrawn, 1 expired" in c.markdown and c.access()[0] == "team"


# ── HR ──────────────────────────────────────────────────────────────────────

def test_hr_cards_are_hr_only_and_exclude_individuals():
    org = X.hr_org_digest_card([{"department": "Support", "job_title": "Agent", "headcount": 4, "full_name": "Thandi Mokoena", "email": EMAIL},
                                {"department": "Finance", "job_title": "Accountant", "headcount": 1}], NOW)
    assert "Support (4 active)" in org.markdown and "Thandi" not in org.markdown and EMAIL not in org.markdown
    assert set(roles(org)) == {"hr", "hr_manager", "hr_admin"} and org.access()[0] == "team"
    course = X.training_course_card({"id": "c1", "title": "POPIA basics", "description": f"mail {EMAIL}", "category": "COMPLIANCE", "duration_hours": 2,
                                     "mandatory": True, "status": "ACTIVE", "score": 99, "employee_id": "e1"}, {"enrolled": 10, "completed": 6}, NOW)
    assert "Enrolled: 10; completed: 6" in course.markdown and EMAIL not in course.markdown and "99" not in course.markdown
    assert "hr" in roles(course)
    kpi = X.company_kpi_card({"id": "k1", "fiscal_year": 2026, "sales_budget_zar": 1000000, "sales_actual_zar": 900000, "cost_budget_zar": 1, "cost_actual_zar": 1,
                              "profit_budget_zar": 1, "profit_actual_zar": 1, "values_weight_pct": 20, "values_description": "Customer first"}, NOW)
    assert "Customer first" in kpi.markdown and "hr" in roles(kpi)


# ── network / iot / rica ────────────────────────────────────────────────────

def test_network_service_hides_address_gps_and_serial():
    row = {"id": "s1", "customer_id": "c1", "service_reference": "OFS-77", "status": "active", "technology": "ftth", "fno_provider": "Openserve",
           "download_speed_mbps": 100, "upload_speed_mbps": 50, "city": "Pretoria", "province": "Gauteng", "activated_at": NOW,
           "address_line1": "1 Long St", "gps_latitude": -25.7, "ont_serial": "ZTEG12345678", "fno_account_id": "ACC-1"}
    c = X.network_service_card(row, NOW)
    for hidden in ("1 Long St", "-25.7", "ZTEG12345678", "ACC-1"):
        assert hidden not in c.markdown
    assert ("network_service", "customer") == (c.edges[0].src_type, c.edges[0].dst_type)


def test_fleet_digest_has_counts_only():
    c = X.fleet_digest_card([{"device_type": "router", "manufacturer": "Huawei", "model": "HG8", "status": "online", "devices": 40, "silent_24h": 2,
                              "serial_number": "SN-SECRET", "mac_address": "AA:BB:CC:DD:EE:FF", "management_ip": "10.0.0.1"}],
                            [{"device_type": "sensor", "status": "online", "devices": 3, "silent_24h": 0}], NOW)
    for hidden in ("SN-SECRET", "AA:BB", "10.0.0.1"):
        assert hidden not in c.markdown
    assert "40 (2 not seen in 24h)" in c.markdown


def test_sla_incident_and_rica_digests():
    assert "breaches" in X.sla_digest_card("2026-09", [{"metric_type": "latency", "severity": "major", "breaches": 3, "resolved": 2, "avg_seconds": 600}], [], NOW).markdown
    assert "notifications" in X.incident_digest_card("2026-09", [{"trigger_type": "sla_breach", "severity": "major", "notifications": 5, "failed": 1}], NOW).markdown
    r = X.rica_digest_card("2026-09", [{"verification_type": "id", "status": "approved", "verifications": 9, "id_number": SAID}], [], NOW)
    clean(r)
    assert "[approved]: 9" in r.markdown


# ── inventory ───────────────────────────────────────────────────────────────

def test_product_card_excludes_cost_and_catalogue_is_tenant_visible():
    c = X.product_card({"id": "p1", "sku": "ONT-1", "name": "ONT Router", "description": "Dual band", "unit_of_measure": "each", "rrp": 899,
                        "is_active": True, "is_serialized": True, "category_name": "CPE", "cost_price": 500, "markup_pct": 80, "barcode": "BC123"}, NOW)
    assert "R899.00" in c.markdown and "500" not in c.markdown and "BC123" not in c.markdown
    assert c.access() == ("tenant", [])


def test_purchase_order_and_supplier_cards_are_procurement_tagged_with_graph_edges():
    po = X.purchase_order_card({"id": "po1", "supplier_id": "sup1", "supplier_name": "Acme", "warehouse_name": "Main", "po_number": "PO-1", "status": "sent",
                                "subtotal_zar": 1000, "tax_zar": 150, "total_zar": 1150, "currency": "ZAR", "notes": f"call {PHONE}",
                                "created_by": "u1", "approval_hash": "HASH", "sent_to": EMAIL},
                               [{"product_id": "p1", "product_name": "ONT Router", "quantity_ordered": 10, "quantity_received": 4, "unit_cost_zar": 100}], NOW)
    clean(po)
    assert "HASH" not in po.markdown and "u1" not in po.markdown
    assert {(e.dst_type, e.relation) for e in po.edges} == {("supplier", "ordered_from"), ("product", "orders")}
    assert "procurement" in roles(po) and po.access()[0] == "team"
    sup = X.supplier_card({"id": "sup1", "code": "ACM", "name": "Acme", "payment_terms": "30 days", "lead_time_days": 7, "is_active": True, "email": EMAIL,
                           "phone": PHONE, "tax_id": "TAX1", "notes": "bank 12345678901", "contact_person": "Bob"}, {"pos": 3, "open_pos": 1, "total_zar": 5000}, NOW)
    clean(sup)
    for hidden in ("TAX1", "12345678901", "Bob"):
        assert hidden not in sup.markdown
    assert "procurement" in roles(sup)


def test_package_stock_and_movement_cards():
    pk = X.package_card({"id": "k1", "sku": "PK-1", "name": "Fibre 100 bundle", "package_type": "bundle", "rrp": 999, "is_active": True, "cost_price": 400},
                        [{"product_id": "p1", "product_name": "ONT Router", "quantity": 1, "is_required": True, "sort_order": 1}], NOW)
    assert "400" not in pk.markdown and pk.edges[0].relation == "contains"
    st = X.warehouse_stock_card({"id": "w1", "code": "JHB", "name": "Johannesburg", "is_external": False},
                                {"products": 40, "soh": 500, "sit": 10, "allocated": 5, "below_reorder": 2},
                                [{"product_id": "p1", "name": "ONT Router", "sku": "ONT-1", "soh": 1, "reorder_point": 5}], NOW)
    assert "below reorder point: 2" in st.markdown.lower() or "at or below reorder point: 2" in st.markdown
    assert st.edges and st.edges[0].dst_type == "product"
    assert "movements" in X.stock_movement_digest_card("2026-09", [{"movement_type": "receipt", "movements": 4, "units": 40}], NOW).markdown


# ── finance / billing ───────────────────────────────────────────────────────

def test_invoice_card_is_customer_safe_has_edges_and_billing_roles():
    row = {"id": "i1", "customer_id": "c1", "subscription_id": "s1", "number": "INV-1", "status": "overdue", "subtotal_zar": 500, "vat_zar": 75, "total_zar": 575,
           "amount_paid_zar": 100, "due_date": NOW, "created_at": NOW, "notes": f"pay to acc 12345678901 {EMAIL}", "paystack_ref": "PSK"}
    c = X.invoice_card(row, [{"id": "l1", "product_name": "Fibre 100", "quantity": 1, "total_zar": 575, "line_type": "subscription"}], NOW)
    assert c.markdown == X.invoice_card(row, [{"id": "l1", "product_name": "Fibre 100", "quantity": 1, "total_zar": 575, "line_type": "subscription"}], NOW).markdown
    clean(c)
    assert "12345678901" not in c.markdown and "PSK" not in c.markdown
    assert "outstanding R475.00" in c.markdown
    assert {(e.dst_type, e.relation) for e in c.edges} == {("customer", "billed_to"), ("subscription", "for_subscription")}
    assert "billing" in roles(c) and c.importance == 0.75
    assert E._invoice_build({**row, "status": "draft"}, {}, NOW) is None          # drafts have no card


def test_subscription_arrangement_dunning_and_journal_cards():
    sub = X.subscription_card({"id": "s1", "customer_id": "c1", "plan": "Fibre 100", "status": "active", "billing_interval": "month", "base_price_zar": 599,
                               "quantity": 1, "paystack_subscription_code": "SUB_x", "paystack_email_token": "TOK"}, NOW)
    assert "SUB_x" not in sub.markdown and "TOK" not in sub.markdown and sub.edges[0].dst_type == "customer"
    arr = X.payment_arrangement_card({"id": "a1", "customer_id": "c1", "total_owed_zar": 3000, "installment_zar": 1000, "installments_count": 3,
                                      "installments_paid": 1, "status": "active", "notes": "private"}, NOW)
    assert "private" not in arr.markdown and "1 paid" in arr.markdown
    assert "executed" in X.dunning_digest_card("2026-09", [{"action_type": "sms", "step": 1, "actions": 5, "executed": 4, "failed": 1}], NOW).markdown
    coa = X.chart_of_accounts_card([{"code": "1000", "name": "Bank"}, {"code": "4000", "name": "Revenue"}], NOW)
    assert coa.access()[1] == ["finance", "finance_manager", "accountant"]
    jd = X.journal_digest_card("2026-09", {"posted": 10, "unposted": 1, "debit": 1000, "credit": 1000}, [{"grp": "4", "debit": 0, "credit": 1000, "lines": 3}],
                               [{"account_code": "4000", "account_name": "Revenue", "debit": 0, "credit": 1000, "volume": 1000}], NOW)
    assert "Group 4xxx" in jd.markdown


# ── call centre ─────────────────────────────────────────────────────────────

def call_row(**kw):
    return {"id": "call1", "agent_name": "Thandi Mokoena", "customer_id": "c1", "direction": "INBOUND", "queue_name": "Support", "start_time": NOW,
            "duration_seconds": 300, "sentiment_score": 0.4, "outcome": "RESOLVED", "notes": f"cb {PHONE}", "recording_consent": "given",
            "transcript": f"Agent: hello. Customer: my email is {EMAIL}, id {SAID}, password: {PWD}.", "has_transcript": True, "retention_ok": True,
            "recording_url": "https://rec/secret.wav", **kw}


def test_call_transcript_scrubbed_and_consent_gated():
    ok = X.call_session_card(call_row(), NOW)
    clean(ok)
    assert "Agent: hello." in ok.markdown and "Thandi M." in ok.markdown and "Mokoena" not in ok.markdown and "secret.wav" not in ok.markdown
    assert "call_center" in roles(ok)
    for kw in ({"recording_consent": "declined"}, {"recording_consent": "unknown"}, {"retention_ok": False}, {"transcript": None}):
        c = X.call_session_card(call_row(**kw), NOW)
        assert "Agent: hello." not in c.markdown and "Withheld" in c.markdown
        clean(c)
    assert "Agent: hello." in X.call_session_card(call_row(recording_consent="not_required"), NOW).markdown


def test_call_center_digest_uses_initials():
    c = X.call_center_digest_card([{"name": "Support", "direction": "INBOUND", "queued_calls": 2}],
                                  [{"name": "Thandi Mokoena", "status": "available", "csat_score": 4.5, "mttr_minutes": 6, "daily_sales": 2}],
                                  [{"month": "2026-09", "direction": "INBOUND", "calls": 100, "avg_seconds": 240, "avg_sentiment": 0.3, "resolved": 80}], NOW)
    assert "Thandi M." in c.markdown and "Mokoena" not in c.markdown and "call_center" in roles(c)


# ── support / lifecycle / retention / portal / marketing ────────────────────

def test_kb_article_published_only_and_scrubbed():
    row = {"id": "kb1", "title": "Reset your router", "content": f"Hold reset 10s.\n\nMail {EMAIL}", "category": "How to", "tags": ["router", "wifi"], "is_published": True}
    c = X.kb_article_card(row, NOW)
    clean(c)
    assert "Hold reset 10s." in c.markdown and c.access() == ("tenant", [])
    assert X.kb_article_card({**row, "is_published": False}, NOW) is None
    assert "router" in X.kb_article_card({**row, "tags": "{router,wifi}"}, NOW).markdown


def test_lifecycle_cards_and_cancellation_digest():
    j = X.journey_card({"id": "j1", "name": "Save at cancel", "status": "active", "trigger_event": "cancel_request", "times_shown": 10, "times_accepted": 4,
                        "offer_id": "o1", "revenue_preserved": 2000}, NOW)
    assert "40.0% acceptance" in j.markdown and j.edges[0].dst_type == "retention_offer"
    o = X.offer_card({"id": "o1", "name": "20% off", "offer_type": "discount", "status": "active", "parameters": '{"percent": 20, "api_key": "k"}'}, NOW)
    assert "percent=20" in o.markdown
    d = X.cancellation_digest_card("2026-09", [{"cancel_reason": "price", "source_channel": "web", "events": 7}], [{"status": "completed", "workflows": 2, "etf_zar": 100}],
                                   [{"outcome": "retained", "outcomes": 3, "discount_cost": 50, "rev_before": 900, "rev_after": 800}], NOW)
    assert "price via web: 7" in d.markdown
    assert "Funnel" in X.lifecycle_summary_card({"id": "ls1", "period_type": "monthly", "period_date": NOW, "total_leads": 5}, NOW).markdown


def test_churn_batch_lists_customers_by_link_only():
    c = X.churn_batch_card({"id": "b1", "started_at": NOW, "customers_scored": 100, "critical_count": 2, "high_risk_count": 5},
                           [{"risk_level": "critical", "customers": 2, "avg_prob": 0.9}], [{"primary_reason": "price", "customers": 4}],
                           [{"customer_id": "c1", "risk_level": "critical", "churn_probability": 0.93, "primary_reason": "price", "customer_name": "Thandi Mokoena"}], NOW)
    assert "[[customer:c1]]" in c.markdown and "Thandi" not in c.markdown
    assert c.edges[0].dst_id == "c1" and "retention" in roles(c)


def test_portal_page_public_copy_only_and_submissions_digest_without_payload():
    content = {"blocks": [{"type": "hero", "heading": "Fibre for everyone", "body": "From R599", "cta_url": "https://evil", "image": "x.png"},
                          {"type": "faq", "items": [{"title": "Is it fast?", "body": "Yes"}]}]}
    row = {"id": "pg1", "slug": "fibre", "title": "Fibre", "status": "published", "page_type": "landing", "views": 10, "conversions": 1, "custom_js": "alert(1)"}
    c = X.portal_page_card(row, content, NOW)
    assert "Fibre for everyone" in c.markdown and "Is it fast?" in c.markdown and "evil" not in c.markdown and "alert" not in c.markdown
    assert X.portal_page_card({**row, "status": "draft"}, content, NOW) is None
    assert "Fibre for everyone" in X.portal_page_card(row, '{"blocks": [{"heading": "Fibre for everyone"}]}', NOW).markdown
    d = X.portal_submissions_digest_card("2026-09", [{"page_id": "pg1", "title": "Fibre", "utm_source": "fb", "submissions": 4, "converted": 1, "form_data": EMAIL}], NOW)
    clean(d)
    assert "4 consented submissions" in d.markdown and d.edges[0].dst_id == "pg1"


def test_audience_segment_card():
    c = X.audience_segment_card({"id": "g1", "name": "Lapsed", "member_count": 40, "created_at": NOW, "rules": {"status": "churned", "email": EMAIL}}, NOW)
    clean(c)
    assert "Members: 40" in c.markdown


# ── allow-lists ─────────────────────────────────────────────────────────────

def test_allow_list_override_can_only_narrow_new_sources(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_FIELDS_INVOICE", "id,number,status,email,notes")
    allowed = allowed_fields("invoice", X.INVOICE_FIELDS)
    assert allowed == {"id", "number", "status"}
    c = X.invoice_card({"id": "i1", "number": "INV-9", "status": "sent", "total_zar": 999, "customer_id": "c9"}, [], NOW)
    assert "INV-9" in c.markdown and "R999.00" not in c.markdown and not c.edges


def test_every_builder_field_set_excludes_never_index_columns():
    for src, fields in X.NEW_CARD_FIELD_SETS.items():
        assert not (allowed_fields(src, fields) & {"email", "phone", "id_number", "password", "address", "bank_account", "token", "reference", "paystack_ref"}), src


# ── SQL hygiene across every new source ─────────────────────────────────────

FORBIDDEN = re.compile(r"\b(email|billing_email|phone|phone_normalized|id_number|passport|password\w*|secret|api_key|\w*token\w*|serial_number|ont_serial|mac_address|"
                       r"management_ip|ip_address|ip_hash|full_name|salary|basic_salary|bank\w*|account_number|address_line\d|physical_address|street_address|"
                       r"gps_\w+|date_of_birth|tax_number|body_text|body_html|form_data|recipient_email|recording_url|live_transcript|paystack_\w+|"
                       r"radius_password|cost_price|guidance_prompt|custom_js|data_subject_\w+|registration_number|sars_reference|"
                       r"customer_snapshot|customer_features|customer_name|sent_to|approval_hash|contact_person|tax_id|spend_limit)\b", re.I)


class Recorder:
    def __init__(self, exists=True):
        self.sql, self.exists = [], exists

    async def __call__(self, session, sql, params):
        self.sql.append((sql, params))
        return [{"ok": self.exists}] if "to_regclass" in sql else []


@pytest.mark.parametrize("src", E.EXT_SOURCES, ids=lambda s: s.name)
def test_every_new_source_uses_explicit_columns_tenant_filters_and_no_forbidden_columns(monkeypatch, src):
    rec = Recorder()
    monkeypatch.setattr(S, "_rows", rec)
    page = run(src.fetch(None, T, {"last_ts": NOW, "meta": {"last_id": "x"}}, 10))
    assert page.cards == [] and page.rows == 0
    queries = [(q, p) for q, p in rec.sql if "to_regclass" not in q]
    assert queries or src.snapshot, src.name
    for q, p in queries:
        assert not re.search(r"select\s+\*|\.\*", q, re.I), (src.name, q)
        assert re.search(r"tenant_id", q), (src.name, q)
        assert not FORBIDDEN.search(q), (src.name, FORBIDDEN.search(q).group(0), q)
        assert ":t" in q or ":tenant_id" in q
    # reconcile queries obey the same rules
    rec.sql.clear()
    run(src.ids(None, T))
    for q, p in rec.sql:
        if "to_regclass" not in q:
            assert "tenant_id" in q and not re.search(r"select\s+\*", q, re.I)


@pytest.mark.parametrize("src", [s for s in E.EXT_SOURCES if not s.snapshot], ids=lambda s: s.name)
def test_keyset_sources_use_the_watermark_and_stable_order(monkeypatch, src):
    rec = Recorder()
    monkeypatch.setattr(S, "_rows", rec)
    run(src.fetch(None, T, {"last_ts": NOW, "meta": {"last_id": "abc"}}, 7))
    q, p = [x for x in rec.sql if "to_regclass" not in x[0]][0]
    assert "wm_ts" in q and p["wm_id"] == "abc" and p["limit"] == 7 and re.search(r"ORDER BY .*, .*LIMIT", q, re.S)


def test_missing_table_means_empty_page_and_reconcile_refuses(monkeypatch):
    rec = Recorder(exists=False)
    monkeypatch.setattr(S, "_rows", rec)
    src = S.SOURCES["invoices"]
    page = run(src.fetch(None, T, None, 10))
    assert page.cards == [] and page.rows == 0
    assert all("to_regclass" in q for q, _ in rec.sql)
    with pytest.raises(RuntimeError):
        run(src.ids(None, T))
    snap = S.SOURCES["journal_digests"]
    assert run(snap.fetch(None, T, None, 10)).cards == []


def test_all_new_sources_are_registered_with_types_and_modules():
    names = {s.name for s in E.EXT_SOURCES}
    assert names <= set(S.SOURCES) and len(names) == len(E.EXT_SOURCES)
    types = {t for s in E.EXT_SOURCES for t in s.source_types}
    for needed in ("compliance_document", "emp201", "network_service", "fleet_digest", "product", "purchase_order", "invoice", "subscription",
                   "journal_digest", "consent_digest", "call_session", "kb_article", "retention_journey", "churn_batch", "portal_page", "audience_segment", "rica_digest"):
        assert needed in types, needed
    assert set(E.SKIPPED) and all(isinstance(v, str) for v in E.SKIPPED.values())


# ── enable flags ────────────────────────────────────────────────────────────

def test_knowledge_sources_flag(monkeypatch):
    assert S.source_enabled("invoices", "") and S.source_enabled("anything", "all")
    assert S.source_enabled("invoices", "invoices,leads") and not S.source_enabled("hr_org", "invoices,leads")
    assert not S.source_enabled("hr_org", "all,-hr_org") and S.source_enabled("leads", "all,-hr_org")
    assert not S.source_enabled("hr_org", "-hr_org")
    monkeypatch.setenv("KNOWLEDGE_SOURCES", "kb_articles")
    assert S.source_enabled("kb_articles") and not S.source_enabled("invoices")


# ── incremental watermark + tombstones through the real Indexer ─────────────

class FakeTable:
    """In-memory stand-in for knowledge_base answering the SQL that keyset_source generates."""
    def __init__(self):
        self.rows = {}

    def put(self, rid, title, ts, published=True):
        self.rows[rid] = {"id": rid, "title": title, "content": f"{title} body", "category": "How to", "tags": [], "is_published": published,
                          "created_at": ts, "ts": ts}

    async def __call__(self, session, sql, params):
        if "to_regclass" in sql:
            return [{"ok": True}]
        if "AS ts" in sql:
            rows = list(self.rows.values())
            if "wm_ts" in params:
                rows = [r for r in rows if (r["ts"], r["id"]) > (params["wm_ts"], params["wm_id"])]
            return [dict(r) for r in sorted(rows, key=lambda r: (r["ts"], r["id"]))[: params["limit"]]]
        return [{"id": r["id"]} for r in self.rows.values() if r["is_published"]]          # ids(): the `live` predicate


def make_indexer(monkeypatch, table, batch=2):
    monkeypatch.setenv("INDEX_BATCH_SIZE", str(batch))
    monkeypatch.setenv("INDEX_SLEEP_S", "0")
    monkeypatch.setattr(S, "_rows", table)
    store = MemoryStore(now=lambda: NOW)

    @asynccontextmanager
    async def sess():
        yield None

    async def nosleep(_):
        return None

    return Indexer(store, HashEmbedder(32), sess, get_settings(), {"kb_articles": S.SOURCES["kb_articles"]}, nosleep), store


def test_incremental_watermark_unpublish_tombstone_and_reconcile(monkeypatch):
    tb = FakeTable()
    for i in range(5):
        tb.put(f"k{i}", f"Article {i}", NOW + timedelta(minutes=i))
    ix, store = make_indexer(monkeypatch, tb)
    r1 = run(ix.run_source(T, "kb_articles"))
    assert r1["cards"] == 5 and r1["pages"] == 3
    assert run(store.get_watermark(T, "kb_articles"))["last_ts"] == NOW + timedelta(minutes=4)
    assert run(ix.run_source(T, "kb_articles"))["cards"] == 0                       # nothing new: watermark respected
    tb.put("k5", "Article 5", NOW + timedelta(hours=1))
    assert run(ix.run_source(T, "kb_articles"))["cards"] == 1                       # only the new row
    # unpublish => builder returns None => tombstone, no card
    tb.put("k1", "Article 1", NOW + timedelta(hours=2), published=False)
    r = run(ix.run_source(T, "kb_articles"))
    assert r["tombstoned"] == 1 and "k1" not in run(store.live_source_ids(T, "kb_article"))
    # a row deleted at the source disappears on the daily full reconcile
    del tb.rows["k2"]
    rep = run(ix.run_source(T, "kb_articles", full=True))
    assert rep["tombstoned"] >= 1 and "k2" not in run(store.live_source_ids(T, "kb_article"))
    assert run(store.live_source_ids(T, "kb_article")) == {"k0", "k3", "k4", "k5"}
    # unchanged text on a full rebuild is not re-embedded
    assert run(ix.run_source(T, "kb_articles", full=True))["chunks_embedded"] == 0


def test_disabled_sources_are_skipped_by_run_tenant(monkeypatch):
    tb = FakeTable()
    tb.put("k0", "Article 0", NOW)
    ix, store = make_indexer(monkeypatch, tb)
    monkeypatch.setenv("KNOWLEDGE_SOURCES", "leads")
    assert run(ix.run_tenant(T)) == [] and ix.enabled_names() == []
    monkeypatch.setenv("KNOWLEDGE_SOURCES", "all,-kb_articles")
    assert run(ix.run_tenant(T)) == []
    monkeypatch.delenv("KNOWLEDGE_SOURCES")
    assert run(ix.run_tenant(T))[0]["cards"] == 1


def test_role_tagged_chunks_are_hidden_from_other_roles_and_visible_to_admin(monkeypatch):
    store = MemoryStore(now=lambda: NOW)
    ix = Indexer(store, HashEmbedder(32), None, get_settings(), {}, None)
    cards = [X.compliance_document_card(doc_row(), NOW), X.hr_org_digest_card([{"department": "Ops", "job_title": "Tech", "headcount": 3}], NOW),
             X.invoice_card({"id": "i1", "number": "INV-1", "status": "sent"}, [], NOW), X.product_card({"id": "p1", "sku": "S", "name": "ONT", "rrp": 1}, NOW)]
    run(ix.index_cards(T, cards))

    def visible(scope):
        got = run(store.chunks_for_sources(T, [(c.source_type, c.source_id) for c in cards], __import__("services.tenant_memory.knowledge.kdata", fromlist=["Filters"]).Filters(), scope))
        return {c.source_type for c in got}

    agent = AccessScope(T, "u1", frozenset({"agent"}), frozenset(), False)
    assert visible(agent) == {"product"}
    assert visible(AccessScope(T, "u2", frozenset({"hr_manager"}), frozenset(), False)) == {"product", "hr_org"}
    assert visible(AccessScope(T, "u3", frozenset({"billing"}), frozenset(), False)) == {"product", "invoice"}
    assert visible(AccessScope(T, "u4", frozenset({"compliance"}), frozenset(), False)) == {"product", "compliance_document"}
    assert visible(AccessScope(T, "u5", frozenset({"admin"}), frozenset(), True)) == {"product", "hr_org", "invoice", "compliance_document"}


def test_graph_edges_link_customer_invoice_subscription_and_po_product(monkeypatch):
    store = MemoryStore(now=lambda: NOW)
    ix = Indexer(store, HashEmbedder(32), None, get_settings(), {}, None)
    inv = X.invoice_card({"id": "i1", "customer_id": "c1", "subscription_id": "s1", "number": "INV-1", "status": "sent"}, [], NOW)
    po = X.purchase_order_card({"id": "po1", "supplier_id": "sup1", "po_number": "PO-1", "status": "sent"},
                               [{"product_id": "p1", "product_name": "ONT", "quantity_ordered": 1, "quantity_received": 0, "unit_cost_zar": 1}], NOW)
    run(ix.index_cards(T, [inv, po]))
    near_customer = {(n["node_type"], n["node_id"]) for n in run(store.traverse(T, [("customer", "c1")], 2, None, 20))}
    assert ("invoice", "i1") in near_customer and ("subscription", "s1") in near_customer
    near_product = {(n["node_type"], n["node_id"]) for n in run(store.traverse(T, [("product", "p1")], 2, None, 20))}
    assert ("purchase_order", "po1") in near_product and ("supplier", "sup1") in near_product
