-- Migration: rename journey_engine's router_return_status enum type out of a
-- real, discovered-in-production enum-name collision with
-- services/billing/models.py's own, unrelated router_return_status type
-- (a hardware RMA/logistics workflow: courier_booked/in_transit/inspected/
-- refund_issued -- completely different values from journey_engine's
-- not_required/pending/scheduled/collected/returned/lost/written_off).
--
-- Whichever service's create_type=True ran first silently "won" the shared
-- type name; journey_engine's own enum values had never actually applied
-- in any DB that also ran billing's migration first (same root cause as
-- 20260923_network_radius_accounts_rename.sql, one layer down: an enum
-- type name collision instead of a table name collision). Does NOT touch
-- billing's existing router_return_status type at all. The column name on
-- cancellation_workflows (router_return_status) is unchanged -- only the
-- underlying Postgres type it references changes.
--
-- Safe to run: cancellation_workflows is empty in every environment this
-- has been tested in (the enum mismatch meant no insert into it could ever
-- have succeeded). If a shared DB somehow already has rows, back them up
-- first -- this statement will fail on any row whose (billing-shaped) value
-- isn't also a valid member of the new type.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'journey_router_return_status') THEN
        CREATE TYPE journey_router_return_status AS ENUM (
            'not_required', 'pending', 'scheduled', 'collected', 'returned', 'lost', 'written_off'
        );
    END IF;
END $$;

ALTER TABLE cancellation_workflows
    ALTER COLUMN router_return_status DROP DEFAULT,
    ALTER COLUMN router_return_status TYPE journey_router_return_status
        USING router_return_status::text::journey_router_return_status,
    ALTER COLUMN router_return_status SET DEFAULT 'not_required';
