"""Lead lifecycle operations shared by the lead endpoints, the board and
automations (SPEC-lead-lifecycle.md).

Everything here runs inside the request's AsyncSession, so the lead change, its
timeline entry and its event-bus event commit together. Closing deals won/lost
needs the bridges in main.py (commission, finance, lifecycle), so callers pass
those in as `close_won` / `close_lost`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.event_bus import publish
from services.sales.lead_stages import (
    StageChangeError,
    format_reference,
    lead_status_for_deal,
    plan_stage_change,
)
from services.sales.models import Contact, Deal, DealStage, Lead, LeadActivity, LeadTask, Pipeline

EVENT_SOURCE = "sales"

CloseWon = Callable[[AsyncSession, uuid.UUID, Deal], Awaitable[None]]
CloseLost = Callable[[AsyncSession, uuid.UUID, Deal, str], Awaitable[None]]


@dataclass
class Actor:
    id: Optional[uuid.UUID] = None
    name: Optional[str] = None


SYSTEM = Actor(name="System")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def full_name(lead: Lead) -> str:
    return f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "Unnamed lead"


# ── Reads ───────────────────────────────────────────────────────────────────

async def stage_names(db: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    rows = await db.execute(
        select(DealStage.name)
        .join(Pipeline, Pipeline.id == DealStage.pipeline_id)
        .where(Pipeline.tenant_id == tenant_id, Pipeline.is_default == True)  # noqa: E712
        .order_by(DealStage.sort_order)
    )
    return [r for (r,) in rows.all()]


async def deals_by_lead(db: AsyncSession, lead_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[Deal, Optional[str]]]:
    """Latest deal (and its stage name) for each lead."""
    if not lead_ids:
        return {}
    rows = await db.execute(
        select(Deal, DealStage.name)
        .outerjoin(DealStage, DealStage.id == Deal.stage_id)
        .where(Deal.lead_id.in_(lead_ids))
        .order_by(Deal.lead_id, Deal.created_at.desc())
    )
    out: dict[uuid.UUID, tuple[Deal, Optional[str]]] = {}
    for deal, stage in rows.all():
        out.setdefault(deal.lead_id, (deal, stage))
    return out


async def open_task_counts(db: AsyncSession, lead_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not lead_ids:
        return {}
    rows = await db.execute(
        select(LeadTask.lead_id, func.count())
        .where(LeadTask.lead_id.in_(lead_ids), LeadTask.status == "open")
        .group_by(LeadTask.lead_id)
    )
    return {lead_id: n for lead_id, n in rows.all()}


def lead_dict(lead: Lead, deal: Optional[Deal] = None, deal_stage: Optional[str] = None, open_tasks: int = 0) -> dict:
    return {
        "id": lead.id, "tenant_id": lead.tenant_id, "contact_id": lead.contact_id,
        "agent_id": lead.agent_id, "first_name": lead.first_name, "last_name": lead.last_name,
        "email": lead.email, "phone": lead.phone, "address": lead.address, "source": lead.source,
        "interest_level": lead.interest_level, "status": lead.status, "notes": lead.notes,
        "converted_at": lead.converted_at, "created_at": lead.created_at, "updated_at": lead.updated_at,
        "reference": format_reference(lead.ref_no), "owner_id": lead.owner_id, "owner_name": lead.owner_name,
        "priority": lead.priority or "normal", "closed_at": lead.closed_at,
        "close_reason": lead.close_reason, "escalated_at": lead.escalated_at,
        "deal_id": deal.id if deal else None, "deal_stage": deal_stage if deal else None,
        "deal_status": deal.status if deal else None,
        "deal_value_zar": deal.value_zar if deal else None, "open_tasks": open_tasks,
    }


async def lead_with_deal(db: AsyncSession, lead: Lead) -> dict:
    deal, stage = (await deals_by_lead(db, [lead.id])).get(lead.id, (None, None))
    tasks = (await open_task_counts(db, [lead.id])).get(lead.id, 0)
    return lead_dict(lead, deal, stage, tasks)


# ── Writes ──────────────────────────────────────────────────────────────────

async def next_ref_no(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Per-tenant sequence, serialised by a transaction-scoped advisory lock."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"lead_ref:{tenant_id}"})
    current = (await db.execute(
        select(func.coalesce(func.max(Lead.ref_no), 0)).where(Lead.tenant_id == tenant_id)
    )).scalar()
    return int(current or 0) + 1


async def record_activity(
    db: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID, kind: str, summary: str,
    details: Optional[dict] = None, actor: Actor = SYSTEM,
) -> LeadActivity:
    activity = LeadActivity(
        id=uuid.uuid4(), tenant_id=tenant_id, lead_id=lead_id, kind=kind, summary=summary[:300],
        details=details or {}, actor_id=actor.id, actor_name=actor.name, created_at=utcnow(),
    )
    db.add(activity)
    return activity


def lead_event_payload(lead: Lead, **extra: Any) -> dict:
    return {
        "lead_id": str(lead.id), "reference": format_reference(lead.ref_no), "name": full_name(lead),
        "email": lead.email, "phone": lead.phone, "source": lead.source, "status": lead.status,
        "owner_name": lead.owner_name, "priority": lead.priority, **extra,
    }


async def publish_lead_event(db: AsyncSession, lead: Lead, event_type: str, **extra: Any) -> None:
    await publish(db, lead.tenant_id, event_type, lead_event_payload(lead, **extra),
                  source=EVENT_SOURCE, subject=("lead", lead.id))


async def ensure_lead_contact(db: AsyncSession, lead: Lead) -> uuid.UUID:
    if lead.contact_id:
        return lead.contact_id
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    contact = Contact(
        id=uuid.uuid4(), tenant_id=lead.tenant_id,
        first_name=lead.first_name or "Lead", last_name=lead.last_name or "-",
        email=lead.email, phone=lead.phone, physical_address=lead.address,
        status="ACTIVE", lifecycle_stage="QUALIFIED", created_at=now, updated_at=now,
    )
    db.add(contact)
    await db.flush()
    lead.contact_id = contact.id
    return contact.id


async def _stage_id(db: AsyncSession, tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    row = (await db.execute(
        select(DealStage.id)
        .join(Pipeline, Pipeline.id == DealStage.pipeline_id)
        .where(Pipeline.tenant_id == tenant_id, Pipeline.is_default == True,  # noqa: E712
               func.lower(DealStage.name) == name.lower())
    )).scalar_one_or_none()
    if row is None:
        raise StageChangeError(f"Unknown pipeline stage '{name}'")
    return row


async def apply_stage_change(
    db: AsyncSession,
    lead: Lead,
    *,
    close_won: CloseWon,
    close_lost: CloseLost,
    target_status: Optional[str] = None,
    target_stage: Optional[str] = None,
    value_zar: Optional[Decimal] = None,
    deal_name: Optional[str] = None,
    reason: Optional[str] = None,
    actor: Actor = SYSTEM,
) -> tuple[Lead, Optional[Deal]]:
    """Apply lead_stages.plan_stage_change to the lead and its deal, write the
    timeline entry and publish sales.lead.stage_changed. Raises StageChangeError."""
    tenant_id = lead.tenant_id
    deal, deal_stage = (await deals_by_lead(db, [lead.id])).get(lead.id, (None, None))
    names = await stage_names(db, tenant_id)
    plan = plan_stage_change(
        current_status=lead.status, deal_status=deal.status if deal else None, stage_names=names,
        target_status=target_status, target_stage=target_stage, reason=reason,
    )
    before = deal_stage if deal else lead.status
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if plan.create_deal_at:
        contact_id = await ensure_lead_contact(db, lead)
        value = Decimal(str(value_zar)) if value_zar is not None else Decimal("0")
        deal = Deal(
            id=uuid.uuid4(), tenant_id=tenant_id, contact_id=contact_id, lead_id=lead.id,
            agent_id=lead.agent_id, stage_id=await _stage_id(db, tenant_id, plan.create_deal_at),
            name=deal_name or f"{full_name(lead)} - {lead.source or 'Lead'}",
            amount=value, value_zar=value, status="OPEN", created_at=now, updated_at=now,
        )
        db.add(deal)
        await db.flush()
        deal_stage = plan.create_deal_at
        lead.converted_at = lead.converted_at or now
    if plan.move_deal_to and deal is not None:
        deal.stage_id = await _stage_id(db, tenant_id, plan.move_deal_to)
        deal.updated_at = now
        deal_stage = plan.move_deal_to
    if plan.close_deal == "won" and deal is not None:
        await close_won(db, tenant_id, deal)
        deal_stage = "Closed Won"
    elif plan.close_deal == "lost" and deal is not None:
        await close_lost(db, tenant_id, deal, plan.reason or "Lost")
        deal_stage = "Closed Lost"

    lead.status = plan.lead_status
    lead.updated_at = now
    if plan.closed:
        lead.closed_at = lead.closed_at or utcnow()
        lead.close_reason = plan.reason or lead.close_reason
    else:
        lead.closed_at = None
        lead.close_reason = None
    await db.flush()

    after = deal_stage if deal else lead.status
    summary = (f"Added to the pipeline at {after}" if plan.create_deal_at and not plan.close_deal
               else f"Stage changed: {_label(before)} → {_label(after)}")
    await record_activity(db, tenant_id, lead.id, "stage_changed", summary,
                          {"from": before, "to": after, "deal_id": str(deal.id) if deal else None,
                           "reason": plan.reason}, actor)
    await publish_lead_event(db, lead, "sales.lead.stage_changed", **{
        "from": before, "to": after, "deal_id": str(deal.id) if deal else None,
        "deal_stage": deal_stage if deal else None,
    })
    return lead, deal


STATUS_LABELS = {
    "NEW": "New", "CONTACTED": "Contacted", "QUALIFIED": "Qualified", "DISQUALIFIED": "Disqualified",
    "CONVERTED": "In pipeline", "WON": "Won", "LOST": "Lost",
}


def _label(value: Optional[str]) -> str:
    """Lead statuses read as words; board stage names are already labels."""
    return STATUS_LABELS.get(value or "", value or "—")


async def sync_lead_from_deal(
    db: AsyncSession, deal: Deal, stage_name: Optional[str], actor: Actor = SYSTEM,
) -> Optional[Lead]:
    """Board → lead: after a deal moved/closed, mirror it on the linked lead."""
    if not deal.lead_id:
        return None
    lead = await db.get(Lead, deal.lead_id)
    if lead is None or lead.tenant_id != deal.tenant_id:
        return None
    before = lead.status
    lead.status = lead_status_for_deal(deal.status)
    lead.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if deal.status in ("WON", "LOST"):
        lead.closed_at = lead.closed_at or utcnow()
        lead.close_reason = deal.close_reason or lead.close_reason
    else:
        lead.closed_at = None
        lead.close_reason = None
    await record_activity(db, lead.tenant_id, lead.id, "stage_changed",
                          f"Pipeline board: deal moved to {stage_name or deal.status}",
                          {"from": before, "to": stage_name, "deal_id": str(deal.id), "via": "board"}, actor)
    await publish_lead_event(db, lead, "sales.lead.stage_changed",
                             **{"from": before, "to": stage_name, "deal_id": str(deal.id),
                                "deal_stage": stage_name, "via": "board"})
    return lead


async def publish_deal_event(db: AsyncSession, deal: Deal, stage_name: Optional[str]) -> None:
    event_type = {"WON": "sales.deal.won", "LOST": "sales.deal.lost"}.get(deal.status, "sales.deal.stage_changed")
    await publish(db, deal.tenant_id, event_type, {
        "deal_id": str(deal.id), "lead_id": str(deal.lead_id) if deal.lead_id else None,
        "name": deal.name, "stage": stage_name, "status": deal.status,
        "value_zar": float(deal.value_zar or 0), "close_reason": deal.close_reason,
    }, source=EVENT_SOURCE, subject=("deal", deal.id))
