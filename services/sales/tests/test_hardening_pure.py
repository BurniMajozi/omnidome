"""Sales hardening: logic that needs no database (the DB-backed twins are in test_hardening_db.py).

Run from the repo root:  PYTHONPATH=. python -m pytest services/sales/tests -q
"""

import asyncio
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from sqlalchemy.dialects import postgresql  # noqa: E402

from services.common.auth import AuthContext  # noqa: E402
from services.common.rate_limiter import RateLimiter  # noqa: E402
from services.sales import access, database, lead_actions, lead_service, main  # noqa: E402
from services.sales.lead_stages import (  # noqa: E402
    SALES_CHANNELS,
    STANDARD_FUNNEL_STAGES,
    canonical_stage,
    cohort_conversion,
    funnel_bucket,
    normalize_channel,
)
from services.sales.schema import LEAD_LIFECYCLE_SQL  # noqa: E402

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def run(coro):
    return asyncio.run(coro)


def sql_of(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class Result:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return self

    def scalar(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FakeDB:
    """Records statements and answers them from a script (one Result per execute call)."""

    def __init__(self, *results):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.info = {}

    async def execute(self, stmt, params=None):
        self.statements.append(stmt)
        return self.results.pop(0) if self.results else Result([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def refresh(self, *a, **kw):
        raise AssertionError("refresh must not be reached")


# ── H3: one stage mapping, funnel counts add up ─────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("QUALIFIED", "QUALIFIED"), ("Qualified", "QUALIFIED"), ("  qualified ", "QUALIFIED"),
    ("new", "NEW"), ("Contacted", "CONTACTED"), ("prospecting", "Prospecting"),
    ("PROPOSAL", "Proposal"), ("negotiation", "Negotiation"),
    ("Closed Won", "Closed Won"), ("closed_won", "Closed Won"), ("WON", "Closed Won"),
    ("Closed Lost", "Closed Lost"), ("LOST", "Closed Lost"), ("disqualified", "Closed Lost"),
    ("Discovery", None), ("", None), (None, None),
])
def test_stage_mapping_table(name, expected):
    assert canonical_stage(name) == expected


def test_funnel_bucket_board_stage_matches_lead_status_case_insensitively():
    # the bug: board stage 'Qualified' never matched 'QUALIFIED'
    assert funnel_bucket("CONVERTED", "OPEN", "Qualified", True)[0] == "QUALIFIED"
    assert funnel_bucket("QUALIFIED")[0] == "QUALIFIED"


def test_funnel_bucket_terminals_and_fallbacks():
    assert funnel_bucket("CONVERTED", "WON", "Closed Won", True) == ("Closed Won", True, False)
    assert funnel_bucket("CONVERTED", "OPEN", "Closed Won", True) == ("Closed Won", True, False)
    assert funnel_bucket("CONVERTED", "LOST", "Closed Lost", True) == ("Closed Lost", False, True)
    assert funnel_bucket("WON") == ("Closed Won", True, False)
    assert funnel_bucket("DISQUALIFIED") == ("Closed Lost", False, True)
    assert funnel_bucket("CONVERTED") == ("CONVERTED", False, False)  # deal row missing
    assert funnel_bucket("CONVERTED", "OPEN", "Discovery   call", True) == ("Discovery call", False, False)
    assert funnel_bucket(None)[0] == "NEW"


def lead(status="NEW", channel=None, source=None, deal=None):
    """deal = (status, stage, value) or None"""
    return main.FunnelLead(
        lead_status=status, source_channel=channel, source=source, has_deal=deal is not None,
        deal_status=deal[0] if deal else None, deal_stage=deal[1] if deal else None,
        deal_value=Decimal(str(deal[2])) if deal else Decimal("0"))


MIXED = [
    lead("NEW", "MARKETING"), lead("new", "MARKETING"), lead("CONTACTED", "FIELD_SALES"),
    lead("QUALIFIED", "REFERRAL"), lead("CONVERTED", "FIELD_SALES", deal=("OPEN", "Qualified", 89997)),
    lead("CONVERTED", "FIELD_SALES", deal=("OPEN", "qualified", 100)),
    lead("CONVERTED", "MARKETING", deal=("OPEN", "Proposal", 500)),
    lead("CONVERTED", "MARKETING", deal=("OPEN", "Discovery", 70)),
    lead("CONVERTED", "MARKETING", deal=("OPEN", "DISCOVERY ", 30)),
    lead("WON", "TENDER", deal=("WON", "Closed Won", 1000)),
    lead("CONVERTED", "TENDER", deal=("LOST", "Closed Lost", 400)),
    lead("LOST", "TENDER"), lead("DISQUALIFIED", "BROADBAND"), lead("CONVERTED", "OTHER"),
    lead("NEW", None, source="weird source"),
]


def test_funnel_counts_always_sum_to_total_leads():
    data = main.compute_funnel(MIXED)
    assert sum(data["overall_counts"].values()) == len(MIXED)
    for cd in data["channels"].values():
        assert sum(cd["stage_counts"].values()) == cd["total_leads"]
    assert sum(cd["total_leads"] for cd in data["channels"].values()) == len(MIXED)
    counts = data["overall_counts"]
    assert counts["QUALIFIED"] == 3          # 1 lead + 2 board deals ('Qualified', 'qualified')
    assert counts["Discovery"] == 2          # custom board stage, case-insensitive, never dropped
    assert counts["Closed Won"] == 1 and counts["Closed Lost"] == 3 and counts["CONVERTED"] == 1
    assert set(STANDARD_FUNNEL_STAGES) <= set(counts)


def test_funnel_value_split_open_won_lost():
    cd = main.compute_funnel(MIXED)["channels"]
    total_open = sum(c["open_value_zar"] for c in cd.values())
    assert total_open == Decimal("89997") + 100 + 500 + 70 + 30
    assert sum(c["won_value_zar"] for c in cd.values()) == Decimal("1000")
    assert sum(c["lost_value_zar"] for c in cd.values()) == Decimal("400")
    assert cd["TENDER"]["won_count"] == 1 and cd["TENDER"]["lost_count"] == 2


def test_funnel_unknown_channels_land_in_other_so_nothing_is_dropped():
    cd = main.compute_funnel([lead("NEW", None, source="BROADBAND"), lead("NEW", "weird")])["channels"]
    assert cd["OTHER"]["total_leads"] == 2


def test_cohort_conversion_is_clamped_and_never_divides_by_zero():
    out = cohort_conversion({"NEW": 10, "CONTACTED": 0, "QUALIFIED": 3, "Closed Won": 2, "Closed Lost": 4})
    assert out["NEW"]["cohort"] == 15  # everyone who is at or past NEW (lost excluded)
    for stage, row in out.items():
        assert 0.0 <= row["conversion_from_previous_pct"] <= 100.0, stage
    assert cohort_conversion({})["NEW"]["conversion_from_previous_pct"] == 0.0
    # a stage with more leads than the previous one can never read above 100 %
    skewed = cohort_conversion({"NEW": 0, "Proposal": 7})
    assert all(r["conversion_from_previous_pct"] <= 100.0 for r in skewed.values())


# ── H3: channel mapping ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("FIELD_SALES", "FIELD_SALES"), ("call-center-inbound", "CALL_CENTER_INBOUND"), ("FIELD_VISIT", "FIELD_SALES"),
    ("inbound_call", "CALL_CENTER_INBOUND"), ("telesales", "CALL_CENTER_OUTBOUND"), ("web_form", "PORTAL_WEBSITE"),
    ("tender_rfq", "TENDER"), ("campaign_ad", "MARKETING"), ("Facebook ad", "MARKETING"),
    ("email enquiry", "INBOUND_EMAIL"), ("walk-in", "WALK_IN"), ("partner", "REFERRAL"),
    # substring traps: none of these contain the keyword as a WORD
    ("BROADBAND", "OTHER"), ("DIALING", "OTHER"), ("ROADSHOW", "OTHER"), ("ADDRESS LIST", "OTHER"),
    ("CALLING", "CALL_CENTER_OUTBOUND"), ("", "OTHER"), ("totally unknown", "OTHER"),
])
def test_channel_allow_list(raw, expected):
    assert normalize_channel(None, raw) == expected
    assert normalize_channel(raw) == expected if raw else True


