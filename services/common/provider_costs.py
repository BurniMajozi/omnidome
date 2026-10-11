"""Supplier evidence and allocations; append-only, separate from customer charges."""
from sqlalchemy import text

DDL = [
    """CREATE TABLE IF NOT EXISTS platform_provider_receipts (
      id uuid PRIMARY KEY, provider text NOT NULL, reference text NOT NULL,
      normalized_reference text NOT NULL, amount numeric NOT NULL CHECK(amount>=0),
      currency text NOT NULL, period_start date NOT NULL, period_end date NOT NULL,
      actor_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      CHECK(period_end>period_start), UNIQUE(provider,normalized_reference))""",
    """CREATE TABLE IF NOT EXISTS platform_provider_cost_allocations (
      id uuid PRIMARY KEY, receipt_id uuid NOT NULL REFERENCES platform_provider_receipts(id),
      tenant_id uuid NOT NULL REFERENCES tenants(id), cost_event_id uuid NOT NULL UNIQUE REFERENCES platform_cost_events(id),
      amount numeric NOT NULL CHECK(amount>=0), quantity numeric NOT NULL CHECK(quantity>=0),
      unit text NOT NULL, reason text NOT NULL, actor_id uuid NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS platform_provider_allocation_voids (
      allocation_id uuid PRIMARY KEY REFERENCES platform_provider_cost_allocations(id),
      actor_id uuid NOT NULL, reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
]


async def ensure_schema(conn):
    for statement in DDL:
        await conn.execute(text(statement))
    for table in ("platform_provider_receipts", "platform_provider_cost_allocations", "platform_provider_allocation_voids"):
        await conn.execute(text(f"DROP TRIGGER IF EXISTS immutable_provider_cost ON {table}"))
        await conn.execute(text(f"CREATE TRIGGER immutable_provider_cost BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION platform_cost_immutable()"))
