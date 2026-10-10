"""Sources for the personalised layer and the Communication panel.

  personal_context   snapshot source: per-user PRIVATE cards (tasks, escalations, schedule, KPIs, approvals), recomputed on
                     every sweep (about every 2 minutes); unchanged text is never re-embedded, and the cards carry a short
                     `valid_to` that the indexer keeps extending only while the data is still being produced.
  mail_threads       the Communication panel's mailbox thread digest (agent_mailboxes / agent_emails). Derived on the fly
                     by deterministic grouping (normalised subject per mailbox), so no extra table and no hook into the
                     ingestion path are needed.

Same rules as sources.py / sources_ext.py: explicit column lists, explicit tenant filter, reads in a SAVEPOINT, missing
table => empty page, and reconcile refuses to tombstone anything when the table is missing.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.tenant_memory.knowledge import personal as P
from services.tenant_memory.knowledge.cards import builders_personal as BP
from services.tenant_memory.knowledge.cards import sources as S
from services.tenant_memory.knowledge.cards.sources import Page, Source

MAIL_WINDOW_DAYS = int(os.getenv("KNOWLEDGE_MAIL_WINDOW_DAYS", "90") or 90)
MAIL_RESCAN_HOURS = int(os.getenv("KNOWLEDGE_MAIL_RESCAN_HOURS", "6") or 6)
FLAG_KEYS = ("is_read", "agent_reply_sent", "unsubscribed", "suppressed", "do_not_contact", "legal_hold", "knowledge_forget")


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1", "yes")


async def _exists(session, table: str) -> bool:
    return await P._exists(session, table)


# ── personal context ────────────────────────────────────────────────────────

async def fetch_personal(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    now = datetime.now(timezone.utc)
    data = await P.gather(session, tenant, now)
    page = Page()
    for uid, d in sorted(data.items()):
        page.cards += BP.personal_cards(uid, d, now)
    page.rows = len(page.cards)
    return page


async def ids_personal(session, tenant: str) -> dict:
    now = datetime.now(timezone.utc)
    data = await P.gather(session, tenant, now)
    out: dict[str, set] = {t: set() for t in BP.PERSONAL_TYPES.values()}
    for uid, d in data.items():
        for c in BP.personal_cards(uid, d, now):
            out[c.source_type].add(c.source_id)
    return out


# ── mail threads ────────────────────────────────────────────────────────────

_EMAIL_COLS = ("e.id::text AS id, e.mailbox_id::text AS mailbox_id, e.direction, e.sender, e.recipient, e.subject, e.status, e.created_at, "
               "LEFT(e.body_text, 1200) AS body, jsonb_build_object(" +
               ", ".join(f"'{k}', e.headers->'{k}'" for k in FLAG_KEYS) + ") AS flags")


def _norm_flags(flags: Any) -> dict:
    return {k: _truthy(v) for k, v in (flags or {}).items()}


async def _suppressed_addresses(session, tenant: str, emails: list[dict]) -> set:
    if not await _exists(session, "marketing_suppressions"):
        return set()
    from services.common.suppression import normalize_email
    addrs = {normalize_email(e["sender"] if e["direction"] == "inbound" else e["recipient"]) for e in emails}
    addrs.discard("")
    if not addrs:
        return set()
    rows = await S._rows(session, "SELECT email_lower FROM marketing_suppressions WHERE tenant_id = CAST(:t AS uuid) "
                                  "AND email_lower = ANY(CAST(:a AS text[]))", {"t": tenant, "a": sorted(addrs)})
    return {r["email_lower"] for r in rows}


async def fetch_mail_threads(session, tenant: str, wm: Optional[dict], limit: int) -> Page:
    page = Page()
    if not await _exists(session, "agent_emails") or not await _exists(session, "agent_mailboxes"):
        return page
    since = f" AND e.created_at > now() - interval '{MAIL_WINDOW_DAYS} days'"
    ks, kp = S._keyset("e.created_at", "e.id::text", wm)
    new = await S._rows(session, f"SELECT e.id::text AS id, e.mailbox_id::text AS mailbox_id, e.subject, e.created_at AS ts FROM agent_emails e "
                                 f"WHERE e.tenant_id = CAST(:t AS uuid) AND e.status <> 'deleted'{since}{ks} ORDER BY e.created_at, e.id::text LIMIT :lim",
                        {"t": tenant, "lim": limit, **kp})
    S._track(page, new)
    touched = {(r["mailbox_id"], BP.thread_key(r["subject"])) for r in new}
    if wm and wm.get("last_ts"):                              # status/read changes carry no timestamp: re-check recent threads
        recent = await S._rows(session, "SELECT e.mailbox_id::text AS mailbox_id, e.subject FROM agent_emails e WHERE e.tenant_id = CAST(:t AS uuid) "
                                        f"AND e.status <> 'deleted' AND e.created_at > now() - interval '{MAIL_RESCAN_HOURS} hours' LIMIT :lim",
                               {"t": tenant, "lim": limit})
        touched |= {(r["mailbox_id"], BP.thread_key(r["subject"])) for r in recent}
    if not touched:
        return page
    mailbox_ids = sorted({m for m, _ in touched})
    rows = await S._rows(session, f"SELECT {_EMAIL_COLS} FROM agent_emails e WHERE e.tenant_id = CAST(:t AS uuid) AND e.status <> 'deleted' "
                                  f"AND e.mailbox_id = ANY(CAST(:mb AS uuid[])){since} ORDER BY e.created_at DESC LIMIT 4000",
                         {"t": tenant, "mb": mailbox_ids})
    threads: dict[tuple, list[dict]] = {}
    for r in rows:
        k = (r["mailbox_id"], BP.thread_key(r["subject"]))
        if k in touched:
            r["flags"] = _norm_flags(r["flags"])
            threads.setdefault(k, []).append(r)
    boxes = {m["id"]: m for m in await S._rows(session, "SELECT id::text AS id, agent_type, display_name FROM agent_mailboxes "
                                                        "WHERE tenant_id = CAST(:t AS uuid) AND id = ANY(CAST(:mb AS uuid[]))",
                                               {"t": tenant, "mb": mailbox_ids})}
    suppressed = await _suppressed_addresses(session, tenant, [e for es in threads.values() for e in es])
    from services.common.suppression import normalize_email
    for (mid, key), emails in threads.items():
        box = boxes.get(mid)
        if box is None:
            continue
        sup = any(normalize_email(e["sender"] if e["direction"] == "inbound" else e["recipient"]) in suppressed for e in emails)
        card = BP.build_mail_thread_card({**box, "id": mid}, emails, suppressed=sup)
        if card is None:
            page.tombstones.append(("mail_thread", f"{mid}:{key}"))
        else:
            page.cards.append(card)
    for k in touched - set(threads):                         # every message of the thread was deleted
        page.tombstones.append(("mail_thread", f"{k[0]}:{k[1]}"))
    return page


async def ids_mail_threads(session, tenant: str) -> dict:
    if not await _exists(session, "agent_emails"):
        raise RuntimeError("table agent_emails does not exist; refusing to reconcile mail_threads")
    rows = await S._rows(session, "SELECT e.mailbox_id::text AS mailbox_id, e.subject FROM agent_emails e WHERE e.tenant_id = CAST(:t AS uuid) "
                                  f"AND e.status <> 'deleted' AND e.created_at > now() - interval '{MAIL_WINDOW_DAYS} days' LIMIT 50000", {"t": tenant})
    return {"mail_thread": {f"{r['mailbox_id']}:{BP.thread_key(r['subject'])}" for r in rows}}


PERSONAL_SOURCES = [
    Source("personal_context", "personal", tuple(BP.PERSONAL_TYPES.values()), fetch_personal, ids_personal, snapshot=True),
    Source("mail_threads", "communication", ("mail_thread",), fetch_mail_threads, ids_mail_threads),
]