def test_channel_result_is_always_in_the_allow_list():
    for raw in ["xyz", "BROADBAND", "a" * 80, "  ", "!!!", "FIELD", "call in", "Unknown_Thing"]:
        assert normalize_channel(raw) in SALES_CHANNELS
        assert normalize_channel(None, raw) in SALES_CHANNELS


def test_sql_backfill_mirrors_python_with_word_boundaries():
    assert "ILIKE '%ad%'" not in LEAD_LIFECYCLE_SQL
    assert "source ILIKE '%web%'" not in LEAD_LIFECYCLE_SQL
    assert "(^|[^a-z0-9])(market|marketing|campaign|social|ad|ads" in LEAD_LIFECYCLE_SQL
    assert "ELSE 'OTHER'" in LEAD_LIFECYCLE_SQL
    # rows holding a raw value outside the allow-list are reset and redone
    assert "SET source_channel = NULL" in LEAD_LIFECYCLE_SQL


def test_chunking_keeps_every_statement_under_asyncpg_parameter_cap():
    ids = list(range(70000))
    chunks = lead_service.chunked(ids)
    assert sum(len(c) for c in chunks) == 70000 and max(len(c) for c in chunks) < 32767


# ── H2: dates and summary ───────────────────────────────────────────────────

def test_end_date_includes_the_whole_end_day():
    assert main._next_day_start(date(2026, 9, 30)) == datetime(2026, 10, 1, 0, 0)
    conds = main._deal_conditions(TENANT, end_date=date(2026, 9, 30), closed_to=date(2026, 9, 30),
                                  closed_from=date(2026, 9, 1))
    compiled = [c.compile(dialect=postgresql.dialect()) for c in conds]
    text_ = " ".join(str(c) for c in compiled)
    assert "deals.created_at <" in text_ and "deals.closed_at <" in text_ and "deals.closed_at >=" in text_
    bounds = [v for c in compiled for v in c.params.values() if isinstance(v, datetime)]
    assert datetime(2026, 10, 1) in bounds and datetime(2026, 9, 1) in bounds


