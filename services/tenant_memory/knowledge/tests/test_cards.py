from datetime import date, datetime, timezone

from services.tenant_memory.knowledge.cards import builders as B
from services.tenant_memory.knowledge.cards.base import NEVER_INDEX, allowed_fields, stable_text
from services.tenant_memory.knowledge.textutil import chunk_markdown, scrub

NOW = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
SECRETS = ["thandi@example.com", "0821234567", "8001015009087", "hunter2", "sk-live-abcdef123456"]


def customer_row(**extra):
    return {"id": "c-1", "first_name": "Thandi", "last_name": "Mokoena", "status": "active", "province": "Gauteng",
            "account_number": "AC100", "rica_verified": True, "company_id": None, "created_at": NOW, "updated_at": NOW,
            "email": SECRETS[0], "phone": SECRETS[1], "id_number": SECRETS[2], "password": SECRETS[3], "address": "1 Long St", **extra}


def test_customer_card_is_deterministic_and_pii_free():
    subs = [{"id": "s1", "plan": "Fibre 100", "status": "active", "base_price_zar": 599, "billing_interval": "month"}]
    tickets = [{"id": "t1", "subject": f"Call me on {SECRETS[1]} or {SECRETS[0]}", "status": "open", "priority": "HIGH", "created_at": NOW}]
    bal = {"open_invoices": 1, "outstanding_zar": 599, "overdue_invoices": 1}
    a = B.customer_card(customer_row(), subs, bal, tickets, ["vip"], NOW)
    b = B.customer_card(customer_row(), subs, bal, tickets, ["vip"], NOW)
    assert a.markdown == b.markdown
    for s in SECRETS + ["Mokoena", "1 Long St"]:
        assert s not in a.markdown
    assert "Thandi M." in a.markdown and "R599.00" in a.markdown
    assert {(e.dst_type, e.relation) for e in a.edges} == {("subscription", "has_subscription"), ("ticket", "raised")}
    assert a.importance == 0.75                      # overdue invoices raise importance


def test_allow_list_can_only_narrow(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_FIELDS_CUSTOMER", "id,first_name,email,province")
    allowed = allowed_fields("customer", B.CUSTOMER_FIELDS)
    assert "email" not in allowed and allowed == {"id", "first_name", "province"}
    card = B.customer_card(customer_row(), [], {}, [], [], NOW)
    assert "Gauteng" in card.markdown and "AC100" not in card.markdown


def test_never_index_is_never_allowed():
    assert not (allowed_fields("x", NEVER_INDEX | {"id"}) & NEVER_INDEX)


def test_scrub_redacts_identifiers_and_secrets():
    out = scrub("mail a@b.co id 8001015009087 card 4111 1111 1111 1111 password: hunter2 tel 082 123 4567")
    for bad in ("a@b.co", "8001015009087", "4111", "hunter2", "082 123 4567"):
        assert bad not in out


def test_hash_text_ignores_volatile_as_of():
    c1 = B.customer_card(customer_row(), [], {}, [], [], NOW)
    c2 = B.customer_card(customer_row(), [], {}, [], [], datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert c1.markdown != c2.markdown and stable_text(c1.markdown) == stable_text(c2.markdown)


def test_ticket_card_hides_private_replies_and_scrubs():
    t = {"id": "t1", "customer_id": "c-1", "subject": "No sync", "description": "mail me x@y.com", "priority": "NORMAL",
         "status": "OPEN", "created_at": NOW}
    replies = [{"id": "r1", "author_type": "STAFF", "message": "internal: refund", "is_private": True, "created_at": NOW},
               {"id": "r2", "author_type": "STAFF", "message": "Please reboot", "is_private": False, "created_at": NOW}]
    md = B.ticket_card(t, replies, NOW).markdown
    assert "internal: refund" not in md and "Please reboot" in md and "x@y.com" not in md


def test_skill_card_never_includes_guidance_prompt():
    sk = {"id": "k1", "skill_name": "refund-flow", "version": "1", "category": "billing", "source_agent_type": "billing",
          "target_agent_types": [], "tools_required": ["billing.refund"], "description": "Handles refunds",
          "guidance_prompt": "SECRET SYSTEM PROMPT"}
    assert "SECRET SYSTEM PROMPT" not in B.skill_card(sk, NOW).markdown


def test_billing_digest_carries_asof_disclaimer_and_role_gate():
    c = B.billing_digest("2026-09", "residential", {"invoices": 10, "invoiced_zar": 6000, "collected_zar": 3000, "payments": 5}, NOW)
    assert "governed queries" in c.markdown and "50.0%" in c.markdown and c.module == "billing"
    assert c.access()[0] == "team" and "finance" in c.access()[1]


def test_metric_fact_card_actual_and_forecast():
    base = {"id": "m1", "metric_key": "revenue", "label": "Revenue", "dimensions": {"segment": "residential"},
            "period_start": date(2026, 3, 1), "period_end": date(2026, 3, 31), "grain": "month", "value": 1080000, "unit": "ZAR",
            "kind": "actual", "method": "bi_semantic.run", "source_query": {"dataset": "billing", "measures": ["revenue"]},
            "source_query_key": "abc123"}
    prior = {"value": 1000000, "period_start": date(2026, 2, 1), "period_end": date(2026, 2, 28), "grain": "month"}
    card = B.metric_fact_card(base, prior, NOW)
    assert "Revenue, March 2026: R1,080,000.00, +8.0% vs February 2026" in card.markdown
    assert "dataset billing" in card.markdown and "abc123" in card.markdown and "segment=residential" in card.markdown
    assert card.source_ref["query_key"] == "abc123"
    fc = B.metric_fact_card({**base, "id": "m2", "kind": "forecast", "model_name": "ets", "model_version": "1",
                             "lower_bound": 1000000, "upper_bound": 1200000, "interval_level": 0.8}, None, NOW)
    assert "(forecast, 80% interval R1,000,000.00 to R1,200,000.00)" in fc.markdown and "Model: ets 1" in fc.markdown


def test_chunking_keeps_short_cards_whole_and_repeats_frontmatter():
    short = "---\nsource: x\n---\n# t\nbody\n"
    assert chunk_markdown(short, 1800) == [short]
    long = "---\nsource: x\n---\n" + "\n\n".join(f"para {i} " + "word " * 60 for i in range(20))
    parts = chunk_markdown(long, 800, 50)
    assert len(parts) > 2 and all(p.startswith("---\nsource: x\n---") for p in parts)
