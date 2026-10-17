"""Email conversation state, mailbox access, audit trail and event publishing for the AgentMail integration.

Everything here runs inside the caller's transaction (the one that stored the message), so a thread row and a
domain event exist if and only if the email row committed. SQL is raw and idempotent (CREATE TABLE IF NOT EXISTS):
this service has no migrations tooling and create_all() never ALTERs existing tables.

Tables (all tenant-scoped, every query filters tenant_id):
  email_threads        one row per (mailbox, provider thread): status, owner, linked customer/lead/ticket, counters
  agent_mailbox_access per-mailbox access: shared (default; roles by the mailbox's area) or personal (one owner)
  email_audit_log      who/what read, drafted, sent or flagged email, and what was ingested

Events (services/common/event_bus, source "communication"; payloads carry a REDACTED preview, never the full body,
and `untrusted: true`; consumers fetch the full thread through the API where access is checked):
  email.received       inbound message stored          (idempotency key: email.received:<provider message id>)
  email.sent           outbound message accepted by the provider
  email.send_failed    outbound message the provider refused
  email.delivery_failed  provider reported bounce / complaint / rejection for something we sent
  email.thread_status_changed  a person or agent closed / reopened / reassigned a thread
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text

from services.common import email_safety as ES

logger = logging.getLogger("communication.mail_state")
SOURCE = "communication"

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS email_threads (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        mailbox_id UUID NOT NULL,
        thread_key VARCHAR(255) NOT NULL,
        provider_thread_id VARCHAR(255),
        subject VARCHAR(500) NOT NULL DEFAULT '',
        status VARCHAR(30) NOT NULL DEFAULT 'needs_response',
        owner_user_id UUID,
        counterpart VARCHAR(255),
        customer_id UUID,
        lead_id UUID,
        ticket_id UUID,
        message_count INTEGER NOT NULL DEFAULT 0,
        inbound_count INTEGER NOT NULL DEFAULT 0,
        last_message_at TIMESTAMPTZ,
        last_inbound_at TIMESTAMPTZ,
        last_outbound_at TIMESTAMPTZ,
        closed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT uq_email_threads_key UNIQUE (tenant_id, mailbox_id, thread_key)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_email_threads_status ON email_threads (tenant_id, status, last_inbound_at)",
    "CREATE INDEX IF NOT EXISTS ix_email_threads_owner ON email_threads (tenant_id, owner_user_id)",
    """CREATE TABLE IF NOT EXISTS agent_mailbox_access (
        mailbox_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        kind VARCHAR(20) NOT NULL DEFAULT 'shared',
        owner_user_id UUID,
        required_roles TEXT[] NOT NULL DEFAULT '{}',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_mailbox_access_kind CHECK (kind IN ('shared', 'personal'))
    )""",
    "CREATE INDEX IF NOT EXISTS ix_agent_mailbox_access_tenant ON agent_mailbox_access (tenant_id)",
    """CREATE TABLE IF NOT EXISTS email_audit_log (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        actor_id UUID,
        actor_kind VARCHAR(20) NOT NULL DEFAULT 'system',
        action VARCHAR(40) NOT NULL,
        email_id UUID,
        thread_key VARCHAR(255),
        detail JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_email_audit_tenant_time ON email_audit_log (tenant_id, created_at DESC)",
    # webhook retries, polling and the 'message.sent' webhook can race: the database has the last word
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_emails_provider_msg ON agent_emails (tenant_id, direction, message_id) "
    "WHERE message_id IS NOT NULL",
)

_SCHEMA_LOCK = 74_210_031


async def ensure_schema() -> None:
    """Idempotent; never fails startup (a step that cannot run is logged and the feature degrades)."""
    from services.common.db import get_async_engine
    try:
        async with get_async_engine().begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SCHEMA_LOCK})
            for stmt in SCHEMA_STATEMENTS:
                try:
                    async with conn.begin_nested():
                        await conn.execute(text(stmt))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("email schema step failed (%s): %s", " ".join(stmt.split())[:60], exc)
            try:
                from services.common.event_bus import ensure_schema as ensure_bus
                async with conn.begin_nested():
                    await ensure_bus(conn)
            except Exception as exc:  # noqa: BLE001
                logger.warning("event bus schema unavailable: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not apply email schema: %s", exc)


# ── Mailbox access ───────────────────────────────────────────────────────────

