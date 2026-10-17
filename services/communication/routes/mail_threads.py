"""Email conversations for people and agents: thread list/read, state (status, owner), draft, send, backfill, audit.

Mounted under /mail (see main.py). Every route is tenant-scoped, and every thread route filters by mailbox access
(mail_state.can_read_mailbox): a personal mailbox is its owner's alone, a shared mailbox needs the area permission.

Agent contract (orchestrator tools email.* call these routes with the signed identity of the person behind the agent):
  * thread content comes back FENCED as untrusted data with injection signals, bodies redacted, quoted history cut;
  * `draft` stores text for a person to review and never sends;
  * `send` is the only way out and the orchestrator puts it behind the approval gate (email.send_reply); it also
    refuses credential-shaped text and replying twice to the same message.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from services.common import agentmail as agentmail_client
from services.common import email_safety as ES
from services.common.auth import AuthContext, get_auth_context
from services.communication import mail_state
from services.communication.database import get_session
from services.communication.models import AgentEmail, AgentMailbox
from services.communication.routes import mail as M

logger = logging.getLogger("communication.mail_threads")
router = APIRouter(prefix="/mail", tags=["agent-mail-threads"])

MAX_THREAD_MESSAGES = 60


# ── access ───────────────────────────────────────────────────────────────────

async def _readable_mailboxes(session, auth: AuthContext) -> dict[str, AgentMailbox]:
    """mailbox id -> mailbox, for the mailboxes this caller may read."""
    boxes = (await session.execute(select(AgentMailbox).where(
        AgentMailbox.tenant_id == auth.tenant_id, AgentMailbox.is_active == True))).scalars().all()  # noqa: E712
    access = await mail_state.load_access(session, auth.tenant_id, [b.id for b in boxes])
    roles, perms = await M._effective_access(auth)
    return {str(b.id): b for b in boxes if mail_state.can_read_mailbox(
        user_id=auth.user_id, roles=roles, permissions=perms, is_platform_admin=auth.is_platform_admin,
        agent_type=b.agent_type, access=access.get(str(b.id)))}


def _thread_view(r: dict, box: Optional[AgentMailbox]) -> dict:
    return {
        "thread_id": r["id"], "thread_key": r["thread_key"], "mailbox_id": r["mailbox_id"],
        "mailbox": getattr(box, "email_address", None), "agent_type": getattr(box, "agent_type", None),
        "subject": ES.neutralise_fence(r["subject"]), "status": r["status"],
        "owner_user_id": r["owner_user_id"], "counterpart": r["counterpart"],
        "customer_id": r["customer_id"], "lead_id": r["lead_id"], "ticket_id": r["ticket_id"],
        "message_count": r["message_count"], "inbound_count": r["inbound_count"],
        "last_message_at": r["last_message_at"], "last_inbound_at": r["last_inbound_at"],
        "last_outbound_at": r["last_outbound_at"],
        "waiting_hours": _waiting_hours(r),
    }


def _waiting_hours(r: dict) -> Optional[float]:
    if r["status"] != ES.NEEDS_RESPONSE or not r["last_inbound_at"]:
        return None
    return round((datetime.now(timezone.utc) - r["last_inbound_at"]).total_seconds() / 3600, 1)


_THREAD_COLS = ("id::text AS id, thread_key, mailbox_id::text AS mailbox_id, subject, status, owner_user_id::text AS owner_user_id, "
                "counterpart, customer_id::text AS customer_id, lead_id::text AS lead_id, ticket_id::text AS ticket_id, "
                "message_count, inbound_count, last_message_at, last_inbound_at, last_outbound_at, provider_thread_id")


async def _get_thread(session, auth: AuthContext, thread_id: uuid.UUID) -> tuple[dict, AgentMailbox]:
    readable = await _readable_mailboxes(session, auth)
    row = (await session.execute(text(f"SELECT {_THREAD_COLS} FROM email_threads WHERE tenant_id = :t AND id = :i"),
                                 {"t": auth.tenant_id, "i": thread_id})).mappings().first()
    # same answer for "does not exist" and "not yours": no probing for other mailboxes' threads
    if row is None or row["mailbox_id"] not in readable:
        raise HTTPException(status_code=404, detail="Thread not found")
    return dict(row), readable[row["mailbox_id"]]


async def _thread_emails(session, auth: AuthContext, thread: dict) -> List[AgentEmail]:
    core = ES.normalise_subject(thread["subject"])
    like = "%" + core.replace("%", "").replace("_", r"\_")[:120] + "%"
    rows = (await session.execute(select(AgentEmail).where(
        AgentEmail.tenant_id == auth.tenant_id, AgentEmail.mailbox_id == uuid.UUID(thread["mailbox_id"]),
        AgentEmail.status != "deleted", AgentEmail.subject.ilike(like, escape="\\"))
        .order_by(AgentEmail.created_at.desc()).limit(400))).scalars().all()
    mine = [e for e in rows if mail_state.thread_key_of(e.headers, e.subject) == thread["thread_key"]]
    return sorted(mine, key=lambda e: e.created_at)[-MAX_THREAD_MESSAGES:]


# ── list / summary / read ────────────────────────────────────────────────────

@router.get("/threads")
async def list_threads(
    status: Optional[str] = Query(None, description="needs_response | awaiting_customer | closed"),
    mailbox_id: Optional[uuid.UUID] = None,
    owner: Optional[str] = Query(None, description="me | unassigned"),
    older_than_hours: Optional[float] = Query(None, ge=0, description="only threads waiting at least this long"),
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
):
    if status and status not in ES.THREAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(ES.THREAD_STATUSES)}")
    async with get_session() as session:
        readable = await _readable_mailboxes(session, auth)
        ids = [uuid.UUID(m) for m in readable if not mailbox_id or str(mailbox_id) == m]
        if not ids:
            return {"threads": [], "total": 0}
        where, params = ["tenant_id = :t", "mailbox_id = ANY(:mb)"], {"t": auth.tenant_id, "mb": ids, "lim": limit, "off": offset}
        if status:
            where.append("status = :st"); params["st"] = status
        if owner == "me":
            where.append("owner_user_id = :me"); params["me"] = auth.user_id
        elif owner == "unassigned":
            where.append("owner_user_id IS NULL")
        if older_than_hours:
            where.append("last_inbound_at <= :cut"); params["cut"] = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        w = " AND ".join(where)
        total = (await session.execute(text(f"SELECT count(*) FROM email_threads WHERE {w}"), params)).scalar_one()
        rows = (await session.execute(text(
            f"SELECT {_THREAD_COLS} FROM email_threads WHERE {w} "
            "ORDER BY (status = 'needs_response') DESC, last_message_at ASC NULLS LAST LIMIT :lim OFFSET :off"), params)).mappings().all()
    return {"total": total, "untrusted_fields": ["subject"],
            "threads": [_thread_view(dict(r), readable.get(r["mailbox_id"])) for r in rows]}


@router.get("/threads/summary")
async def threads_summary(auth: AuthContext = Depends(get_auth_context)):
    """What needs a response, by mailbox: the answer to 'which emails are waiting on us?' for people, agents and the daily review."""
    async with get_session() as session:
        readable = await _readable_mailboxes(session, auth)
        if not readable:
            return {"needs_response": 0, "awaiting_customer": 0, "closed": 0, "mailboxes": []}
        ids = [uuid.UUID(m) for m in readable]
        rows = (await session.execute(text(
            "SELECT mailbox_id::text AS mailbox_id, status, count(*) AS n, min(last_inbound_at) AS oldest, "
            "count(*) FILTER (WHERE owner_user_id IS NULL) AS unassigned FROM email_threads "
            "WHERE tenant_id = :t AND mailbox_id = ANY(:mb) GROUP BY 1, 2"), {"t": auth.tenant_id, "mb": ids})).mappings().all()
    totals = {s: 0 for s in ES.THREAD_STATUSES}
    boxes: dict[str, dict] = {}
    now = datetime.now(timezone.utc)
    for r in rows:
        totals[r["status"]] = totals.get(r["status"], 0) + r["n"]
        b = boxes.setdefault(r["mailbox_id"], {"mailbox_id": r["mailbox_id"], "mailbox": readable[r["mailbox_id"]].email_address,
                                                 "agent_type": readable[r["mailbox_id"]].agent_type,
                                                 **{s: 0 for s in ES.THREAD_STATUSES}, "oldest_waiting_hours": None, "unassigned_waiting": 0})
        b[r["status"]] = r["n"]
        if r["status"] == ES.NEEDS_RESPONSE:
            b["unassigned_waiting"] = r["unassigned"]
            b["oldest_waiting_hours"] = round((now - r["oldest"]).total_seconds() / 3600, 1) if r["oldest"] else None
    return {**totals, "mailboxes": list(boxes.values())}


@router.get("/threads/{thread_id}")
async def read_thread(thread_id: uuid.UUID, auth: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        thread, box = await _get_thread(session, auth, thread_id)
        emails = await _thread_emails(session, auth, thread)
        view = _thread_view(thread, box)
        messages, flagged_any = [], []
        for e in emails:
            body = ES.prepare_body(e.body_text, limit=4000)
            flagged = ES.detect_injection(e.subject, e.body_text) if e.direction == "inbound" else []
            flagged_any += flagged
            sender_name = ES.display_name(e.sender, "") or ES.bare_address(e.sender)
            messages.append({
                "email_id": str(e.id), "direction": e.direction, "at": e.created_at.isoformat() if e.created_at else None,
                "from_name": sender_name, "from_address": ES.bare_address(e.sender), "status": e.status,
                "injection_suspected": flagged,
                "content": ES.fence_email(e.sender if e.direction == "inbound" else f"{box.display_name} (us)", e.subject, body, flagged=flagged),
            })
        last_in = next((e for e in reversed(emails) if e.direction == "inbound"), None)
        draft = (last_in.agent_response or "").strip() if last_in is not None else ""
        await mail_state.audit(session, auth.tenant_id, "read_thread", actor_id=auth.user_id, actor_kind="user",
                               thread_key=thread["thread_key"], detail={"messages": len(messages), "injection": sorted(set(flagged_any))})
    return {**view, "content_trust": "untrusted", "notice": ES.UNTRUSTED_NOTICE, "injection_suspected": sorted(set(flagged_any)),
            "messages": messages, "pending_draft": draft or None,
            "reply_to_email_id": str(last_in.id) if last_in is not None else None}


# ── state ────────────────────────────────────────────────────────────────────

class ThreadUpdate(BaseModel):
    status: Optional[str] = None
    owner_user_id: Optional[uuid.UUID] = None
    claim: Optional[bool] = Field(None, description="true = assign to me, false = unassign")
    ticket_id: Optional[uuid.UUID] = None
    customer_id: Optional[uuid.UUID] = None
    lead_id: Optional[uuid.UUID] = None


@router.patch("/threads/{thread_id}")
async def update_thread(thread_id: uuid.UUID, payload: ThreadUpdate, auth: AuthContext = Depends(get_auth_context)):
    await M.require_mail_write(auth)
    if payload.status and payload.status not in ES.THREAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {', '.join(ES.THREAD_STATUSES)}")
    sets, params = [], {"t": auth.tenant_id, "i": thread_id}
    if payload.status:
        sets.append("status = :st"); params["st"] = payload.status
        sets.append("closed_at = CASE WHEN :st = 'closed' THEN now() ELSE NULL END")
    if payload.claim is True:
        sets.append("owner_user_id = :owner"); params["owner"] = auth.user_id
    elif payload.claim is False:
        sets.append("owner_user_id = NULL")
    elif payload.owner_user_id:
        sets.append("owner_user_id = :owner"); params["owner"] = payload.owner_user_id
    for col in ("ticket_id", "customer_id", "lead_id"):
        if getattr(payload, col):
            sets.append(f"{col} = :{col}"); params[col] = getattr(payload, col)
    if not sets:
        raise HTTPException(status_code=422, detail="Nothing to update")
    async with get_session() as session:
        before, box = await _get_thread(session, auth, thread_id)
        await session.execute(text(f"UPDATE email_threads SET {', '.join(sets)}, updated_at = now() WHERE tenant_id = :t AND id = :i"), params)
        after = (await session.execute(text(f"SELECT {_THREAD_COLS} FROM email_threads WHERE tenant_id = :t AND id = :i"),
                                       {"t": auth.tenant_id, "i": thread_id})).mappings().first()
        from services.common import event_bus
        await event_bus.publish(session, auth.tenant_id, "email.thread_status_changed",
                                {"thread_id": str(thread_id), "mailbox_id": before["mailbox_id"], "from_status": before["status"],
                                 "status": after["status"], "owner_user_id": after["owner_user_id"], "ticket_id": after["ticket_id"],
                                 "changed_by": str(auth.user_id)},
                                source=mail_state.SOURCE, subject=("email_thread", str(thread_id)))
        await mail_state.audit(session, auth.tenant_id, "thread_updated", actor_id=auth.user_id, actor_kind="user",
                               thread_key=before["thread_key"], detail={"from": before["status"], "to": after["status"]})
        return _thread_view(dict(after), box)


# ── draft and send ───────────────────────────────────────────────────────────

class DraftPayload(BaseModel):
    body_text: str = Field(..., min_length=1, max_length=20000)


class SendPayload(BaseModel):
    body_text: Optional[str] = Field(None, max_length=20000, description="omit to send the stored draft")


async def _last_inbound(session, auth: AuthContext, thread: dict) -> AgentEmail:
    emails = await _thread_emails(session, auth, thread)
    last_in = next((e for e in reversed(emails) if e.direction == "inbound"), None)
    if last_in is None:
        raise HTTPException(status_code=409, detail="This thread has no inbound message to reply to")
    return last_in


@router.post("/threads/{thread_id}/draft")
async def draft_reply(thread_id: uuid.UUID, payload: DraftPayload, auth: AuthContext = Depends(get_auth_context)):
    """Store reply text on the latest inbound message for a person to review. Nothing is sent."""
    await M.require_mail_write(auth)
    async with get_session() as session:
        thread, _box = await _get_thread(session, auth, thread_id)
        last_in = await _last_inbound(session, auth, thread)
        if (last_in.headers or {}).get("agent_reply_sent") or last_in.status in M._REPLY_FINAL_STATUSES:
            raise HTTPException(status_code=409, detail="The latest message has already been answered")
        row = await session.get(AgentEmail, last_in.id)
        row.agent_response = payload.body_text
        row.headers = {**(row.headers or {}), "draft_by": str(auth.user_id), "draft_at": datetime.now(timezone.utc).isoformat()}
        await mail_state.audit(session, auth.tenant_id, "draft_saved", actor_id=auth.user_id, actor_kind="agent",
                               email_id=row.id, thread_key=thread["thread_key"], detail={"chars": len(payload.body_text)})
    return {"success": True, "thread_id": str(thread_id), "reply_to_email_id": str(last_in.id), "sent": False,
            "note": "Draft saved for review. Sending needs email.send_reply and a person's approval."}


@router.post("/threads/{thread_id}/send", status_code=201)
async def send_reply(thread_id: uuid.UUID, payload: SendPayload, auth: AuthContext = Depends(get_auth_context)):
    """Reply to the latest inbound message of a thread. The orchestrator only calls this after human approval."""
    await M.require_mail_write(auth)
    async with get_session() as session:
        thread, box = await _get_thread(session, auth, thread_id)
        last_in = await _last_inbound(session, auth, thread)
    body = (payload.body_text if payload.body_text is not None else (last_in.agent_response or "")).strip()
    if not body:
        raise HTTPException(status_code=409, detail="No reply text: pass body_text or save a draft first")
    if ES.contains_secret(body):
        async with get_session() as session:
            await mail_state.audit(session, auth.tenant_id, "send_refused_secret", actor_id=auth.user_id, actor_kind="agent",
                                   email_id=last_in.id, thread_key=thread["thread_key"])
        raise HTTPException(status_code=422, detail="The reply contains what looks like a credential or key; remove it")
    target = M._clean_addrs([M._reply_target(last_in.sender)], "sender")
    async with get_session() as session:
        claimed = (await session.execute(M._claim_reply_stmt(last_in.id, auth.tenant_id))).scalar_one_or_none()
    if claimed is None:
        raise HTTPException(status_code=409, detail="The latest message was already answered or is being answered")
    try:
        rec = await M._deliver_and_store(
            auth.tenant_id, last_in.mailbox_id, target, [], [], M._reply_subject(last_in.subject), body, None, last_in.message_id,
            extra_headers={"reply_to_email_id": str(last_in.id), "sent_by": str(auth.user_id)},
            thread_id=(last_in.headers or {}).get("thread_id") or thread.get("provider_thread_id"),
            actor={"action": "sent", "id": auth.user_id, "kind": "agent", "detail": {"reply_to": str(last_in.id)}})
    except BaseException:
        await M._release_reply_claim(last_in.id, auth.tenant_id, last_in.status)
        raise
    if rec.status == "sent":
        async with get_session() as session:
            row = await session.get(AgentEmail, last_in.id)
            if row is not None and row.tenant_id == auth.tenant_id:
                row.headers = {**(row.headers or {}), "agent_reply_sent": True}
                row.status = "replied"
    else:
        await M._release_reply_claim(last_in.id, auth.tenant_id, last_in.status)
        raise HTTPException(status_code=502, detail="The provider did not accept the message; nothing was sent")
    return {"success": True, "sent": True, "email_id": str(rec.id), "message_id": rec.message_id, "thread_id": str(thread_id)}


# ── administration: mailbox access, backfill, audit ──────────────────────────

class AccessPayload(BaseModel):
    kind: str = Field(..., pattern="^(shared|personal)$")
    owner_user_id: Optional[uuid.UUID] = None
    required_roles: List[str] = Field(default_factory=list, max_length=20)


@router.put("/mailboxes/{mailbox_id}/access")
async def set_mailbox_access(mailbox_id: uuid.UUID, payload: AccessPayload, auth: AuthContext = Depends(get_auth_context)):
    await M.require_mail_admin(auth)
    if payload.kind == "personal" and not payload.owner_user_id:
        raise HTTPException(status_code=422, detail="A personal mailbox needs owner_user_id")
    async with get_session() as session:
        box = (await session.execute(select(AgentMailbox).where(
            AgentMailbox.id == mailbox_id, AgentMailbox.tenant_id == auth.tenant_id))).scalar_one_or_none()
        if box is None:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        await mail_state.set_access(session, auth.tenant_id, mailbox_id, kind=payload.kind,
                                    owner_user_id=payload.owner_user_id, required_roles=payload.required_roles)
        await mail_state.audit(session, auth.tenant_id, "mailbox_access_set", actor_id=auth.user_id, actor_kind="user",
                               detail={"mailbox_id": str(mailbox_id), "kind": payload.kind})
    return {"mailbox_id": str(mailbox_id), "kind": payload.kind, "owner_user_id": str(payload.owner_user_id) if payload.owner_user_id else None}


class BackfillPayload(BaseModel):
    provider_days: int = Field(0, ge=0, le=730, description="also import this many days of provider history (0 = local rebuild only)")
    max_messages: int = Field(500, ge=1, le=5000)


@router.post("/backfill")
async def backfill(payload: BackfillPayload, auth: AuthContext = Depends(get_auth_context)):
    """One-off, repeatable: (1) import provider history for the tenant's inboxes without events or auto-replies, then
    (2) rebuild thread state from every stored email. Idempotent by provider message id."""
    await M.require_mail_admin(auth)
    imported = 0
    if payload.provider_days:
        creds = await M._tenant_creds(auth.tenant_id)
        if not agentmail_client.is_configured(creds):
            raise HTTPException(status_code=503, detail="Email provider not configured")
        since = (datetime.now(timezone.utc) - timedelta(days=payload.provider_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with get_session() as session:
            boxes = (await session.execute(select(AgentMailbox).where(
                AgentMailbox.tenant_id == auth.tenant_id, AgentMailbox.is_active == True))).scalars().all()  # noqa: E712
        for box in boxes:
            token = None
            while imported < payload.max_messages:
                items, token = await agentmail_client.list_messages_page(box.email_address, creds=creds, after=since, page_token=token)
                for m in items:
                    mid = str(m.get("message_id") or "")
                    if not mid:
                        continue
                    is_sent = "sent" in (m.get("labels") or [])
                    direction = "outbound" if is_sent else "inbound"
                    async with get_session() as session:
                        have = (await session.execute(select(AgentEmail.id).where(
                            AgentEmail.tenant_id == auth.tenant_id, AgentEmail.direction == direction,
                            AgentEmail.message_id == mid))).first()
                    if have:
                        continue
                    full = await agentmail_client.get_message(box.email_address, mid, creds=creds)
                    if is_sent:
                        if await M._store_provider_sent(auth.tenant_id, box.email_address, full, via="backfill"):
                            imported += 1
                    else:
                        flat = agentmail_client.normalize_message(full, box.email_address)
                        flat["recipient"] = box.email_address
                        await M._process_inbound(auth.tenant_id, None, M.InboundEmailPayload(**flat), via="backfill", backfill=True)
                        imported += 1
                if not token:
                    break
    async with get_session() as session:
        rebuilt = await mail_state.rebuild_threads(session, auth.tenant_id)
        await mail_state.audit(session, auth.tenant_id, "backfill", actor_id=auth.user_id, actor_kind="user",
                               detail={"imported": imported, **rebuilt})
    return {"imported_from_provider": imported, **rebuilt}


@router.get("/audit")
async def audit_log(action: Optional[str] = None, limit: int = Query(50, ge=1, le=200), auth: AuthContext = Depends(get_auth_context)):
    await M.require_mail_admin(auth)
    async with get_session() as session:
        rows = (await session.execute(text(
            "SELECT id::text AS id, actor_id::text AS actor_id, actor_kind, action, email_id::text AS email_id, thread_key, detail, created_at "
            "FROM email_audit_log WHERE tenant_id = :t AND (CAST(:a AS text) IS NULL OR action = :a) "
            "ORDER BY created_at DESC LIMIT :l"), {"t": auth.tenant_id, "a": action, "l": limit})).mappings().all()
    return {"entries": [dict(r) for r in rows]}
