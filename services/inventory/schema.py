"""Startup schema reconciliation for the inventory service.

``Base.metadata.create_all`` never ALTERs an existing table, and the LIVE ``inventory_products`` /
``inventory_levels`` were created by config/master_schema.sql in an older, different shape
(no barcode / unit_of_measure / is_active / range_id ..., levels without reserved / available,
global ``UNIQUE(sku)``, FKs into the legacy ``product_categories`` / ``warehouses`` tables). The
decision (owner, 2026-10) is to migrate the LIVE tables to the ORM, not the other way round.

Everything here is idempotent and runs under one Postgres advisory lock (several uvicorn workers start
at once), wrapped in ``run_with_db_retry`` by ``init_schema``. Nothing in here drops data:

* columns are added with ``ADD COLUMN IF NOT EXISTS`` + defaults (existing rows are back-filled by the
  default);
* legacy foreign keys that point at the wrong parent table are dropped and replaced (``NOT VALID`` so
  rows written before the change are not re-checked);
* unique indexes and NOT NULLs that could fail on pre-existing dirty data are created only when the
  data allows it - otherwise the offending count is LOGGED and the step is skipped (startup never fails);
* ``available`` becomes a GENERATED column (``soh - allocated - reserved``): one source of truth.

The pure parts (``migration_statements``, ``UNIQUE_INDEXES``, ``NOT_NULLS`` and the ``*_sql`` builders)
are unit-tested without a database.

Alembic: ``migrations/env.py`` still lists these two tables in EXCLUDED_TABLES. Alembic cannot be
turned on for them while this runtime migration owns their shape (two owners would fight), so the
exclusion is intentionally left and documented there.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Sequence, Tuple

logger = logging.getLogger("inventory.schema")

SCHEMA_LOCK_KEY = 0x1A7E_0010  # arbitrary constant; serialises startup DDL across workers


# ---------------------------------------------------------------------------
# Pure statement builders
# ---------------------------------------------------------------------------

def _add_columns(table: str, columns: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [(f"{table}.{name}", f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}") for name, ddl in columns]


def _drop_fks_to(table: str, legacy_parent: str) -> Tuple[str, str]:
    """Drop every FK on ``table`` that points at ``legacy_parent`` (no-op when none / table missing)."""
    return (
        f"{table}: drop FKs to legacy {legacy_parent}",
        f"""DO $$ DECLARE c text; BEGIN
  FOR c IN SELECT conname FROM pg_constraint
           WHERE conrelid = to_regclass('{table}') AND contype = 'f'
             AND confrelid = to_regclass('{legacy_parent}')
  LOOP
    EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', c);
  END LOOP;
END $$""",
    )


def _add_fk(table: str, name: str, column: str, ref_table: str, on_delete: str) -> Tuple[str, str]:
    """Add an FK when the parent exists and the constraint is absent. NOT VALID: old rows are not re-checked."""
    return (
        f"{table}: fk {name}",
        f"""DO $$ BEGIN
  IF to_regclass('{ref_table}') IS NOT NULL
     AND to_regclass('{table}') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}' AND conrelid = to_regclass('{table}'))
  THEN
    ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}) REFERENCES {ref_table}(id)
      ON DELETE {on_delete} NOT VALID;
  END IF;
END $$""",
    )


def _add_check(table: str, name: str, expr: str) -> Tuple[str, str]:
    return (
        f"{table}: check {name}",
        f"""DO $$ BEGIN
  IF to_regclass('{table}') IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}' AND conrelid = to_regclass('{table}'))
  THEN
    ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr}) NOT VALID;
  END IF;
