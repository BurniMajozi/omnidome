"""Idempotent schema migrations for the admin service (seats, invites, role rank, sync state).

The same DDL is mirrored in config/master_schema.sql so a fresh database matches; this
module upgrades EXISTING databases (the repo has no migration tool, create_all never ALTERs).

Safe with several uvicorn workers: everything runs in ONE transaction that first takes
pg_advisory_xact_lock, so concurrent workers queue instead of deadlocking on ALTER TABLE.
"""
from __future__ import annotations

import logging
import os
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("admin.migrations")

MIGRATION_LOCK_KEY = 74190201
DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Default seat cap for NEW tenants (override with ADMIN_DEFAULT_SEAT_LIMIT). NULL means
# unlimited and is used only for the dev tenant / when a platform admin sets it explicitly.
DEFAULT_SEAT_LIMIT = int(os.getenv("ADMIN_DEFAULT_SEAT_LIMIT", "5"))

# Rank ladder used by the grant guardrails: an actor may grant only roles whose rank is
# <= the actor's own highest rank. Unknown/custom roles default to 10 (least privilege).
ROLE_RANKS = {
    "platform_admin": 100,
    "owner": 90,
    "org_admin": 80,
    "admin": 80,
    "tenant_admin": 80,
    "super_admin": 80,
    "manager": 50,
    "line_manager": 50,
    "hr_manager": 50,
    "hr_admin": 50,
    "hr": 50,
    "org_user": 10,
}

# System roles created for every tenant (name, description). org_admin / org_user already
# come from provision_tenant(); the rest are added by ensure_tenant_roles().
TENANT_SYSTEM_ROLES = [
    ("owner", "Tenant owner (billing, seats, ownership transfer)"),
    ("org_admin", "Organisation administrator"),
    ("manager", "Line manager"),
    ("hr_manager", "HR manager"),
    ("org_user", "Organisation user"),
]
ADMIN_CAPABLE_ROLES = ("owner", "org_admin")