# agent_mailboxes.agent_type -> the panel whose `<panel>.read` permission opens it (same map as the knowledge digest)
AREA_BY_AGENT = {"support": "support", "sales": "sales", "billing": "billing", "collections": "billing",
                 "retention": "retention", "marketing": "marketing", "hr": "hr", "finance": "finance",
                 "compliance": "compliance", "customer_facing": "support", "call_center": "call_center",
                 "network": "network", "inventory": "inventory"}
ADMIN_ROLES = frozenset({"platform_admin", "owner", "org_admin", "admin", "tenant_admin", "super_admin"})


def area_permission(agent_type: Any) -> str:
    area = AREA_BY_AGENT.get(str(agent_type or "").lower())
    return f"{area}.read" if area else "communication.admin"


def can_read_mailbox(*, user_id: Any, roles: Iterable[str], permissions: Iterable[str], is_platform_admin: bool,
                     agent_type: Any, access: Optional[dict]) -> bool:
    """The single rule for reading a mailbox's mail (API, agent tools and the index mirror it).

    personal  -> its owner only (admins included; the mailbox is a person's, not the team's)
    shared    -> tenant/platform admins; then, when the mailbox lists required_roles, holders of one of those roles; otherwise
                 anyone holding `<area>.read|write|admin` for the mailbox's area (or communication.admin).
    """
    access = access or {}
    if access.get("kind") == "personal":
        owner = access.get("owner_user_id")
        return bool(owner and user_id and str(owner) == str(user_id))
    rs = {str(r).lower() for r in roles or []}
    perms = {str(p).lower() for p in permissions or []}
    if is_platform_admin or rs & ADMIN_ROLES:
        return True
    wanted = {str(r).lower() for r in access.get("required_roles") or []}
    if wanted:                       # an explicit role list replaces the area permission (the knowledge index does the same)
        return bool(rs & wanted)
    area = AREA_BY_AGENT.get(str(agent_type or "").lower())
    if "communication.admin" in perms or "mail.admin" in perms:
        return True
    if area:
        return bool(perms & {f"{area}.read", f"{area}.write", f"{area}.admin", f"{area}.manage"})
    return False


async def load_access(session, tenant_id, mailbox_ids: Iterable[Any]) -> dict[str, dict]:
    ids = sorted({str(m) for m in mailbox_ids})
    if not ids:
        return {}
    async with session.begin_nested():
        rows = (await session.execute(text(
            "SELECT mailbox_id::text AS mailbox_id, kind, owner_user_id::text AS owner_user_id, required_roles "
            "FROM agent_mailbox_access WHERE tenant_id = CAST(:t AS uuid) AND mailbox_id = ANY(CAST(:m AS uuid[]))"),
            {"t": str(tenant_id), "m": ids})).mappings().all()
    return {r["mailbox_id"]: dict(r) for r in rows}


async def set_access(session, tenant_id, mailbox_id, *, kind: str, owner_user_id: Any = None, required_roles: Iterable[str] = ()) -> None:
    if kind == "personal" and not owner_user_id:
        raise ValueError("a personal mailbox needs an owner")
    await session.execute(text(
        "INSERT INTO agent_mailbox_access (mailbox_id, tenant_id, kind, owner_user_id, required_roles, updated_at) "
        "VALUES (CAST(:m AS uuid), CAST(:t AS uuid), :k, CAST(:o AS uuid), CAST(:r AS text[]), now()) "
        "ON CONFLICT (mailbox_id) DO UPDATE SET kind = EXCLUDED.kind, owner_user_id = EXCLUDED.owner_user_id, "
        "required_roles = EXCLUDED.required_roles, updated_at = now()"),
        {"m": str(mailbox_id), "t": str(tenant_id), "k": kind, "o": str(owner_user_id) if owner_user_id else None,
         "r": [str(r).lower() for r in required_roles]})


# ── Audit trail ──────────────────────────────────────────────────────────────