def test_deals_summary_is_computed_in_sql():
    sql = sql_of(main._deal_summary_query(main._deal_conditions(TENANT, status_filter="won")))
    assert sql.count("FILTER (WHERE deals.status") == 6
    assert "coalesce(sum(deals.value_zar)" in sql.lower() or "coalesce(sum(deals.value_zar)" in sql
    assert main._money(Decimal("19889.005")) == 19889.01 and main._money(None) == 0.0


def test_summary_route_is_registered_before_the_deal_id_route():
    paths = [getattr(r, "path", "") for r in main.app.routes]
    assert paths.index("/deals/summary") < paths.index("/deals/{deal_id}")


# ── M1: commissions report ──────────────────────────────────────────────────

def test_commission_report_sql_compiles_with_filter_counts():
    stmt = main._commission_report_query(TENANT, datetime(2026, 9, 1), datetime(2026, 10, 1))
    sql = sql_of(stmt)
    assert sql.count("FILTER (WHERE commissions.status") == 4
    assert "GROUP BY commissions.agent_id" in sql and "CAST" not in sql.upper().replace("COALESCE", "")


# ── H4: closed deals are terminal ───────────────────────────────────────────

def test_closed_deal_decision_table():
    d = main._closed_deal_decision
    assert d("OPEN", "WON") == "proceed" and d(None, "LOST") == "proceed"
    assert d("WON", "WON") == "noop" and d("LOST", "LOST") == "noop"
    for current, target in (("WON", "LOST"), ("LOST", "WON")):
        with pytest.raises(HTTPException) as exc:
            d(current, target)
        assert exc.value.status_code == 409


def test_repeat_close_won_books_nothing():
    deal = SimpleNamespace(status="WON", agent_id=uuid.uuid4())
    db = FakeDB()
    run(main._close_won(db, TENANT, deal))
    assert db.statements == [] and db.added == [] and db.info == {}


def test_close_lost_on_a_won_deal_is_409_and_touches_nothing():
    deal = SimpleNamespace(status="WON")
    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        run(main._close_lost(db, TENANT, deal, "changed mind"))
    assert exc.value.status_code == 409 and db.statements == [] and db.info == {}
    with pytest.raises(HTTPException) as exc:
        run(main._close_won(db, TENANT, SimpleNamespace(status="LOST")))
    assert exc.value.status_code == 409


def test_deals_are_locked_for_update_before_the_status_check():
    deal = SimpleNamespace(id=uuid.uuid4(), status="OPEN")
    db = FakeDB(Result([deal]))
    assert run(main._lock_deal(db, TENANT, deal.id)) is deal
    assert "FOR UPDATE" in sql_of(db.statements[0])
    with pytest.raises(HTTPException) as exc:
        run(main._lock_deal(FakeDB(Result([])), TENANT, uuid.uuid4()))
    assert exc.value.status_code == 404