DDL: List[str] = [
    "CREATE TABLE IF NOT EXISTS admin_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())",
    # --- tenants: seats + billing state -------------------------------------------------
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS seat_limit integer",
    f"ALTER TABLE tenants ALTER COLUMN seat_limit SET DEFAULT {DEFAULT_SEAT_LIMIT}",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS seat_price numeric(12,2)",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS billing_status text NOT NULL DEFAULT 'active'",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS owner_user_id uuid",
    # --- users: membership state (one tenant per email, so membership lives on users) ----
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_owner boolean NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS supabase_user_id uuid",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS supabase_synced boolean NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS supabase_synced_at timestamptz",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS supabase_sync_error text",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS deactivated_at timestamptz",
    # --- roles: rank ---------------------------------------------------------------------
    "ALTER TABLE roles ADD COLUMN IF NOT EXISTS role_rank integer NOT NULL DEFAULT 10",
    # --- seat_events (append-only) -------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS seat_events (
        id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id uuid,
        delta integer NOT NULL,
        reason text NOT NULL,
        actor_id uuid,
        active_after integer,
        pending_after integer,
        at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_seat_events_tenant_at ON seat_events(tenant_id, at)",
    """CREATE OR REPLACE FUNCTION seat_events_no_update() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'seat_events is append-only'; END; $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS trg_seat_events_no_update ON seat_events",
    """CREATE TRIGGER trg_seat_events_no_update BEFORE UPDATE ON seat_events
       FOR EACH ROW EXECUTE FUNCTION seat_events_no_update()""",
    # delete-blocking too (DDL runs under pg_advisory_xact_lock, so this is race-free)
    """CREATE OR REPLACE FUNCTION seat_events_no_delete() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'seat_events is append-only'; END; $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS trg_seat_events_no_delete ON seat_events",
    """CREATE TRIGGER trg_seat_events_no_delete BEFORE DELETE ON seat_events
       FOR EACH ROW EXECUTE FUNCTION seat_events_no_delete()""",
    # --- invites -------------------------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS invites (
        id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        email text NOT NULL,
        role_names text[] NOT NULL DEFAULT '{}',
        token_hash text NOT NULL,
        status text NOT NULL DEFAULT 'pending',
        expires_at timestamptz NOT NULL,
        invited_by uuid,
        created_at timestamptz NOT NULL DEFAULT now(),
        accepted_at timestamptz,
        accepted_user_id uuid,
        revoked_at timestamptz,
        supabase_user_id uuid,
        supabase_created boolean NOT NULL DEFAULT false,
        CHECK (status IN ('pending','accepted','revoked','expired'))
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_invites_token_hash ON invites(token_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_invites_pending_email ON invites(tenant_id, lower(email)) WHERE status = 'pending'",
    "CREATE INDEX IF NOT EXISTS idx_invites_email ON invites(lower(email))",
    "CREATE INDEX IF NOT EXISTS idx_invites_tenant ON invites(tenant_id, status)",
    # --- audit_logs: append-only (no escape hatch; a superuser must drop the trigger to purge) ---
    """CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
       BEGIN RAISE EXCEPTION 'audit_logs is append-only (% not allowed)', TG_OP USING ERRCODE = 'insufficient_privilege'; END;
       $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs",
    """CREATE TRIGGER trg_audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs
       FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()""",
    "CREATE INDEX IF NOT EXISTS idx_users_supabase_unsynced ON users(supabase_synced) WHERE supabase_synced = false",
]


async def ensure_unique_lower_email(conn) -> bool:
    """Case-insensitive unique email. Skips (with a warning) while case-variant duplicates exist,
    so a bad row never blocks startup; nothing is deleted or merged automatically."""
    dupes = (
        await conn.execute(text("SELECT lower(email) AS e, count(*) FROM users GROUP BY lower(email) HAVING count(*) > 1 LIMIT 20"))
    ).fetchall()
    if dupes:
        logger.warning(
            "users_email_lower_key NOT created: %d duplicate lower(email) group(s) exist (e.g. %s); resolve them and restart",
            len(dupes), ", ".join(str(r[0]) for r in dupes[:3]),
        )
        return False
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (lower(email))"))
    return True


async def _once(conn, name: str, statements: List[str]) -> None:
    done = (await conn.execute(text("SELECT 1 FROM admin_migrations WHERE name = :n"), {"n": name})).first()
    if done:
        return
    for stmt in statements:
        await conn.execute(text(stmt))
    await conn.execute(text("INSERT INTO admin_migrations (name) VALUES (:n)"), {"n": name})
    logger.info("admin migration applied: %s", name)


async def ensure_tenant_roles(conn, tenant_id) -> None:
    """Create the system roles for one tenant (idempotent) and give them ranks and permissions."""
    for name, description in TENANT_SYSTEM_ROLES:
        await conn.execute(
            text(
                """
                INSERT INTO roles (tenant_id, name, scope, description, is_system, role_rank)
                VALUES (:t, :n, 'TENANT', :d, TRUE, :rank)
                ON CONFLICT (tenant_id, name) DO NOTHING
                """
            ),
            {"t": str(tenant_id), "n": name, "d": description, "rank": ROLE_RANKS[name]},
        )
        # provision_tenant() creates org_admin/org_user first, with the default rank
        await conn.execute(
            text("UPDATE roles SET role_rank = :rank WHERE tenant_id = :t AND name = :n AND is_system AND role_rank = 10 AND :rank <> 10"),
            {"t": str(tenant_id), "n": name, "rank": ROLE_RANKS[name]},
        )
    # owner mirrors org_admin's permissions; manager/hr_manager mirror org_user's
    for target, source in (("owner", "org_admin"), ("manager", "org_user"), ("hr_manager", "org_user")):
        await conn.execute(
            text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT t.id, rp.permission_id
                FROM roles t
                JOIN roles s ON s.tenant_id = t.tenant_id AND s.name = :src
                JOIN role_permissions rp ON rp.role_id = s.id
                WHERE t.tenant_id = :t AND t.name = :tgt
                ON CONFLICT DO NOTHING
                """
            ),
            {"t": str(tenant_id), "src": source, "tgt": target},
        )


