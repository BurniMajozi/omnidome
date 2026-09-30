"""Safe tenant-scoped SQL execution tool (spec A9 `safe-sql`).

Follows the WeKnora `database_query` pattern:
1. Parse SQL with sqlglot (reject invalid syntax or non-SQL).
2. Exactly 1 statement, strictly SELECT (reject INSERT/UPDATE/DELETE/DDL/SELECT INTO).
3. Validate all tables against per-agent allowlist (executive/analytics: deals, leads, etc.).
4. Rewrite every allowed table to `(SELECT * FROM table WHERE tenant_id = :tenant) AS alias`
   so queries cannot read across tenants even if the model writes a tenant_id clause.
5. Limit capped at <= 200 (injected if missing).
6. Executed in a READ ONLY transaction with statement_timeout = 5s.
7. Results formatted and capped according to output budget (A3).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set
import uuid

import sqlglot
import sqlglot.expressions as exp
from sqlalchemy import text

from services.common.db import session_scope

logger = logging.getLogger(__name__)

DEFAULT_STATEMENT_TIMEOUT_S = 5
MAX_ROW_LIMIT = 200
DEFAULT_MAX_CHARS = 8000

# Per-agent table allowlists (spec A9)
DEFAULT_ALLOWLIST: Set[str] = {
    "deals",
    "leads",
    "contacts",
    "customers",
    "invoices",
    "tickets",
    "subscriptions",
    "payments",
    "lead_activities",
    "lead_tasks",
}

AGENT_TABLE_ALLOWLISTS: Dict[str, Set[str]] = {
    "auto": DEFAULT_ALLOWLIST,
    "orchestrator": DEFAULT_ALLOWLIST,
    "executive": DEFAULT_ALLOWLIST,
    "analytics": DEFAULT_ALLOWLIST,
    "sales": {"deals", "leads", "contacts", "customers", "lead_activities", "lead_tasks"},
    "support": {"tickets", "contacts", "customers"},
    "billing": {"invoices", "payments", "subscriptions", "contacts", "customers"},
    "retention": {"deals", "leads", "customers", "invoices", "subscriptions", "tickets"},
}

# Functions that read the server, run SQL given as a string (and so bypass the
# table allowlist and tenant rewrite), or reach other databases.
DISALLOWED_FUNCTIONS = re.compile(
    r"^(pg_.*|lo_.*|dblink.*|.*_to_xml.*|.*_to_xmlschema|ts_stat|current_setting|set_config|"
    r"txid_.*|inet_(server|client)_.*|version|system|exec|sleep)$",
    re.IGNORECASE,
)

def _function_name(func: exp.Func) -> str:
    """The SQL function's own name. For functions sqlglot knows, `.name` is the
    first argument's name, not the function's, so use sql_name() for those."""
    if isinstance(func, exp.Anonymous):
        return str(func.this or "").lower()
    return func.sql_name().lower()


def get_allowlist_for_agent(agent_type: Optional[str] = None) -> Set[str]:
    """Get the table allowlist for a specific agent type. None (direct API use)
    gets the default list; an agent without a list gets no tables — an OKF
    skill can hand analytics.query to any agent."""
    if not agent_type:
        return set(DEFAULT_ALLOWLIST)
    return set(AGENT_TABLE_ALLOWLISTS.get(agent_type.lower(), set()))


def validate_and_rewrite_query(
    sql: str,
    tenant_id: str,
    agent_type: Optional[str] = None,
) -> str:
    """Validate query safety and rewrite tables with tenant isolation subqueries.

    Raises ValueError on any safety violation.
    """
    cleaned_sql = sql.strip().rstrip(";")
    if not cleaned_sql:
        raise ValueError("Empty SQL query provided")

    try:
        statements = sqlglot.parse(cleaned_sql, read="postgres")
    except Exception as exc:
        raise ValueError(f"SQL parse error: {exc}") from exc

    if not statements:
        raise ValueError("No SQL statements parsed")
    if len(statements) > 1:
        raise ValueError("Multiple SQL statements are not permitted")

    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise ValueError(
            f"Only SELECT queries are permitted (found {statement.__class__.__name__})"
        )

    # Disallow SELECT ... INTO
    if statement.args.get("into") is not None:
        raise ValueError("SELECT INTO statements are not permitted")

    # Disallow dangerous functions
    for func in statement.find_all(exp.Func):
        fname = _function_name(func)
        if DISALLOWED_FUNCTIONS.match(fname):
            raise ValueError(f"Function '{fname}' is not permitted")

    # CTEs. The rewrite below treats a table reference as a CTE (and leaves it
    # unscoped) when its name is a CTE name, so that must match Postgres'
    # scoping exactly or a CTE could hide a physical table from the tenant
    # filter ("WITH deals AS (SELECT * FROM deals) ..." reads every tenant):
    # - one top-level WITH only, not RECURSIVE;
    # - inside CTE i, a CTE name may only refer to a CTE defined before it.
    withs = list(statement.find_all(exp.With))
    top_with = next((w for w in withs if w.parent is statement), None)   # arg key differs by sqlglot version
    if withs and (len(withs) > 1 or withs[0] is not top_with):
        raise ValueError("Only one top-level WITH clause is permitted")
    ctes: Set[str] = set()
    if top_with is not None:
        if top_with.args.get("recursive"):
            raise ValueError("WITH RECURSIVE is not permitted")
        names = [(cte.alias or "").lower() for cte in top_with.expressions]
        for i, cte in enumerate(top_with.expressions):
            earlier = set(names[:i])
            for table in cte.this.find_all(exp.Table):
                tname = (table.name or "").lower()
                if tname in names and tname not in earlier:
                    raise ValueError(f"WITH name '{tname}' may not reuse the name of a table it reads")
        ctes = set(names)

    allowlist = get_allowlist_for_agent(agent_type)

    # Validate all referenced physical tables against allowlist
    found_tables = []
    for table in statement.find_all(exp.Table):
        tname = (table.name or "").lower()
        if not tname:
            continue
        if tname in ctes:
            continue
        if tname not in allowlist:
            allowed_sorted = ", ".join(sorted(allowlist))
            raise ValueError(
                f"Table '{tname}' is not in the allowed tables list ({allowed_sorted})"
            )
        found_tables.append(tname)

    if not found_tables and not statement.find_all(exp.CTE):
        # Query doesn't reference any table (e.g. SELECT 1)
        pass

    # Tenant-scope rewriting: rewrite each physical table `t` to
    # `(SELECT * FROM t WHERE tenant_id = 'tenant_id') AS alias`
    clean_tenant = str(uuid.UUID(str(tenant_id)))  # validate tenant UUID formatting

    def _rewrite_table(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Table):
            tname = (node.name or "").lower()
            if tname in ctes:
                return node
            alias = node.alias or tname
            subq_sql = f"(SELECT * FROM {tname} WHERE tenant_id = '{clean_tenant}') AS {alias}"
            return sqlglot.parse_one(subq_sql, read="postgres")
        return node

    rewritten_statement = statement.transform(_rewrite_table, copy=True)

    # Ensure LIMIT <= MAX_ROW_LIMIT (inject or cap)
    limit_exp = rewritten_statement.args.get("limit")
    limit_val = MAX_ROW_LIMIT
    if limit_exp is not None and limit_exp.expression is not None:
        try:
            val = int(limit_exp.expression.name)
            limit_val = min(val, MAX_ROW_LIMIT)
        except Exception:
            limit_val = MAX_ROW_LIMIT
        rewritten_statement.set("limit", None)

    rewritten_statement = rewritten_statement.limit(limit_val)
    return rewritten_statement.sql(dialect="postgres")


def _serialize_row_value(val: Any) -> Any:
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, dict):
        return {k: _serialize_row_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize_row_value(item) for item in val]
    return val


async def execute_safe_sql(
    query: str,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_type: Optional[str] = "analytics",
    timeout_s: int = DEFAULT_STATEMENT_TIMEOUT_S,
    max_output_chars: int = DEFAULT_MAX_CHARS,
) -> Dict[str, Any]:
    """Validate, rewrite and execute query against database in read-only transaction."""
    if not tenant_id:
        # Never guess a tenant: every row this tool returns is scoped to one.
        return {"success": False, "error": "No tenant for this query; refusing to run it."}

    try:
        rewritten_sql = validate_and_rewrite_query(query, tenant_id=tenant_id, agent_type=agent_type)
    except ValueError as val_err:
        logger.warning("Safe SQL validation rejected: %s", val_err)
        return {"success": False, "error": str(val_err)}
    except Exception as exc:
        logger.exception("Unexpected error rewriting SQL: %s", exc)
        return {"success": False, "error": f"Failed to parse query: {exc}"}

    try:
        async with session_scope() as session:
            # Enforce read-only and statement timeout for the transaction
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_s)}s'"))

            result = await session.execute(text(rewritten_sql))
            rows = result.mappings().all()

            columns = list(result.keys()) if rows else []
            data_rows = []
            for r in rows:
                data_rows.append({k: _serialize_row_value(v) for k, v in r.items()})

            data = {
                "success": True,
                "row_count": len(data_rows),
                "columns": columns,
                "rows": data_rows,
            }

            # Budget check
            rendered = json.dumps(data, default=str)
            if len(rendered) > max_output_chars:
                # Cap the rows to fit within max_output_chars
                capped_rows = data_rows[: min(len(data_rows), 50)]
                data["rows"] = capped_rows
                data["truncated"] = True
                data["note"] = f"Output truncated to {len(capped_rows)} rows due to size limit."

            return {"success": True, "data": data}

    except Exception as exc:
        logger.error("Safe SQL execution error: %s (query: %s)", exc, rewritten_sql)
        return {"success": False, "error": f"Query execution failed: {str(exc)}"}