END $$""",
    )


@dataclass(frozen=True)
class UniqueIndexSpec:
    name: str
    table: str
    columns: Tuple[str, ...]
    where: Optional[str] = None


@dataclass(frozen=True)
class NotNullSpec:
    table: str
    column: str


# Created only when no duplicate rows exist (otherwise skipped + logged; app-level checks still hold).
UNIQUE_INDEXES: Tuple[UniqueIndexSpec, ...] = (
    UniqueIndexSpec("uq_inventory_products_tenant_sku", "inventory_products", ("tenant_id", "sku")),
    UniqueIndexSpec("uq_inv_level_tenant_wh_product", "inventory_levels", ("tenant_id", "warehouse_id", "product_id")),
    UniqueIndexSpec("uq_stock_move_tenant_client_ref", "inventory_stock_movements", ("tenant_id", "client_ref"),
                    "client_ref IS NOT NULL"),
    UniqueIndexSpec("uq_gr_tenant_po_receipt_ref", "inventory_goods_receipts", ("tenant_id", "po_id", "receipt_ref"),
                    "receipt_ref IS NOT NULL"),
    UniqueIndexSpec("uq_gr_tenant_po_idempotency_key", "inventory_goods_receipts",
                    ("tenant_id", "po_id", "idempotency_key"), "idempotency_key IS NOT NULL"),
)

# Applied only when the column holds no NULLs (otherwise skipped + logged).
NOT_NULLS: Tuple[NotNullSpec, ...] = (
    NotNullSpec("inventory_products", "tenant_id"),
    NotNullSpec("inventory_levels", "tenant_id"),
    NotNullSpec("inventory_levels", "warehouse_id"),
    NotNullSpec("inventory_levels", "product_id"),
)


def duplicate_count_sql(spec: UniqueIndexSpec) -> str:
    cols = ", ".join(spec.columns)
    where = f" WHERE {spec.where}" if spec.where else ""
    return f"SELECT count(*) FROM (SELECT 1 FROM {spec.table}{where} GROUP BY {cols} HAVING count(*) > 1) d"


def unique_index_sql(spec: UniqueIndexSpec) -> str:
    cols = ", ".join(spec.columns)
    where = f" WHERE {spec.where}" if spec.where else ""
    return f"CREATE UNIQUE INDEX IF NOT EXISTS {spec.name} ON {spec.table} ({cols}){where}"


def null_count_sql(spec: NotNullSpec) -> str:
    return f"SELECT count(*) FROM {spec.table} WHERE {spec.column} IS NULL"


def not_null_sql(spec: NotNullSpec) -> str:
    return f"ALTER TABLE {spec.table} ALTER COLUMN {spec.column} SET NOT NULL"


def migration_statements() -> List[Tuple[str, str]]:
    """Ordered (label, sql) list; every statement is safe to run on every startup.

    Runs AFTER create_all (so every referenced inventory_* table exists on a fresh or legacy DB).
    """
    s: List[Tuple[str, str]] = []

    # Preserve IDs and data before replacing the legacy parent foreign keys.
    s.append(("legacy warehouse parents", """DO $$ BEGIN
      IF to_regclass('warehouses') IS NOT NULL THEN
        INSERT INTO inventory_warehouses (id, tenant_id, code, name, location, is_external, partner_name, is_active, created_at, updated_at)
        SELECT id, tenant_id, 'LEGACY-' || id::text, name, location, coalesce(is_external, false), partner_name, true, coalesce(created_at, now()), now()
        FROM warehouses WHERE tenant_id IS NOT NULL ON CONFLICT (id) DO NOTHING;
      END IF;
    END $$"""))
    s.append(("legacy category parents", """DO $$ BEGIN
      IF to_regclass('product_categories') IS NOT NULL THEN
        INSERT INTO inventory_service_types (id, tenant_id, code, name, sort_order, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), tenant_id, 'legacy-import', 'Imported categories', 0, true, now(), now()
        FROM product_categories WHERE tenant_id IS NOT NULL GROUP BY tenant_id
        ON CONFLICT (tenant_id, code) DO NOTHING;
        INSERT INTO inventory_product_categories (id, tenant_id, service_type_id, code, name, description, sort_order, is_active, created_at, updated_at)
        SELECT c.id, c.tenant_id, s.id, 'LEGACY-' || c.id::text, c.name, c.description, 0, true, coalesce(c.created_at, now()), now()
        FROM product_categories c JOIN inventory_service_types s ON s.tenant_id = c.tenant_id AND s.code = 'legacy-import'
        ON CONFLICT (id) DO NOTHING;
      END IF;
    END $$"""))

    # -- inventory_products: legacy master_schema shape -> ORM shape --------------------------------
    s += _add_columns("inventory_products", [
        ("range_id", "UUID"),
        ("service_type_id", "UUID"),
        ("preferred_supplier_id", "UUID"),
        ("barcode", "VARCHAR(64)"),
        ("unit_of_measure", "VARCHAR(20) NOT NULL DEFAULT 'EA'"),
        ("weight_kg", "NUMERIC(8,3)"),
        ("markup_pct", "NUMERIC(5,2) DEFAULT 0"),
        ("is_active", "BOOLEAN NOT NULL DEFAULT TRUE"),
        ("is_serialized", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("updated_at", "TIMESTAMPTZ NOT NULL DEFAULT now()"),
    ])
    s.append(("inventory_products: drop legacy global UNIQUE(sku)", """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint
             WHERE conname = 'inventory_products_sku_key' AND conrelid = to_regclass('inventory_products'))
  THEN
    ALTER TABLE inventory_products DROP CONSTRAINT inventory_products_sku_key;
  END IF;