async def audit(session, tenant_id, action: str, *, actor_id: Any = None, actor_kind: str = "system",
                email_id: Any = None, thread_key: Optional[str] = None, detail: Optional[dict] = None) -> None:
    """Append one audit row; never raises (an unavailable audit table must not block mail)."""
    try:
        async with session.begin_nested():
            await session.execute(text(
                "INSERT INTO email_audit_log (id, tenant_id, actor_id, actor_kind, action, email_id, thread_key, detail) "
                "VALUES (:id, CAST(:t AS uuid), CAST(:a AS uuid), :k, :act, CAST(:e AS uuid), :th, CAST(:d AS jsonb))"),
                {"id": uuid.uuid4(), "t": str(tenant_id), "a": str(actor_id) if actor_id else None, "k": actor_kind,
                 "act": action[:40], "e": str(email_id) if email_id else None, "th": thread_key,
                 "d": json.dumps(detail or {}, default=str)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("email audit write failed (%s): %s", action, exc)


# ── Linking ──────────────────────────────────────────────────────────────────

async def resolve_links(session, tenant_id, address: str) -> dict:
    """customer_id / lead_id whose email equals `address` (case-insensitive), tenant-scoped. Empty when unknown."""
    addr = ES.bare_address(address)
    out: dict[str, Optional[str]] = {"customer_id": None, "lead_id": None}
    if not addr or "@" not in addr:
        return out
    for key, table in (("customer_id", "customers"), ("lead_id", "leads")):
        try:
            async with session.begin_nested():
                row = (await session.execute(text(
                    f"SELECT id::text FROM {table} WHERE tenant_id = CAST(:t AS uuid) AND lower(email) = :e "
                    "ORDER BY created_at DESC LIMIT 1"), {"t": str(tenant_id), "e": addr})).first()
            out[key] = row[0] if row else None
        except Exception as exc:  # noqa: BLE001 - table absent / different shape: unlinked, not broken
            logger.debug("link lookup on %s skipped: %s", table, exc)
    return out


# ── Thread state ─────────────────────────────────────────────────────────────

def thread_key_of(headers: Optional[dict], subject: Any) -> str:
    return ES.thread_key_for((headers or {}).get("thread_id"), subject)


def counterpart_of(direction: str, sender: str, recipient: str) -> str:
    return ES.bare_address(sender if direction == "inbound" else recipient)[:255]


_UPSERT_THREAD = """
INSERT INTO email_threads (id, tenant_id, mailbox_id, thread_key, provider_thread_id, subject, status, counterpart,
    customer_id, lead_id, message_count, inbound_count, last_message_at, last_inbound_at, last_outbound_at)
VALUES (:id, CAST(:t AS uuid), CAST(:mb AS uuid), :key, :pid, :subject, :status, :cp,
    CAST(:cust AS uuid), CAST(:lead AS uuid), 1, :inb, :ts, :ts_in, :ts_out)
ON CONFLICT (tenant_id, mailbox_id, thread_key) DO UPDATE SET
    status = CASE WHEN CAST(:direction AS text) = 'inbound' THEN 'needs_response'
                  WHEN NOT CAST(:sent_ok AS boolean) THEN email_threads.status
                  WHEN email_threads.status = 'closed' THEN 'closed'
                  ELSE 'awaiting_customer' END,
    closed_at = CASE WHEN CAST(:direction AS text) = 'inbound' THEN NULL ELSE email_threads.closed_at END,
    message_count = email_threads.message_count + 1,
    inbound_count = email_threads.inbound_count + EXCLUDED.inbound_count,
    last_message_at = GREATEST(email_threads.last_message_at, EXCLUDED.last_message_at),
    last_inbound_at = GREATEST(email_threads.last_inbound_at, EXCLUDED.last_inbound_at),
    last_outbound_at = GREATEST(email_threads.last_outbound_at, EXCLUDED.last_outbound_at),
    counterpart = COALESCE(email_threads.counterpart, EXCLUDED.counterpart),
    customer_id = COALESCE(email_threads.customer_id, EXCLUDED.customer_id),
    lead_id = COALESCE(email_threads.lead_id, EXCLUDED.lead_id),
    updated_at = now()
RETURNING id::text AS id, status, message_count, owner_user_id::text AS owner_user_id, customer_id::text AS customer_id,
          lead_id::text AS lead_id, ticket_id::text AS ticket_id, (xmax = 0) AS created
"""


async def apply_message(session, email: Any) -> dict:
    """Fold one newly stored email (ORM row or equivalent) into its thread. Returns the thread summary."""
    direction = str(email.direction)
    sent_ok = str(email.status) != "failed"
    headers = email.headers or {}
    key = thread_key_of(headers, email.subject)
    cp = counterpart_of(direction, email.sender, email.recipient)
    links = await resolve_links(session, email.tenant_id, cp) if cp else {"customer_id": None, "lead_id": None}
    ts = email.created_at or datetime.now(timezone.utc)
    status0 = ES.next_status(None, direction, sent_ok=sent_ok)
    row = (await session.execute(text(_UPSERT_THREAD), {
        "id": uuid.uuid4(), "t": str(email.tenant_id), "mb": str(email.mailbox_id), "key": key,
        "pid": headers.get("thread_id"), "subject": str(email.subject or "")[:500], "status": status0, "cp": cp or None,
        "cust": links["customer_id"], "lead": links["lead_id"], "inb": 1 if direction == "inbound" else 0,
        "ts": ts, "ts_in": ts if direction == "inbound" else None,
        "ts_out": ts if (direction == "outbound" and sent_ok) else None,
        "direction": direction, "sent_ok": sent_ok})).mappings().first()
    return {**dict(row), "thread_key": key}


def _addr_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v)[:255] for v in (value or [])][:20]


