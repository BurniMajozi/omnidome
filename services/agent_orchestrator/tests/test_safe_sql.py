"""Unit tests for Safe SQL tool (spec A9 `safe-sql`).

Run with cwd = services/agent_orchestrator:
../../.venv/Scripts/python.exe -m pytest tests/test_safe_sql.py -q
"""

import os
import sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

from services.agent_orchestrator.safe_sql import (
    validate_and_rewrite_query,
    get_allowlist_for_agent,
    DEFAULT_ALLOWLIST,
)

TENANT_A = "00000000-0000-0000-0000-000000000001"
TENANT_B = "00000000-0000-0000-0000-000000000002"


def test_rejects_non_select_statements():
    bad_queries = [
        "INSERT INTO deals (id, title) VALUES ('1', 'bad')",
        "UPDATE leads SET status = 'WON'",
        "DELETE FROM invoices WHERE id = '1'",
        "DROP TABLE deals",
        "ALTER TABLE leads ADD COLUMN test INT",
        "CREATE TABLE hack (id INT)",
        "TRUNCATE TABLE tickets",
    ]
    for sql in bad_queries:
        with pytest.raises(ValueError, match="Only SELECT queries are permitted"):
            validate_and_rewrite_query(sql, tenant_id=TENANT_A)


def test_rejects_multiple_statements():
    sql = "SELECT id FROM deals; DROP TABLE leads;"
    with pytest.raises(ValueError, match="Multiple SQL statements are not permitted"):
        validate_and_rewrite_query(sql, tenant_id=TENANT_A)


def test_rejects_select_into():
    sql = "SELECT * INTO backup_deals FROM deals"
    with pytest.raises(ValueError, match="SELECT INTO statements are not permitted"):
        validate_and_rewrite_query(sql, tenant_id=TENANT_A)


def test_rejects_disallowed_functions():
    sql = "SELECT pg_sleep(5), id FROM deals"
    with pytest.raises(ValueError, match="Function 'pg_sleep' is not permitted"):
        validate_and_rewrite_query(sql, tenant_id=TENANT_A)


def test_rejects_non_allowlisted_tables():
    bad_tables = [
        "SELECT * FROM users",
        "SELECT * FROM agent_conversations",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM information_schema.tables",
    ]
    for sql in bad_tables:
        with pytest.raises(ValueError, match="not in the allowed tables list"):
            validate_and_rewrite_query(sql, tenant_id=TENANT_A)


def test_per_agent_allowlist_enforcement():
    # Support agent can query tickets, contacts, customers but NOT deals
    sql_deals = "SELECT * FROM deals"
    with pytest.raises(ValueError, match="not in the allowed tables list"):
        validate_and_rewrite_query(sql_deals, tenant_id=TENANT_A, agent_type="support")

    # Executive can query deals
    rewritten = validate_and_rewrite_query(sql_deals, tenant_id=TENANT_A, agent_type="executive")
    assert "deals" in rewritten
    assert f"tenant_id = '{TENANT_A}'" in rewritten


def test_rewrites_physical_table_with_tenant_subquery():
    sql = "SELECT id, title FROM deals WHERE status = 'WON'"
    rewritten = validate_and_rewrite_query(sql, tenant_id=TENANT_A)

    # Table is replaced with scoped subquery
    assert f"(SELECT * FROM deals WHERE tenant_id = '{TENANT_A}') AS deals" in rewritten
    assert "LIMIT 200" in rewritten


def test_cross_tenant_attempt_cannot_widen_scope():
    # Model attempts to select another tenant's rows
    sql = f"SELECT id FROM deals WHERE tenant_id = '{TENANT_B}'"
    rewritten = validate_and_rewrite_query(sql, tenant_id=TENANT_A)

    # Subquery scopes to TENANT_A first
    assert f"(SELECT * FROM deals WHERE tenant_id = '{TENANT_A}') AS deals" in rewritten
    # Even if outer WHERE checks TENANT_B, base table only contains TENANT_A rows
    assert f"tenant_id = '{TENANT_B}'" in rewritten


def test_caps_limit_to_max():
    # Missing limit gets capped at 200
    r1 = validate_and_rewrite_query("SELECT id FROM deals", tenant_id=TENANT_A)
    assert "LIMIT 200" in r1

    # Excess limit gets clamped to 200
    r2 = validate_and_rewrite_query("SELECT id FROM deals LIMIT 1000", tenant_id=TENANT_A)
    assert "LIMIT 200" in r2

    # Smaller limit is preserved
    r3 = validate_and_rewrite_query("SELECT id FROM deals LIMIT 25", tenant_id=TENANT_A)
    assert "LIMIT 25" in r3


def test_joins_and_aliases_rewritten():
    sql = "SELECT d.id, l.name FROM deals d JOIN leads l ON d.lead_id = l.id WHERE d.status = 'WON'"
    rewritten = validate_and_rewrite_query(sql, tenant_id=TENANT_A)

    assert f"(SELECT * FROM deals WHERE tenant_id = '{TENANT_A}') AS d" in rewritten
    assert f"(SELECT * FROM leads WHERE tenant_id = '{TENANT_A}') AS l" in rewritten
    assert "d.lead_id = l.id" in rewritten


def test_ctes_rewrite_underlying_tables_not_cte_alias():
    sql = "WITH top_deals AS (SELECT id, amount FROM deals WHERE amount > 1000) SELECT * FROM top_deals"
    rewritten = validate_and_rewrite_query(sql, tenant_id=TENANT_A)

    # deals inside CTE is rewritten
    assert f"(SELECT * FROM deals WHERE tenant_id = '{TENANT_A}') AS deals" in rewritten
    # top_deals in outer query is CTE alias, not rewritten to table subquery
    assert "FROM top_deals" in rewritten