END $$"""))
    s.append(_drop_fks_to("inventory_products", "product_categories"))
    s.append(_add_fk("inventory_products", "inventory_products_category_id_inv_fkey", "category_id",
                     "inventory_product_categories", "SET NULL"))
    s.append(_add_fk("inventory_products", "inventory_products_range_id_fkey", "range_id",
                     "inventory_product_ranges", "SET NULL"))
    s.append(_add_fk("inventory_products", "inventory_products_service_type_id_fkey", "service_type_id",
                     "inventory_service_types", "SET NULL"))
    s.append(_add_fk("inventory_products", "inventory_products_preferred_supplier_id_fkey", "preferred_supplier_id",
                     "inventory_suppliers", "SET NULL"))
    s.append(("inventory_products: barcode index",
              "CREATE INDEX IF NOT EXISTS ix_inventory_products_barcode ON inventory_products (barcode)"))
    s.append(("inventory_products: tenant index",
              "CREATE INDEX IF NOT EXISTS ix_inventory_products_tenant_id ON inventory_products (tenant_id)"))

    # -- inventory_levels ----------------------------------------------------------------------------
    # Semantics: soh / allocated / reserved are stored; available = soh - allocated - reserved is GENERATED.
    s += _add_columns("inventory_levels", [
        ("reserved", "INTEGER NOT NULL DEFAULT 0"),
        ("max_threshold", "INTEGER DEFAULT 100"),
        ("reorder_point", "INTEGER DEFAULT 20"),
        ("reorder_quantity", "INTEGER DEFAULT 50"),
    ])
    s.append(("inventory_levels: available -> generated column", """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = 'inventory_levels'
               AND column_name = 'available' AND is_generated <> 'ALWAYS')
  THEN
    DROP INDEX IF EXISTS ix_inv_level_low_stock;
    ALTER TABLE inventory_levels DROP COLUMN available;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema = current_schema() AND table_name = 'inventory_levels'
                   AND column_name = 'available')
  THEN
    ALTER TABLE inventory_levels ADD COLUMN available INTEGER GENERATED ALWAYS AS (soh - allocated - reserved) STORED;
  END IF;