def test_quote_rows_are_locked_too():
    quote = SimpleNamespace(id=uuid.uuid4())
    db = FakeDB(Result([quote]))
    assert run(main._lock_quote(db, TENANT, quote.id)) is quote
    assert "FOR UPDATE" in sql_of(db.statements[0])


def test_quote_expiry():
    today = date(2026, 10, 1)
    assert main._quote_expired(SimpleNamespace(valid_until=date(2026, 9, 30)), today)
    assert not main._quote_expired(SimpleNamespace(valid_until=today), today)
    assert not main._quote_expired(SimpleNamespace(valid_until=None), today)


def test_external_bridges_run_only_after_commit_and_never_after_rollback():
    calls = []

    class FakeSession:
        def __init__(self, fail):
            self.info, self.fail = {}, fail

        async def commit(self):
            calls.append("commit")

        async def rollback(self):
            calls.append("rollback")

        async def close(self):
            pass

    async def hook():
        calls.append("hook")

    def factory(fail):
        return lambda: FakeSession(fail)

    async def scenario(fail):
        database._session_factory = factory(fail)
        try:
            async with database.get_session() as session:
                database.after_commit(session, hook)
                calls.append("work")
                if fail:
                    raise RuntimeError("boom")
        except RuntimeError:
            pass

    try:
        run(scenario(False))
        assert calls == ["work", "commit", "hook"]
        calls.clear()
        run(scenario(True))
        assert calls == ["work", "rollback"]  # rolled back: the finance journal is never posted
    finally:
        database._session_factory = None


# ── M3: foreign ids are 404 ─────────────────────────────────────────────────

@pytest.mark.parametrize("call", [
    lambda db: main._tenant_stage(db, TENANT, uuid.uuid4()),
    lambda db: main._require_lead(db, TENANT, uuid.uuid4()),
    lambda db: main._require_contact(db, TENANT, uuid.uuid4()),
    lambda db: main._require_deal(db, TENANT, uuid.uuid4()),
    lambda db: main._ensure_contact(db, TENANT, uuid.uuid4(), None, datetime(2026, 9, 1)),  # id owned by another tenant
])
def test_foreign_ids_are_not_found(call):
    db = FakeDB(Result([]), Result([]), Result([]))
    with pytest.raises(HTTPException) as exc:
        run(call(db))
    assert exc.value.status_code == 404


def test_tenant_stage_query_joins_the_tenants_pipeline():
    stage = SimpleNamespace(id=uuid.uuid4(), name="Qualified")
    db = FakeDB(Result([stage]))
    assert run(main._tenant_stage(db, TENANT, stage.id)) is stage
    sql = sql_of(db.statements[0])
    assert "JOIN pipelines" in sql and "pipelines.tenant_id" in sql


def test_ids_left_out_are_not_checked():
    db = FakeDB()
    run(main._require_lead(db, TENANT, None))
    run(main._require_agent(db, TENANT, None))
    run(main._require_package(db, TENANT, None))
    caller = uuid.uuid4()
    run(main._require_agent(db, TENANT, caller, caller))
    assert db.statements == []


def test_deal_lead_join_is_tenant_scoped():
    # list_deals / get_deal outer-join Lead on BOTH id and tenant
    src = open(main.__file__, encoding="utf-8").read()
    assert src.count("Lead.tenant_id == Deal.tenant_id") >= 2
    assert ".outerjoin(Lead, Lead.id == Deal.lead_id)" not in src


# ── M4: default pipeline ────────────────────────────────────────────────────

def test_existing_default_pipeline_is_returned_without_locking():
    pid = uuid.uuid4()
    db = FakeDB(Result([pid]))
    assert run(main._ensure_default_pipeline(db, TENANT)) == pid
    assert len(db.statements) == 1 and "pg_advisory" not in str(db.statements[0])


def test_missing_default_pipeline_is_created_once_under_an_advisory_lock():
    db = FakeDB(Result([]), Result([]), Result([]))  # first lookup, the lock, the re-check: nothing there
    pid = run(main._ensure_default_pipeline(db, TENANT))
    assert "pg_advisory_xact_lock" in str(db.statements[1])
    pipelines = [o for o in db.added if isinstance(o, main.Pipeline)]
    stages = [o for o in db.added if isinstance(o, main.DealStage)]
    assert len(pipelines) == 1 and pipelines[0].id == pid and pipelines[0].is_default
    assert [s.name for s in stages] == [d["name"] for d in main.DEFAULT_STAGES]