def event_payload(email: Any, mailbox: Any, thread: dict, *, extra: Optional[dict] = None) -> dict:
    headers = email.headers or {}
    body = ES.prepare_body(email.body_text, limit=500)
    flagged = ES.detect_injection(email.subject, email.body_text) if str(email.direction) == "inbound" else []
    payload = {
        "email_id": str(email.id), "thread_id": thread.get("id") or thread["thread_key"], "thread_key": thread["thread_key"], "mailbox_id": str(email.mailbox_id),
        "mailbox_address": getattr(mailbox, "email_address", None), "agent_type": getattr(mailbox, "agent_type", None),
        "message_id": email.message_id, "direction": str(email.direction),
        "in_reply_to": headers.get("in_reply_to"), "is_reply": bool(headers.get("in_reply_to")) or str(email.subject or "").lower().startswith("re:"),
        "subject": str(email.subject or "")[:300], "body_preview": body,
        "has_attachments": bool(headers.get("attachments")),
        "thread_status": thread.get("status"), "message_count": thread.get("message_count"),
        "customer_id": thread.get("customer_id"), "lead_id": thread.get("lead_id"), "ticket_id": thread.get("ticket_id"),
        "untrusted": True, "injection_suspected": flagged,
    }
    if str(email.direction) == "inbound":
        payload.update({"from_address": ES.bare_address(email.sender), "from_name": ES.display_name(email.sender, ""),
                        "from_domain": ES.address_domain(email.sender), "to_address": ES.bare_address(email.recipient)})
    else:
        payload.update({"from_address": ES.bare_address(email.sender),
                        "to_addresses": _addr_list(headers.get("to") or email.recipient), "status": str(email.status),
                        "error": str(headers.get("error"))[:200] if headers.get("error") else None})
    payload.update(extra or {})
    return payload


async def record_and_publish(session, email: Any, mailbox: Any, *, emit: bool = True, source_via: str = "api") -> Optional[dict]:
    """Thread upsert + audit + event, in a savepoint: a failure here is logged and never loses the stored email."""
    try:
        async with session.begin_nested():
            thread = await apply_message(session, email)
            event_type = None
            if emit:
                if str(email.direction) == "inbound":
                    event_type = "email.received"
                elif str(email.status) == "failed":
                    event_type = "email.send_failed"
                else:
                    event_type = "email.sent"
                from services.common import event_bus
                payload = event_payload(email, mailbox, thread, extra={"via": source_via})
                await event_bus.publish(
                    session, email.tenant_id, event_type, payload, source=SOURCE,
                    subject=("email_thread", thread["thread_key"]),
                    idempotency_key=f"{event_type}:{email.message_id}" if email.message_id else None)
                if payload["injection_suspected"]:
                    await audit(session, email.tenant_id, "injection_flagged", actor_kind="system", email_id=email.id,
                                thread_key=thread["thread_key"], detail={"patterns": payload["injection_suspected"]})
            await audit(session, email.tenant_id, "ingested" if str(email.direction) == "inbound" else "recorded_outbound",
                        actor_kind="system", email_id=email.id, thread_key=thread["thread_key"],
                        detail={"via": source_via, "event": event_type, "status": str(email.status)})
        return thread
    except Exception as exc:  # noqa: BLE001
        logger.error("thread/event bookkeeping failed for email %s: %s", getattr(email, "id", "?"), exc)
        return None