END $$"""))
    s.append(_drop_fks_to("inventory_levels", "warehouses"))
    s.append(_add_fk("inventory_levels", "inventory_levels_warehouse_id_inv_fkey", "warehouse_id",
                     "inventory_warehouses", "CASCADE"))
    s.append(_add_check("inventory_levels", "ck_inv_level_soh_nonneg", "soh >= 0"))
    s.append(_add_check("inventory_levels", "ck_inv_level_allocated_nonneg", "allocated >= 0"))
    s.append(_add_check("inventory_levels", "ck_inv_level_reserved_nonneg", "reserved >= 0"))
    s.append(_add_check("inventory_levels", "ck_inv_level_available_nonneg", "soh >= allocated + reserved"))
    s.append(("inventory_levels: low-stock index",
              "CREATE INDEX IF NOT EXISTS ix_inv_level_low_stock ON inventory_levels (tenant_id, available, reorder_point)"))
    s.append(("inventory_levels: tenant/product index",
              "CREATE INDEX IF NOT EXISTS ix_inv_level_tenant_product ON inventory_levels (tenant_id, product_id)"))

    # -- inventory_stock_movements (ORM uses from_/to_location_*; the old writer used from_/to_warehouse_id) ----
    s += _add_columns("inventory_stock_movements", [
        ("client_ref", "VARCHAR(128)"),
        ("reference", "VARCHAR(100)"),
        ("before_soh", "INTEGER"),
        ("after_soh", "INTEGER"),
        ("dest_before_soh", "INTEGER"),
        ("dest_after_soh", "INTEGER"),
    ])

    # -- purchase orders -----------------------------------------------------------------------------
    s.append(("inventory_purchase_orders: status enum -> varchar", """DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = 'inventory_purchase_orders'
               AND column_name = 'status' AND data_type = 'USER-DEFINED')
  THEN
    ALTER TABLE inventory_purchase_orders ALTER COLUMN status TYPE VARCHAR(30) USING status::text;
  END IF;