def test_a_request_that_waited_for_the_lock_reuses_the_winners_pipeline():
    winner = uuid.uuid4()
    db = FakeDB(Result([]), Result([]), Result([winner]))
    assert run(main._ensure_default_pipeline(db, TENANT)) == winner
    assert db.added == []


def test_default_pipeline_lookup_is_deterministic_not_scalar_one_or_none():
    src = open(main.__file__, encoding="utf-8").read()
    body = src[src.index("async def _ensure_default_pipeline"):src.index("async def _get_stages")]
    assert "scalar_one_or_none" not in body and "order_by(Pipeline.id)" in body
    from services.sales import schema
    sql = " ".join(c for _, _, c in schema._GUARDED_UNIQUE_INDEXES)
    assert "uq_pipelines_one_default ON pipelines (tenant_id) WHERE is_default" in sql
    assert "uq_deal_stages_pipeline_name" in sql and "uq_commissions_deal_live" in sql


# ── M5: roles ───────────────────────────────────────────────────────────────

def ctx(*roles, platform=False):
    return AuthContext(user_id=uuid.uuid4(), tenant_id=TENANT, roles=list(roles), rbac_loaded=True,
                       is_platform_admin=platform)


@pytest.mark.parametrize("roles,tier,ok", [
    (["org_user"], "admin", False), (["org_user"], "manager", False), (["org_user"], "agent", False),
    ([], "agent", False),
    (["sales_agent"], "agent", True), (["sales_agent"], "manager", False), (["sales_agent"], "admin", False),
    (["manager"], "manager", True), (["manager"], "admin", False), (["manager"], "agent", True),
    (["org_admin"], "admin", True), (["Owner"], "admin", True), (["tenant_admin"], "manager", True),
])
def test_role_tiers(roles, tier, ok):
    if ok:
        run(access.require(ctx(*roles), None, tier))
    else:
        with pytest.raises(HTTPException) as exc:
            run(access.require(ctx(*roles), None, tier))
        assert exc.value.status_code == 403


def test_platform_admin_passes_and_enforcement_can_be_switched_off(monkeypatch):
    run(access.require(ctx(platform=True), None, "admin"))
    monkeypatch.setenv("SALES_ENFORCE_ROLES", "false")
    run(access.require(ctx("org_user"), None, "admin"))


def test_rbac_failure_fails_closed(monkeypatch):
    class Boom:
        def begin_nested(self):
            raise RuntimeError("no rbac tables")

    a = AuthContext(user_id=uuid.uuid4(), tenant_id=TENANT, roles=["admin"], rbac_loaded=False)
    monkeypatch.setenv("AUTH_ENFORCE_RBAC", "true")
    with pytest.raises(HTTPException) as exc:
        run(access.require(a, Boom(), "admin"))
    assert exc.value.status_code == 403  # token roles are not trusted while enforcing


def test_sensitive_routes_carry_the_role_dependency():
    by_path = {(r.path, m): r for r in main.app.routes if hasattr(r, "methods") for m in r.methods}

    def gates(path, method):
        names = {getattr(d.call, "__name__", "") for d in by_path[(path, method)].dependant.dependencies}
        return {n for n in names if n.startswith("require_sales_")}

    assert gates("/deals/{deal_id}", "DELETE") == {"require_sales_admin"}
    assert gates("/pipeline/stages", "POST") == {"require_sales_admin"}
    assert gates("/targets", "POST") == {"require_sales_admin"}
    assert gates("/commissions/report", "GET") == {"require_sales_manager"}
    assert gates("/leads/{lead_id}/email", "POST") == {"require_sales_agent"}
    assert gates("/quotes/{quote_id}/send", "POST") == {"require_sales_agent"}


def test_lead_email_rate_limit_is_per_tenant(monkeypatch):
    monkeypatch.setattr(main, "_lead_email_limiter", RateLimiter(max_requests=3, window_seconds=60))
    other = uuid.uuid4()
    for _ in range(3):
        main.check_lead_email_rate(TENANT)
    with pytest.raises(HTTPException) as exc:
        main.check_lead_email_rate(TENANT)
    assert exc.value.status_code == 429
    main.check_lead_email_rate(other)  # another tenant has its own budget


def test_default_email_rate_is_twenty_a_minute():
    assert main.LEAD_EMAIL_RATE_PER_MIN == int(os.getenv("LEAD_EMAIL_RATE_PER_MIN", "20"))