async def publish_delivery_failure(session, tenant_id, email: Any, mailbox: Any, event_type: str, detail: Any) -> None:
    try:
        async with session.begin_nested():
            from services.common import event_bus
            thread = {"thread_key": thread_key_of(email.headers, email.subject), "status": None}
            payload = event_payload(email, mailbox, thread, extra={"provider_event": event_type})
            await event_bus.publish(session, tenant_id, "email.delivery_failed", payload, source=SOURCE,
                                    subject=("email_thread", thread["thread_key"]),
                                    idempotency_key=f"email.delivery_failed:{email.message_id}:{event_type}")
    except Exception as exc:  # noqa: BLE001
        logger.error("delivery-failure event failed: %s", exc)


async def rebuild_threads(session, tenant_id) -> dict:
    """One-off / repeatable backfill: derive email_threads from the stored emails. Idempotent (values are SET from
    the full history, not incremented) and emits no events, so replaying history never re-triggers automations.
    A thread a person closed stays closed unless a newer inbound message exists."""
    rows = (await session.execute(text(
        "SELECT e.id, e.mailbox_id::text AS mailbox_id, e.direction, e.sender, e.recipient, e.subject, e.status, e.headers, e.created_at "
        "FROM agent_emails e WHERE e.tenant_id = CAST(:t AS uuid) AND e.status <> 'deleted' ORDER BY e.created_at, e.id"),
        {"t": str(tenant_id)})).mappings().all()
    threads: dict[tuple, dict] = {}
    for r in rows:
        key = thread_key_of(r["headers"], r["subject"])
        t = threads.setdefault((r["mailbox_id"], key), {
            "subject": r["subject"], "pid": (r["headers"] or {}).get("thread_id"), "count": 0, "inb": 0, "last": None,
            "last_in": None, "last_out": None, "status": None, "cp": None})
        d, ok = r["direction"], r["status"] != "failed"
        t["count"] += 1
        t["inb"] += 1 if d == "inbound" else 0
        t["last"] = r["created_at"]
        if d == "inbound":
            t["last_in"] = r["created_at"]
        elif ok:
            t["last_out"] = r["created_at"]
        t["status"] = ES.next_status(t["status"], d, sent_ok=ok)
        t["cp"] = t["cp"] or counterpart_of(d, r["sender"], r["recipient"])
    n = 0
    for (mb, key), t in threads.items():
        links = await resolve_links(session, tenant_id, t["cp"]) if t["cp"] else {"customer_id": None, "lead_id": None}
        await session.execute(text(
            "INSERT INTO email_threads (id, tenant_id, mailbox_id, thread_key, provider_thread_id, subject, status, counterpart, "
            "customer_id, lead_id, message_count, inbound_count, last_message_at, last_inbound_at, last_outbound_at) "
            "VALUES (:id, CAST(:t AS uuid), CAST(:mb AS uuid), :key, :pid, :subject, :status, :cp, CAST(:cust AS uuid), "
            "CAST(:lead AS uuid), :cnt, :inb, :last, :last_in, :last_out) "
            "ON CONFLICT (tenant_id, mailbox_id, thread_key) DO UPDATE SET message_count = EXCLUDED.message_count, "
            "inbound_count = EXCLUDED.inbound_count, last_message_at = EXCLUDED.last_message_at, "
            "last_inbound_at = EXCLUDED.last_inbound_at, last_outbound_at = EXCLUDED.last_outbound_at, "
            "status = CASE WHEN email_threads.status = 'closed' AND (EXCLUDED.last_inbound_at IS NULL OR "
            "email_threads.closed_at IS NULL OR EXCLUDED.last_inbound_at <= email_threads.closed_at) THEN 'closed' ELSE EXCLUDED.status END, "
            "customer_id = COALESCE(email_threads.customer_id, EXCLUDED.customer_id), "
            "lead_id = COALESCE(email_threads.lead_id, EXCLUDED.lead_id), updated_at = now()"),
            {"id": uuid.uuid4(), "t": str(tenant_id), "mb": mb, "key": key, "pid": t["pid"], "subject": str(t["subject"] or "")[:500],
             "status": t["status"] or ES.NEEDS_RESPONSE, "cp": t["cp"] or None, "cust": links["customer_id"], "lead": links["lead_id"],
             "cnt": t["count"], "inb": t["inb"], "last": t["last"], "last_in": t["last_in"], "last_out": t["last_out"]})
        n += 1
    return {"threads": n, "messages": len(rows)}