END $$"""))
    s += _add_columns("inventory_purchase_orders", [
        ("currency", "VARCHAR(3) NOT NULL DEFAULT 'ZAR'"),
        ("submitted_by", "UUID"),
        ("submitted_at", "TIMESTAMPTZ"),
        ("approved_at", "TIMESTAMPTZ"),
        ("approval_mode", "VARCHAR(10)"),
        ("approval_hash", "VARCHAR(64)"),
        ("rejection_reason", "TEXT"),
        ("sent_at", "TIMESTAMPTZ"),
        ("sent_to", "VARCHAR(320)"),
        ("sent_message_id", "VARCHAR(255)"),
        ("send_claimed_at", "TIMESTAMPTZ"),
        ("send_idempotency_key", "VARCHAR(128)"),
        ("cancelled_at", "TIMESTAMPTZ"),
    ])
    s.append(("inventory_purchase_orders: legacy 'submitted' -> 'pending_approval'",
              "UPDATE inventory_purchase_orders SET status = 'pending_approval' WHERE status = 'submitted'"))
    s.append(("inventory_purchase_orders: mark pre-signature approvals as legacy",
              "UPDATE inventory_purchase_orders SET approval_mode = 'legacy' "
              "WHERE status IN ('approved', 'partially_received', 'received') "
              "AND approval_mode IS NULL AND approval_hash IS NULL"))
    s += _add_columns("inventory_goods_receipts", [
        ("receipt_ref", "VARCHAR(128)"),
        ("idempotency_key", "VARCHAR(128)"),
        ("value_ex_vat_zar", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
        ("vat_zar", "NUMERIC(14,2) NOT NULL DEFAULT 0"),
    ])
    s += _add_columns("inventory_suppliers", [("spend_limit", "NUMERIC(14,2)")])
    return s


# ---------------------------------------------------------------------------
# Runner (dedupe-safe parts take injectable callables so they are testable without Postgres)
# ---------------------------------------------------------------------------

FetchCount = Callable[[str], Awaitable[int]]
RunDDL = Callable[[str], Awaitable[None]]


async def apply_unique_indexes(fetch_count: FetchCount, run_ddl: RunDDL,
                               specs: Sequence[UniqueIndexSpec] = UNIQUE_INDEXES) -> dict:
    """Create each unique index iff no duplicates exist; log and skip otherwise. Never raises."""
    out = {"created": [], "skipped_duplicates": [], "failed": []}
    for spec in specs:
        try:
            dups = await fetch_count(duplicate_count_sql(spec))
        except Exception as exc:  # noqa: BLE001 - table/column missing etc.
            logger.warning("unique index %s: duplicate check failed (%s: %s); skipped", spec.name, type(exc).__name__, exc)
            out["failed"].append(spec.name)
            continue
        if dups:
            logger.warning("unique index %s on %s%s NOT created: %d duplicate group(s) exist; "
                           "de-duplicate the rows and restart (application-level checks still apply)",
                           spec.name, spec.table, spec.columns, dups)
            out["skipped_duplicates"].append(spec.name)
            continue
        try:
            await run_ddl(unique_index_sql(spec))
            out["created"].append(spec.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("unique index %s could not be created: %s: %s", spec.name, type(exc).__name__, exc)
            out["failed"].append(spec.name)
    return out


async def apply_not_nulls(fetch_count: FetchCount, run_ddl: RunDDL, specs: Sequence[NotNullSpec] = NOT_NULLS) -> dict:
    out = {"applied": [], "skipped_nulls": [], "failed": []}
    for spec in specs:
        label = f"{spec.table}.{spec.column}"
        try:
            nulls = await fetch_count(null_count_sql(spec))
        except Exception as exc:  # noqa: BLE001
            logger.warning("NOT NULL %s: null check failed (%s); skipped", label, type(exc).__name__)
            out["failed"].append(label)
            continue
        if nulls:
            logger.warning("NOT NULL %s NOT applied: %d row(s) have NULL; fix the data and restart", label, nulls)
            out["skipped_nulls"].append(label)
            continue
        try:
            await run_ddl(not_null_sql(spec))
            out["applied"].append(label)
        except Exception as exc:  # noqa: BLE001
            logger.warning("NOT NULL %s could not be applied: %s: %s", label, type(exc).__name__, exc)
            out["failed"].append(label)
    return out


async def run_reconciliation(engine) -> dict:
    """Execute the statement list + guarded unique indexes / NOT NULLs on a Postgres engine.

    Each statement runs in its own transaction: one failing statement is logged and the rest still run.
    """
    from sqlalchemy import text

    failures: List[str] = []

    async def run_ddl(sql: str) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(sql))

    async def fetch_count(sql: str) -> int:
        async with engine.connect() as conn:
            return int((await conn.execute(text(sql))).scalar() or 0)

    for label, sql in migration_statements():
        try:
            await run_ddl(sql)
        except Exception as exc:  # noqa: BLE001
            failures.append(label)
            logger.error("inventory schema step failed [%s]: %s: %s", label, type(exc).__name__, str(exc)[:300])
    uniques = await apply_unique_indexes(fetch_count, run_ddl)
    not_nulls = await apply_not_nulls(fetch_count, run_ddl)
    return {"failed_steps": failures, "unique_indexes": uniques, "not_nulls": not_nulls}


async def init_schema(base) -> Optional[dict]:
    """create_all + reconciliation, under an advisory lock, retried until the DB is reachable."""
    from services.common.db import get_async_engine, run_with_db_retry
    from sqlalchemy import text

    async def _once() -> Optional[dict]:
        engine = get_async_engine()
        is_pg = engine.dialect.name == "postgresql"
        lock_conn = None
        try:
            if is_pg:
                lock_conn = await engine.connect()
                await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SCHEMA_LOCK_KEY})
            async with engine.begin() as conn:
                await conn.run_sync(base.metadata.create_all)
            if not is_pg:
                return None
            result = await run_reconciliation(engine)
            if (result["failed_steps"] or result["unique_indexes"]["failed"]
                    or result["unique_indexes"]["skipped_duplicates"]):
                raise RuntimeError(f"Inventory schema reconciliation is incomplete: {result}")
            logger.info("inventory schema reconciled: %s", result)
            return result
        finally:
            if lock_conn is not None:
                try:
                    await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEMA_LOCK_KEY})
                finally:
                    await lock_conn.close()

    return await run_with_db_retry(_once, logger=logger)