async def _apply_ranks(conn) -> None:
    for name, rank in ROLE_RANKS.items():
        await conn.execute(
            text("UPDATE roles SET role_rank = :r WHERE name = :n AND role_rank = 10 AND :r <> 10"),
            {"n": name, "r": rank},
        )


async def run_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '20s'"))
        await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
        for stmt in DDL:
            await conn.execute(text(stmt))

        await ensure_unique_lower_email(conn)

        # One-shot backfills, each recorded so later edits are never overwritten.
        await _once(
            conn,
            "seat_limit_backfill",
            [
                # dev tenant stays unlimited (NULL); everyone else gets the default, but never
                # below the users they already have.
                f"""UPDATE tenants t SET seat_limit = GREATEST({DEFAULT_SEAT_LIMIT},
                       (SELECT count(*) FROM users u WHERE u.tenant_id = t.id AND u.is_active))
                    WHERE t.id <> '{DEV_TENANT_ID}'""",
                f"UPDATE tenants SET seat_limit = NULL WHERE id = '{DEV_TENANT_ID}'",
            ],
        )

        await _apply_ranks(conn)
        tenants = (await conn.execute(text("SELECT id FROM tenants"))).fetchall()
        for (tid,) in tenants:
            await ensure_tenant_roles(conn, tid)
        await _apply_ranks(conn)

        # first org_admin of each tenant becomes owner (role + flag + tenants.owner_user_id)
        done = (await conn.execute(text("SELECT 1 FROM admin_migrations WHERE name='owner_backfill'"))).first()
        if not done:
            await conn.execute(
                text(
                    """
                    WITH first_admin AS (
                        SELECT DISTINCT ON (ur.tenant_id) ur.tenant_id, ur.user_id
                        FROM user_roles ur JOIN roles r ON r.id = ur.role_id AND r.name = 'org_admin'
                        JOIN users u ON u.id = ur.user_id AND u.tenant_id = ur.tenant_id AND u.is_active
                        WHERE ur.tenant_id IS NOT NULL
                        ORDER BY ur.tenant_id, ur.assigned_at ASC, ur.id
                    )
                    UPDATE users u SET is_owner = TRUE FROM first_admin f WHERE u.id = f.user_id
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    UPDATE tenants t SET owner_user_id = u.id FROM users u
                    WHERE u.tenant_id = t.id AND u.is_owner AND t.owner_user_id IS NULL
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO user_roles (user_id, role_id, tenant_id)
                    SELECT u.id, r.id, u.tenant_id FROM users u
                    JOIN roles r ON r.tenant_id = u.tenant_id AND r.name = 'owner'
                    WHERE u.is_owner
                    ON CONFLICT DO NOTHING
                    """
                )
            )
            await conn.execute(text("INSERT INTO admin_migrations (name) VALUES ('owner_backfill')"))

        # Existing active users hold a seat: record it once so seat_events starts consistent.
        done = (await conn.execute(text("SELECT 1 FROM admin_migrations WHERE name='seat_events_backfill'"))).first()
        if not done:
            await conn.execute(
                text(
                    """
                    INSERT INTO seat_events (tenant_id, user_id, delta, reason, active_after, pending_after)
                    SELECT u.tenant_id, u.id, 1, 'backfill',
                           (SELECT count(*) FROM users x WHERE x.tenant_id = u.tenant_id AND x.is_active), 0
                    FROM users u WHERE u.tenant_id IS NOT NULL AND u.is_active
                    """
                )
            )
            await conn.execute(text("INSERT INTO admin_migrations (name) VALUES ('seat_events_backfill')"))
    logger.info("admin migrations complete")