# ── Suppression ─────────────────────────────────────────────────────────────

def email_event(**over):
    lead_id = str(uuid.uuid4())
    e = {"id": str(uuid.uuid4()), "tenant_id": str(TENANT), "attempt": 1,
         "payload": {"lead_id": lead_id, "to": "optout@example.com", "subject": "Hello", "body": "Hi"}}
    e.update(over)
    return e


def patch_email_path(monkeypatch, suppressed):
    sent, recorded = [], []

    @asynccontextmanager
    async def fake_session():
        yield FakeDB(Result([]))

    async def fake_record(db, tenant_id, lead_id, kind, summary, details=None, actor=None, idempotency_key=None):
        recorded.append((kind, summary, idempotency_key))

    async def fake_send(to, subject, html, **kw):
        sent.append(to)
        return "msg-1"

    async def fake_is_suppressed(session, tenant_id, email):
        return suppressed

    import services.common.suppression as suppression

    monkeypatch.setattr(lead_actions, "get_session", fake_session)
    monkeypatch.setattr(lead_actions, "record_activity", fake_record)
    monkeypatch.setattr(lead_actions.agentmail, "send_email", fake_send)
    monkeypatch.setattr(suppression, "is_suppressed", fake_is_suppressed)
    return sent, recorded


def test_opted_out_address_is_skipped_and_recorded(monkeypatch):
    sent, recorded = patch_email_path(monkeypatch, suppressed=True)
    run(lead_actions.handle_email_requested(email_event()))
    assert sent == []
    assert [r[:2] for r in recorded] == [("email_suppressed", "email suppressed (opt-out)")]


def test_allowed_address_is_sent_and_recorded_once(monkeypatch):
    sent, recorded = patch_email_path(monkeypatch, suppressed=False)
    event = email_event()
    run(lead_actions.handle_email_requested(event))
    assert sent == ["optout@example.com"]
    assert recorded[0][0] == "email_sent" and recorded[0][2] == f"sent:{event['id']}"


def test_missing_suppression_module_allows_with_a_warning(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "services.common.suppression", None)  # import raises ImportError
    with caplog.at_level("WARNING", logger="sales.lead_actions"):
        assert run(lead_actions.email_is_suppressed(FakeDB(), TENANT, "a@b.co")) is False
    assert "opt-out check" in caplog.text


# ── LOW ─────────────────────────────────────────────────────────────────────

def test_ai_draft_attribution_belongs_to_automations():
    r = main.resolve_note_kind
    assert r("note", False).kind == "note" and r("call", False).kind == "call_logged"
    auto = r("ai_draft", True)
    assert (auto.kind, auto.actor_name, auto.unverified) == ("ai_draft", main.AI_DRAFT_ACTOR, False)
    person = r("ai_draft", False)
    assert person.kind == "ai_draft" and person.actor_name != main.AI_DRAFT_ACTOR and person.unverified


def test_strict_mode_downgrades_a_clients_ai_draft_to_a_note(monkeypatch):
    monkeypatch.setenv("SALES_AI_DRAFT_STRICT", "true")
    assert main.resolve_note_kind("ai_draft", False) == main.NoteKind("note")
    assert main.resolve_note_kind("ai_draft", True).kind == "ai_draft"


def test_automation_caller_detection():
    plain = ctx("org_admin")
    assert not access.is_automation_caller(plain, {})
    assert access.is_automation_caller(plain, {"X-Automation-Run": "run-1"})
    assert access.is_automation_caller(ctx("automation"), {})


def test_record_activity_with_a_key_returns_the_existing_row():
    existing = SimpleNamespace(id=uuid.uuid4())
    db = FakeDB(Result([existing]))
    got = run(lead_service.record_activity(db, TENANT, uuid.uuid4(), "email_sent", "x", {"a": 1},
                                           idempotency_key="sent:1"))
    assert got is existing and db.added == []
    db = FakeDB(Result([]))
    made = run(lead_service.record_activity(db, TENANT, uuid.uuid4(), "email_sent", "x", {"a": 1},
                                            idempotency_key="sent:1"))
    assert db.added == [made] and made.details == {"a": 1, "idem_key": "sent:1"}


def test_quote_send_is_honest_about_delivery():
    assert main.QuoteSend().mark_sent_only is False
    assert "delivery" in main.QuoteResponse.model_fields
