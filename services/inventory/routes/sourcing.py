"""Supply-base sourcing API: find suppliers from a product description, run RFI/RFQ rounds with AI drafting, score the replies, and
suggest what to buy from the product KPIs. The tenant's procurement protocol (editable in Admin) governs all of it.

The same endpoints are what the agents call as tools; anything that contacts a supplier follows the protocol's approval rule.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id, get_current_user_id
from services.common.http_client import _request
from services.inventory import catalogue_rules as rules
from services.inventory import sourcing as S
from services.inventory.access import require_access, require_tier
from services.inventory.catalogue_models import CatalogueProduct
from services.inventory.database import (InventoryLevel, PurchaseOrder, PurchaseOrderItem, StockMovement, Supplier, Warehouse, get_session,
                                         next_sequence_number)
from services.inventory.routes.catalogue import _all, _catalogue_map, _get, _log, _normalise_definition_sources, _view
from services.inventory.routes.supplier_perf import load_facts, metrics_for
from services.inventory.sourcing_models import (ProcurementProtocol, SourcingDiscovery, SourcingInvitee, SourcingRequest, SourcingResponse,
                                                SupplierProfile, SupplierProspect)

logger = logging.getLogger("inventory.sourcing.routes")

# The research service is "fno_intelligence" on the compose network; the shared client's default spells it with a hyphen.
import os as _os
from services.common import http_client as _http_client
_http_client._SERVICE_URLS["fno_intelligence"] = _os.getenv("FNO_INTELLIGENCE_SERVICE_URL") or "http://fno_intelligence:8024"
router = APIRouter(prefix="/sourcing", tags=["Sourcing"])

OPEN_STATUSES = ("draft", "pending_approval", "approved", "sent")


# ── helpers ──────────────────────────────────────────────────────────────────

async def _protocol(db, tenant_id) -> S.Protocol:
    row = (await db.execute(select(ProcurementProtocol).where(ProcurementProtocol.tenant_id == tenant_id))).scalar_one_or_none()
    return S.protocol_from(row.config if row else None)


async def _company(db, tenant_id) -> str:
    try:
        return (await db.execute(text("SELECT name FROM tenants WHERE id = CAST(:t AS uuid)"), {"t": str(tenant_id)})).scalar() or "Our company"
    except Exception:  # noqa: BLE001
        return "Our company"


async def _kinds(db, tenant_id) -> dict[str, str]:
    rows = (await db.execute(select(SupplierProfile).where(SupplierProfile.tenant_id == tenant_id))).scalars()
    return {str(r.supplier_id): r.kind for r in rows}


def _req(r: SourcingRequest, product_names: Optional[dict] = None) -> dict:
    return {"id": str(r.id), "number": r.number, "kind": r.kind, "product_id": str(r.product_id) if r.product_id else None,
            "product": (product_names or {}).get(r.product_id), "title": r.title, "quantity": r.quantity,
            "target_price": float(r.target_price) if r.target_price is not None else None, "needed_by": r.needed_by.isoformat() if r.needed_by else None,
            "subject": r.subject, "body": r.body, "drafted_by": r.drafted_by, "status": r.status, "source": r.source,
            "created_at": r.created_at.isoformat() if r.created_at else None, "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None, "awarded_invitee_id": str(r.awarded_invitee_id) if r.awarded_invitee_id else None,
            "award_note": r.award_note, "created_by_agent": r.created_by_agent}


def _inv(i: SourcingInvitee) -> dict:
    return {"id": str(i.id), "supplier_id": str(i.supplier_id) if i.supplier_id else None, "prospect_id": str(i.prospect_id) if i.prospect_id else None,
            "name": i.name, "email": i.email, "kind": i.kind, "status": i.status, "error": i.error,
            "sent_at": i.sent_at.isoformat() if i.sent_at else None}


def _resp(r: SourcingResponse) -> dict:
    return {"id": str(r.id), "invitee_id": str(r.invitee_id), "unit_price": float(r.unit_price) if r.unit_price is not None else None,
            "lead_time_days": r.lead_time_days, "moq": r.moq, "valid_until": r.valid_until.isoformat() if r.valid_until else None,
            "notes": r.notes, "declined": r.declined, "source": r.source, "created_at": r.created_at.isoformat() if r.created_at else None}


async def _load_request(db, tenant_id, rid: uuid.UUID, lock: bool = False) -> SourcingRequest:
    q = select(SourcingRequest).where(SourcingRequest.id == rid, SourcingRequest.tenant_id == tenant_id)
    r = (await db.execute(q.with_for_update() if lock else q)).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Request not found")
    return r


async def _invitees(db, rid) -> list[SourcingInvitee]:
    return list((await db.execute(select(SourcingInvitee).where(SourcingInvitee.request_id == rid).order_by(SourcingInvitee.created_at))).scalars())


async def _event(db, tenant_id, user_id, kind: str, detail: dict) -> None:
    """Tell the event bus (agents and automations listen); advisory, never fails the request."""
    try:
        from services.common.event_bus import publish
        async with db.begin_nested():
            await publish(db, tenant_id, f"sourcing.{kind}", {"user_id": str(user_id) if user_id else None, **detail}, source="inventory")
    except Exception:  # noqa: BLE001
        logger.debug("event not published", exc_info=True)


# ── protocol ─────────────────────────────────────────────────────────────────

@router.get("/protocol", dependencies=[Depends(require_tier("write"))])
async def get_protocol(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    p = await _protocol(db, tenant_id)
    row = (await db.execute(select(ProcurementProtocol).where(ProcurementProtocol.tenant_id == tenant_id))).scalar_one_or_none()
    return {"protocol": p.model_dump(), "defaults": S.DEFAULT_PROTOCOL, "customised": row is not None,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None}


@router.put("/protocol", dependencies=[Depends(require_tier("manager"))])
async def put_protocol(body: S.Protocol, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id),
                       db=Depends(get_session)):
    """Replace the tenant's procurement protocol. Takes effect on the next request; requests already sent are not affected."""
    row = (await db.execute(select(ProcurementProtocol).where(ProcurementProtocol.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
    if row is None:
        db.add(ProcurementProtocol(tenant_id=tenant_id, config=body.model_dump(), updated_by=user_id))
    else:
        row.config, row.updated_by = body.model_dump(), user_id
    return {"protocol": body.model_dump()}


@router.delete("/protocol", dependencies=[Depends(require_tier("manager"))])
async def reset_protocol(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    row = (await db.execute(select(ProcurementProtocol).where(ProcurementProtocol.tenant_id == tenant_id))).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
    return {"protocol": S.DEFAULT_PROTOCOL}


# ── suppliers: internal or external ─────────────────────────────────────────

@router.get("/suppliers", dependencies=[Depends(require_tier("write"))])
async def sourcing_suppliers(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    kinds = await _kinds(db, tenant_id)
    facts = await load_facts(db, tenant_id, 12)
    rows = (await db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None), Supplier.is_active.is_(True)).order_by(Supplier.name))).scalars()
    out = []
    for s in rows:
        m = metrics_for(facts, str(s.id))
        out.append({"id": str(s.id), "name": s.name, "email": s.email, "contact_person": s.contact_person, "lead_time_days": s.lead_time_days,
                    "kind": kinds.get(str(s.id), "external"), "score": m.get("score"), "deliveries": m.get("deliveries", 0)})
    return out


class KindIn(BaseModel):
    kind: Literal["internal", "external"]


@router.put("/suppliers/{supplier_id}/kind", dependencies=[Depends(require_tier("write"))])
async def set_supplier_kind(supplier_id: uuid.UUID, body: KindIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    if (await db.execute(select(Supplier.id).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id))).first() is None:
        raise HTTPException(404, "Supplier not found")
    row = (await db.execute(select(SupplierProfile).where(SupplierProfile.tenant_id == tenant_id, SupplierProfile.supplier_id == supplier_id))).scalar_one_or_none()
    if row is None:
        db.add(SupplierProfile(tenant_id=tenant_id, supplier_id=supplier_id, kind=body.kind))
    else:
        row.kind = body.kind
    return {"id": str(supplier_id), "kind": body.kind}


# ── finding suppliers from the product description ──────────────────────────

class DiscoverIn(BaseModel):
    product_id: uuid.UUID
    country: str = Field("za", max_length=40)
    note: str = Field("", max_length=300)


def _prospect(p: SupplierProspect) -> dict:
    return {"id": str(p.id), "product_id": str(p.product_id) if p.product_id else None, "name": p.name, "domain": p.domain, "website": p.website,
            "email": p.email, "phone": p.phone, "country": p.country, "summary": p.summary, "fit": p.fit, "status": p.status,
            "supplier_id": str(p.supplier_id) if p.supplier_id else None}


@router.post("/discoveries", status_code=201, dependencies=[Depends(require_tier("write"))])
async def start_discovery(body: DiscoverIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id),
                          db=Depends(get_session)):
    """Search the web for suppliers of this product, using its description and specifications. Uses (metered) research credits."""
    protocol = await _protocol(db, tenant_id)
    if not protocol.allow_external:
        raise HTTPException(409, "The procurement protocol does not allow external suppliers")
    view = _view(await _get(db, tenant_id, body.product_id))
    question = S.discovery_question(view, body.country, body.note)
    try:
        run = await _request_research(tenant_id, user_id, question, body.country)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery could not start: %s", exc)
        raise HTTPException(502, "The research service could not start the search. Try again shortly.")
    d = SourcingDiscovery(tenant_id=tenant_id, product_id=body.product_id, query=question, status="running", run_id=str(run.get("id")), created_by=user_id)
    db.add(d)
    await db.flush()
    return {"id": str(d.id), "status": d.status, "query": question}


async def _request_research(tenant_id, user_id, question: str, country: str) -> dict:
    import httpx
    try:
        return await _request("POST", "fno_intelligence", "/api/fno/analytics/research", tenant_id=tenant_id, user_id=user_id,
                              json={"question": question, "depth": "quick", "country": (country or "za")[:2].lower()}, timeout=20.0, retries=1)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        detail = ""
        try:
            detail = exc.response.json().get("detail") or ""
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(402 if code == 402 else 502, str(detail)[:300] or f"Research service answered {code}")


@router.get("/discoveries/{discovery_id}", dependencies=[Depends(require_tier("write"))])
async def get_discovery(discovery_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id),
                        db=Depends(get_session)):
    """Progress of a search. When the research finishes, the suppliers it found become prospects for you to review."""
    d = (await db.execute(select(SourcingDiscovery).where(SourcingDiscovery.id == discovery_id, SourcingDiscovery.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
    if d is None:
        raise HTTPException(404, "Search not found")
    if d.status == "running" and d.run_id:
        try:
            run = await _request("GET", "fno_intelligence", f"/api/fno/analytics/research/{d.run_id}", tenant_id=tenant_id, user_id=user_id, timeout=15.0, retries=1)
        except Exception as exc:  # noqa: BLE001
            return {"id": str(d.id), "status": d.status, "prospects": d.prospects, "note": f"Waiting for the research service ({type(exc).__name__})"}
        if run.get("status") == "failed":
            d.status, d.error = "failed", str(run.get("error") or "The research failed")[:500]
        elif run.get("status") == "done":
            view = _view(await _get(db, tenant_id, d.product_id)) if d.product_id else {}
            d.prospects = await _store_prospects(db, tenant_id, d, run, view)
            d.status, d.summary = "done", str((run.get("report") or {}).get("summary") or "")[:2000]
    prospects = (await db.execute(select(SupplierProspect).where(SupplierProspect.discovery_id == d.id).order_by(SupplierProspect.fit.desc().nullslast()))).scalars().all()
    return {"id": str(d.id), "status": d.status, "error": d.error, "summary": d.summary, "prospects": d.prospects, "items": [_prospect(p) for p in prospects]}


async def _store_prospects(db, tenant_id, d: SourcingDiscovery, run: dict, view: dict) -> int:
    d_ = view.get("definition") or {}
    terms = [w for w in f"{view.get('name', '')} {view.get('family', '')} {view.get('range', '')} {d_.get('customer_name', '')}".replace("/", " ").split() if len(w) > 2]
    report_text = " ".join([str((run.get("report") or {}).get("summary") or "")] + [str(f.get("claim") or "") for f in (run.get("report") or {}).get("key_findings") or []])
    made = 0
    for src in run.get("sources") or []:
        url = str(src.get("url") or "")
        domain = S.domain_of(url)
        if not domain or any(m in domain for m in S.MARKETPLACES):
            continue
        exists = (await db.execute(select(SupplierProspect.id).where(SupplierProspect.tenant_id == tenant_id, SupplierProspect.domain == domain,
                                                                      SupplierProspect.product_id == d.product_id))).first()
        if exists:
            continue
        title = str(src.get("title") or "")
        note = " ".join(str(src.get(k) or "") for k in ("snippet", "description", "text"))[:600]
        db.add(SupplierProspect(tenant_id=tenant_id, product_id=d.product_id, discovery_id=d.id, name=S.prospect_name(title, domain), domain=domain, website=url[:400],
                                summary=(note or title)[:600], fit=S.fit_score(f"{title} {note} {report_text if domain.split('.')[0] in report_text.lower() else ''}", terms),
                                country="South Africa" if domain.endswith(".za") else None, status="new"))
        made += 1
    return made


@router.get("/prospects", dependencies=[Depends(require_tier("write"))])
async def list_prospects(product_id: Optional[uuid.UUID] = None, status: Optional[str] = None, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    q = select(SupplierProspect).where(SupplierProspect.tenant_id == tenant_id)
    if product_id:
        q = q.where(SupplierProspect.product_id == product_id)
    if status:
        q = q.where(SupplierProspect.status == status)
    return [_prospect(p) for p in (await db.execute(q.order_by(SupplierProspect.fit.desc().nullslast(), SupplierProspect.created_at.desc()).limit(200))).scalars()]


class ProspectPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)
    status: Optional[Literal["new", "dismissed"]] = None


@router.patch("/prospects/{prospect_id}", dependencies=[Depends(require_tier("write"))])
async def patch_prospect(prospect_id: uuid.UUID, body: ProspectPatch, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    p = (await db.execute(select(SupplierProspect).where(SupplierProspect.id == prospect_id, SupplierProspect.tenant_id == tenant_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Prospect not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "email" and v:
            v = v.strip().lower()
            if "@" not in v or " " in v:
                raise HTTPException(422, "That does not look like an email address")
        setattr(p, k, v)
    return _prospect(p)


async def _convert(db, tenant_id, p: SupplierProspect) -> Supplier:
    if p.supplier_id:
        s = (await db.execute(select(Supplier).where(Supplier.id == p.supplier_id, Supplier.tenant_id == tenant_id))).scalar_one_or_none()
        if s:
            return s
    base = (p.domain.split(".")[0] or "supplier")[:30]
    code, n = base, 1
    while (await db.execute(select(Supplier.id).where(Supplier.tenant_id == tenant_id, Supplier.code == code))).first():
        n += 1
        code = f"{base}-{n}"
    s = Supplier(tenant_id=tenant_id, code=code, name=p.name, email=p.email, phone=p.phone, notes=f"Found by sourcing search: {p.website}", is_active=True)
    db.add(s)
    await db.flush()
    p.supplier_id, p.status = s.id, "converted"
    return s


@router.post("/prospects/{prospect_id}/convert", dependencies=[Depends(require_tier("write"))])
async def convert_prospect(prospect_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Add a prospect to the supplier master. Complete their VAT number, address and account number in Suppliers."""
    p = (await db.execute(select(SupplierProspect).where(SupplierProspect.id == prospect_id, SupplierProspect.tenant_id == tenant_id).with_for_update())).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Prospect not found")
    s = await _convert(db, tenant_id, p)
    return {"supplier_id": str(s.id), "name": s.name}


@router.get("/candidates", dependencies=[Depends(require_tier("write"))])
async def candidates(product_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Who can be invited for a product: its current suppliers, other suppliers (internal and external) and web prospects."""
    protocol = await _protocol(db, tenant_id)
    view = _view(await _get(db, tenant_id, product_id))
    sources = {str(s["supplier_id"]) for s in (view["definition"].get("sources") or [])}
    kinds, facts = await _kinds(db, tenant_id), await load_facts(db, tenant_id, 12)
    sup = []
    for s in (await db.execute(select(Supplier).where(Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None), Supplier.is_active.is_(True)).order_by(Supplier.name))).scalars():
        kind = kinds.get(str(s.id), "external")
        m = metrics_for(facts, str(s.id), str(view["inventory_product_id"]) if view.get("inventory_product_id") else None)
        allowed = (protocol.allow_internal if kind == "internal" else protocol.allow_external)
        score = m.get("score")
        sup.append({"supplier_id": str(s.id), "name": s.name, "email": s.email, "kind": kind, "current_source": str(s.id) in sources, "score": score,
                    "eligible": allowed and not (protocol.min_supplier_score and score is not None and score < protocol.min_supplier_score),
                    "reason": None if allowed else f"The protocol does not allow {kind} suppliers"})
    prospects = (await db.execute(select(SupplierProspect).where(SupplierProspect.tenant_id == tenant_id, SupplierProspect.product_id == product_id,
                                                                 SupplierProspect.status.in_(("new", "invited"))).order_by(SupplierProspect.fit.desc().nullslast()))).scalars().all()
    return {"suppliers": sup, "prospects": [_prospect(p) for p in prospects], "protocol": {"max_suppliers": protocol.max_suppliers_per_request}}


# ── RFI / RFQ ────────────────────────────────────────────────────────────────

class InviteIn(BaseModel):
    supplier_id: Optional[uuid.UUID] = None
    prospect_id: Optional[uuid.UUID] = None
    email: Optional[str] = Field(None, max_length=255)


class RequestIn(BaseModel):
    kind: Literal["RFI", "RFQ"]
    product_id: uuid.UUID
    quantity: Optional[int] = Field(None, ge=1, le=10_000_000)
    target_price: Optional[Decimal] = Field(None, ge=0)
    needed_by: Optional[date] = None
    invitees: list[InviteIn] = Field(default_factory=list, max_length=50)
    ai: bool = True
    subject: Optional[str] = Field(None, max_length=300)
    body: Optional[str] = Field(None, max_length=8000)
    source: Literal["manual", "reorder_scan", "agent"] = "manual"
    agent: Optional[str] = Field(None, max_length=40)


async def create_request(db, tenant_id, user_id, body: RequestIn) -> SourcingRequest:
    protocol = await _protocol(db, tenant_id)
    if len(body.invitees) > protocol.max_suppliers_per_request:
        raise HTTPException(409, f"The procurement protocol allows at most {protocol.max_suppliers_per_request} suppliers per request")
    cat = await _get(db, tenant_id, body.product_id)
    view = _view(cat)
    kinds, facts = await _kinds(db, tenant_id), await load_facts(db, tenant_id, 12)
    rows: list[SourcingInvitee] = []
    seen: set = set()
    for inv in body.invitees:
        if bool(inv.supplier_id) == bool(inv.prospect_id):
            raise HTTPException(422, "Each invitee needs a supplier or a prospect")
        key = inv.supplier_id or inv.prospect_id
        if key in seen:
            continue
        seen.add(key)
        if inv.supplier_id:
            s = (await db.execute(select(Supplier).where(Supplier.id == inv.supplier_id, Supplier.tenant_id == tenant_id, Supplier.deleted_at.is_(None)))).scalar_one_or_none()
            if s is None:
                raise HTTPException(404, "Supplier not found")
            kind = kinds.get(str(s.id), "external")
            score = metrics_for(facts, str(s.id)).get("score")
            if kind == "internal" and not protocol.allow_internal or kind == "external" and not protocol.allow_external:
                raise HTTPException(409, f"The procurement protocol does not allow {kind} suppliers ({s.name})")
            if protocol.min_supplier_score and score is not None and score < protocol.min_supplier_score:
                raise HTTPException(409, f"{s.name} scores {score:.0f}, below the protocol minimum of {protocol.min_supplier_score}")
            rows.append(SourcingInvitee(tenant_id=tenant_id, supplier_id=s.id, name=s.name, email=(inv.email or s.email or None), kind=kind))
        else:
            if not protocol.allow_external:
                raise HTTPException(409, "The procurement protocol does not allow external suppliers")
            p = (await db.execute(select(SupplierProspect).where(SupplierProspect.id == inv.prospect_id, SupplierProspect.tenant_id == tenant_id))).scalar_one_or_none()
            if p is None:
                raise HTTPException(404, "Prospect not found")
            rows.append(SourcingInvitee(tenant_id=tenant_id, prospect_id=p.id, name=p.name, email=(inv.email or p.email or None), kind="external"))
    number = await next_sequence_number(db, tenant_id, body.kind.lower(), body.kind)
    drafted = {"subject": body.subject or "", "body": body.body or "", "drafted_by": "user"}
    if not (body.subject and body.body):
        if body.ai:
            drafted = await S.draft_request(body.kind, view, await _company(db, tenant_id), body.quantity, body.needed_by,
                                            float(body.target_price) if body.target_price is not None else None, protocol, number)
        else:
            subject, text_ = S.template_request(body.kind, view, await _company(db, tenant_id), body.quantity, body.needed_by,
                                                float(body.target_price) if body.target_price is not None else None, protocol.share_target_price,
                                                protocol.reply_window_days, number)
            drafted = {"subject": body.subject or subject, "body": body.body or text_, "drafted_by": "template"}
    r = SourcingRequest(tenant_id=tenant_id, number=number, kind=body.kind, product_id=body.product_id, title=f"{body.kind} {view['name']}"[:200], quantity=body.quantity,
                        target_price=body.target_price, needed_by=body.needed_by, subject=drafted["subject"][:300], body=drafted["body"], drafted_by=drafted["drafted_by"],
                        status="draft", created_by=user_id, created_by_agent=body.agent, source=body.source)
    db.add(r)
    await db.flush()
    for i in rows:
        i.request_id = r.id
        db.add(i)
    for inv in body.invitees:
        if inv.prospect_id:
            p = await db.get(SupplierProspect, inv.prospect_id)
            if p and p.status == "new":
                p.status = "invited"
    await db.flush()
    return r


@router.post("/requests", status_code=201, dependencies=[Depends(require_tier("write"))])
async def post_request(body: RequestIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    r = await create_request(db, tenant_id, user_id, body)
    return {**_req(r), "invitees": [_inv(i) for i in await _invitees(db, r.id)]}


@router.get("/requests", dependencies=[Depends(require_tier("write"))])
async def list_requests(status: Optional[str] = None, product_id: Optional[uuid.UUID] = None, limit: int = Query(100, ge=1, le=300),
                        tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    q = select(SourcingRequest).where(SourcingRequest.tenant_id == tenant_id)
    if status:
        q = q.where(SourcingRequest.status == status)
    if product_id:
        q = q.where(SourcingRequest.product_id == product_id)
    rows = (await db.execute(q.order_by(SourcingRequest.created_at.desc()).limit(limit))).scalars().all()
    names = {r.id: r.name for r in await _all(db, tenant_id)}
    counts = dict((await db.execute(select(SourcingResponse.request_id, func.count()).where(SourcingResponse.tenant_id == tenant_id).group_by(SourcingResponse.request_id))).all())
    invited = dict((await db.execute(select(SourcingInvitee.request_id, func.count()).where(SourcingInvitee.tenant_id == tenant_id).group_by(SourcingInvitee.request_id))).all())
    return [{**_req(r, names), "replies": counts.get(r.id, 0), "invited": invited.get(r.id, 0)} for r in rows]


@router.get("/requests/{rid}", dependencies=[Depends(require_tier("write"))])
async def get_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    r = await _load_request(db, tenant_id, rid)
    names = {x.id: x.name for x in await _all(db, tenant_id)}
    resp = (await db.execute(select(SourcingResponse).where(SourcingResponse.request_id == rid).order_by(SourcingResponse.created_at))).scalars().all()
    return {**_req(r, names), "invitees": [_inv(i) for i in await _invitees(db, rid)], "responses": [_resp(x) for x in resp]}


class DraftPatch(BaseModel):
    subject: Optional[str] = Field(None, min_length=3, max_length=300)
    body: Optional[str] = Field(None, min_length=10, max_length=8000)
    regenerate: bool = False


@router.patch("/requests/{rid}", dependencies=[Depends(require_tier("write"))])
async def edit_request(rid: uuid.UUID, body: DraftPatch, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Edit the message (or have the AI draft it again) while the request is still a draft."""
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.status not in ("draft", "pending_approval", "approved"):
        raise HTTPException(409, "A request that has been sent can no longer be edited")
    if body.regenerate:
        view = _view(await _get(db, tenant_id, r.product_id))
        d = await S.draft_request(r.kind, view, await _company(db, tenant_id), r.quantity, r.needed_by,
                                  float(r.target_price) if r.target_price is not None else None, await _protocol(db, tenant_id), r.number)
        r.subject, r.body, r.drafted_by = d["subject"][:300], d["body"], d["drafted_by"]
    if body.subject:
        r.subject, r.drafted_by = body.subject, "user"
    if body.body:
        r.body, r.drafted_by = body.body, "user"
    if r.status in ("pending_approval", "approved") and (body.subject or body.body or body.regenerate):
        r.status, r.approved_by, r.approved_at = "draft", None, None          # an edited message has to be approved again
    return _req(r)


@router.post("/requests/{rid}/submit", dependencies=[Depends(require_tier("write"))])
async def submit_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.status != "draft":
        raise HTTPException(409, f"Only a draft can be submitted (this one is {r.status})")
    if not await _invitees(db, rid):
        raise HTTPException(422, "Add at least one supplier to invite")
    protocol = await _protocol(db, tenant_id)
    if protocol.outreach_requires_approval:
        r.status = "pending_approval"
        await _notify(db, tenant_id, f"{r.number} needs approval", f"{r.kind} for {r.title.split(' ', 1)[-1]} is ready to send to suppliers.")
    else:
        r.status, r.approved_by, r.approved_at = "approved", user_id, datetime.now(timezone.utc)
    await _event(db, tenant_id, user_id, "request.submitted", {"request_id": str(r.id), "number": r.number})
    return _req(r)


async def _notify(db, tenant_id, title: str, body: str) -> None:
    try:
        from services.common.event_bus import notify
        async with db.begin_nested():
            await notify(db, tenant_id, title, body=body, category="procurement", link="/dashboard?module=products&tab=sourcing")
    except Exception:  # noqa: BLE001 - the bell is advisory
        logger.debug("notification not stored", exc_info=True)


@router.post("/requests/{rid}/approve", dependencies=[Depends(require_tier("manager"))])
async def approve_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.status != "pending_approval":
        raise HTTPException(409, f"Only a request waiting for approval can be approved (this one is {r.status})")
    protocol = await _protocol(db, tenant_id)
    if not protocol.allow_self_approval and user_id == r.created_by:
        raise HTTPException(403, "The person who prepared a request cannot approve it under the current protocol")
    r.status, r.approved_by, r.approved_at = "approved", user_id, datetime.now(timezone.utc)
    return _req(r)


@router.post("/requests/{rid}/reject", dependencies=[Depends(require_tier("manager"))])
async def reject_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.status != "pending_approval":
        raise HTTPException(409, "Only a request waiting for approval can be sent back")
    r.status = "draft"
    return _req(r)


async def _mailbox(tenant_id, user_id, protocol: S.Protocol) -> str:
    if protocol.mailbox_id:
        return protocol.mailbox_id
    try:
        boxes = await _request("GET", "communication", "/api/v1/mail/mailboxes", tenant_id=tenant_id, user_id=user_id, timeout=15.0, retries=1)
    except Exception as exc:  # noqa: BLE001
        code = getattr(getattr(exc, "response", None), "status_code", None)
        raise HTTPException(409 if code in (401, 403) else 502,
                            "The mail service would not list the mailboxes" + (" (your account needs mail access)." if code in (401, 403) else ". Try again shortly."))
    boxes = [b for b in (boxes if isinstance(boxes, list) else []) if b.get("is_active", True)]
    if not boxes:
        raise HTTPException(409, "No mailbox is set up to send from. Create one in Communication, or choose one in the procurement protocol.")
    return str(boxes[0]["id"])


@router.post("/requests/{rid}/send", dependencies=[Depends(require_tier("write"))])
async def send_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id),
                        auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """Send the request to every invitee: external ones by email, internal ones through the in-app bell. Each outcome is recorded.

    A request waiting for approval can be sent by a manager in one step (their action is the approval); this is also how an agent's
    approved "send" runs."""
    r = await _load_request(db, tenant_id, rid, lock=True)
    protocol = await _protocol(db, tenant_id)
    if r.status == "pending_approval":
        try:
            await require_access(auth, "manager")
        except HTTPException:
            raise HTTPException(409, "This request is waiting for a manager's approval before it can be sent.")
        if not protocol.allow_self_approval and user_id == r.created_by:
            raise HTTPException(403, "The person who prepared a request cannot approve it under the current protocol")
        r.status, r.approved_by, r.approved_at = "approved", user_id, datetime.now(timezone.utc)
    if r.status not in ("approved", "sent"):
        if protocol.outreach_requires_approval or r.status != "draft":
            raise HTTPException(409, f"This request is {r.status}. Submit it and have it approved before it is sent." if protocol.outreach_requires_approval
                                else f"This request is {r.status} and cannot be sent")
    invitees = [i for i in await _invitees(db, rid) if i.status in ("invited", "failed")]
    if not invitees:
        raise HTTPException(409, "Everyone has already been sent this request")
    external = [i for i in invitees if i.kind == "external"]
    mailbox = None
    if external:
        if not protocol.allow_external:
            raise HTTPException(409, "The procurement protocol does not allow external suppliers")
        mailbox = await _mailbox(tenant_id, user_id, protocol)
    sent = failed = 0
    for i in invitees:
        now = datetime.now(timezone.utc)
        if i.kind == "internal":
            await _notify(db, tenant_id, f"{r.number}: {r.subject}", f"Internal request to {i.name}: {r.body[:400]}")
            i.status, i.sent_at, i.error = "sent", now, None
            sent += 1
            continue
        if not i.email:
            i.status, i.error = "failed", "No email address on file for this supplier"
            failed += 1
            continue
        try:
            await _request("POST", "communication", "/api/v1/mail/send", tenant_id=tenant_id, user_id=user_id, timeout=30.0, retries=0,
                           json={"mailbox_id": mailbox, "to": [i.email], "subject": r.subject, "body_text": r.body})
            i.status, i.sent_at, i.error = "sent", now, None
            sent += 1
        except Exception as exc:  # noqa: BLE001 - one bad address must not stop the others
            i.status, i.error = "failed", (str(getattr(getattr(exc, "response", None), "text", "") or exc))[:300]
            failed += 1
    if sent:
        r.status, r.sent_at = "sent", r.sent_at or datetime.now(timezone.utc)
    await _event(db, tenant_id, user_id, "request.sent", {"request_id": str(r.id), "number": r.number, "sent": sent, "failed": failed})
    return {"sent": sent, "failed": failed, "status": r.status, "invitees": [_inv(i) for i in await _invitees(db, rid)]}


class ResponseIn(BaseModel):
    invitee_id: uuid.UUID
    unit_price: Optional[Decimal] = Field(None, gt=0, max_digits=14, decimal_places=2)
    lead_time_days: Optional[int] = Field(None, ge=0, le=730)
    moq: Optional[int] = Field(None, ge=1, le=10_000_000)
    valid_until: Optional[date] = None
    notes: str = Field("", max_length=1000)
    declined: bool = False
    raw: str = Field("", max_length=12000)
    source: Literal["manual", "parsed"] = "manual"


@router.post("/requests/{rid}/responses", status_code=201, dependencies=[Depends(require_tier("write"))])
async def record_response(rid: uuid.UUID, body: ResponseIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.status in ("draft", "pending_approval", "cancelled"):
        raise HTTPException(409, "Nothing has been sent yet, so there can be no replies")
    inv = (await db.execute(select(SourcingInvitee).where(SourcingInvitee.id == body.invitee_id, SourcingInvitee.request_id == rid))).scalar_one_or_none()
    if inv is None:
        raise HTTPException(404, "That supplier was not invited to this request")
    if not body.declined and r.kind == "RFQ" and body.unit_price is None:
        raise HTTPException(422, "A quotation needs a unit price (or mark the supplier as declined)")
    old = (await db.execute(select(SourcingResponse).where(SourcingResponse.invitee_id == inv.id))).scalar_one_or_none()
    if old is not None:
        await db.delete(old)
        await db.flush()
    row = SourcingResponse(tenant_id=tenant_id, request_id=rid, invitee_id=inv.id, unit_price=body.unit_price, lead_time_days=body.lead_time_days, moq=body.moq,
                           valid_until=body.valid_until, notes=body.notes, raw=body.raw, source=body.source, declined=body.declined, created_by=user_id)
    db.add(row)
    inv.status = "declined" if body.declined else "replied"
    await db.flush()
    return _resp(row)


class ParseIn(BaseModel):
    text: str = Field(..., min_length=5, max_length=12000)


@router.post("/requests/{rid}/parse-reply", dependencies=[Depends(require_tier("write"))])
async def parse_reply(rid: uuid.UUID, body: ParseIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    """Read pasted reply text into quotation fields. Nothing is saved: confirm the numbers, then record the response."""
    await _load_request(db, tenant_id, rid)
    return await S.read_reply(body.text)


async def compare(db, tenant_id, r: SourcingRequest) -> dict:
    protocol = await _protocol(db, tenant_id)
    invitees = {i.id: i for i in await _invitees(db, r.id)}
    resp = {x.invitee_id: x for x in (await db.execute(select(SourcingResponse).where(SourcingResponse.request_id == r.id))).scalars()}
    facts = await load_facts(db, tenant_id, 12)
    cat_rows = await _all(db, tenant_id)
    catalogue = _catalogue_map(cat_rows)
    view = catalogue.get(str(r.product_id)) if r.product_id else None
    priced = [{"unit_price": x.unit_price, "lead_time_days": x.lead_time_days} for x in resp.values() if not x.declined and x.unit_price]
    rows = []
    for iid, inv in invitees.items():
        x = resp.get(iid)
        row = {"invitee_id": str(iid), "name": inv.name, "kind": inv.kind, "supplier_id": str(inv.supplier_id) if inv.supplier_id else None, "status": inv.status,
               "unit_price": None, "lead_time_days": None, "moq": None, "valid_until": None, "notes": "", "declined": False, "score": None, "flags": []}
        if x is not None:
            row.update({"unit_price": float(x.unit_price) if x.unit_price is not None else None, "lead_time_days": x.lead_time_days, "moq": x.moq,
                        "valid_until": x.valid_until.isoformat() if x.valid_until else None, "notes": x.notes, "declined": x.declined})
        if x is not None and not x.declined and x.unit_price:
            perf = metrics_for(facts, str(inv.supplier_id)) if inv.supplier_id else {}
            perf_score = perf.get("score") if perf.get("deliveries", 0) >= 3 else None
            sc = S.supply_score({"unit_price": x.unit_price, "lead_time_days": x.lead_time_days, "moq": x.moq, "valid_until": x.valid_until}, priced, protocol.weights, perf_score)
            row["score"], row["breakdown"] = sc["score"], sc
            if not sc["track_record"]:
                row["flags"].append("No delivery track record with us yet")
            elif protocol.min_supplier_score and perf_score is not None and perf_score < protocol.min_supplier_score:
                row["flags"].append(f"Delivery score {perf_score:.0f} is below the protocol minimum of {protocol.min_supplier_score}")
            if x.valid_until and x.valid_until < date.today():
                row["flags"].append("The quotation has expired")
            if r.quantity and x.moq and x.moq > r.quantity:
                row["flags"].append(f"Minimum order {x.moq} is more than the {r.quantity} requested")
            total = float(x.unit_price) * (r.quantity or 1)
            row["total"] = round(total, 2)
            if protocol.rfq_budget_limit_zar and total > protocol.rfq_budget_limit_zar:
                row["flags"].append(f"Order value R{total:,.0f} is above the protocol limit of R{protocol.rfq_budget_limit_zar:,.0f}: needs escalation")
            if view is not None:
                d = dict(view.get("definition") or {})
                key = str(inv.supplier_id or inv.prospect_id or iid)
                d["sources"] = [{"supplier_id": key, "unit_cost": float(x.unit_price), "preferred": True, "cadence": "Once-off", "lead_time_days": x.lead_time_days}]
                try:
                    e = rules.economics(str(r.product_id), {**catalogue, str(r.product_id): {**view, "definition": d}}, supplier_id=key, names={key: inv.name})
                    row["margin_pct"] = e.get("margin_pct") if e.get("complete") else None
                except Exception:  # noqa: BLE001
                    row["margin_pct"] = None
        rows.append(row)
    scored = sorted([x for x in rows if x["score"] is not None], key=lambda x: -x["score"])
    best = scored[0] if scored else None
    return {"request": _req(r), "rows": sorted(rows, key=lambda x: (x["score"] is None, -(x["score"] or 0))), "best": best["invitee_id"] if best else None,
            "replies": len(scored), "needed": protocol.min_quotes_before_award,
            "ready_to_award": len(scored) >= protocol.min_quotes_before_award, "weights": protocol.weights.model_dump()}


@router.get("/requests/{rid}/compare", dependencies=[Depends(require_tier("write"))])
async def compare_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    return await compare(db, tenant_id, await _load_request(db, tenant_id, rid))


class AwardIn(BaseModel):
    invitee_id: uuid.UUID
    reason: str = Field("", max_length=500)
    add_source: bool = True                       # record the winner as a supplier source on the product
    make_preferred: bool = False                  # and make them the preferred supplier (draft and in-review products only)
    create_po: bool = True                        # prepare a draft purchase order at the quoted price
    warehouse_id: Optional[uuid.UUID] = None      # where it is delivered (default: the only active warehouse)


async def apply_award_source(db, tenant_id, user_id, r: SourcingRequest, supplier_id: uuid.UUID, quote: dict, make_preferred: bool) -> dict:
    """Make the awarded supplier a source on the product at the quoted price and lead time.

    An active product's commercial fields (which include the automatic purchase-cost line) change through a revision, so for a launched
    product the supplier is added or updated without becoming preferred and without touching the preferred supplier's price."""
    cat = await _get(db, tenant_id, r.product_id)
    old = cat.definition or {}
    if cat.status == "archived":
        return {"status": "skipped", "note": "The product is archived."}
    active = cat.status == "active"
    sid = str(supplier_id)
    note_text = f"From {r.number}" + (f" (valid until {quote['valid_until']})" if quote.get("valid_until") else "")

    def build(prefer: bool, reprice_preferred: bool) -> tuple[dict, bool]:
        d = {**old, "sources": [dict(s) for s in old.get("sources") or []]}
        row = next((s for s in d["sources"] if str(s["supplier_id"]) == sid), None)
        added = row is None
        if added:
            d["sources"].append({"supplier_id": sid, "supplier_sku": "", "unit_cost": quote["unit_price"], "cadence": "Once-off",
                                 "lead_time_days": quote.get("lead_time_days"), "moq": quote.get("moq"), "preferred": False, "notes": note_text})
        elif reprice_preferred or not row.get("preferred"):
            row.update({"unit_cost": quote["unit_price"], "lead_time_days": quote.get("lead_time_days"), "moq": quote.get("moq"), "notes": note_text})
        if prefer:
            for s in d["sources"]:
                s["preferred"] = str(s["supplier_id"]) == sid
        return d, added

    new_def, added = build(make_preferred and not active, reprice_preferred=not active)
    try:
        await _normalise_definition_sources(db, tenant_id, new_def)
    except HTTPException as exc:
        return {"status": "skipped", "note": str(exc.detail)}
    if active and rules.commercial_changes(old, new_def):
        new_def, added = build(False, reprice_preferred=False)
        await _normalise_definition_sources(db, tenant_id, new_def)
        if rules.commercial_changes(old, new_def):
            return {"status": "skipped", "note": "A launched product's cost changes through a revision. Update the supplier price there."}
    note = ""
    if active and (make_preferred or any(str(s["supplier_id"]) == sid and s.get("preferred") for s in old.get("sources") or [])):
        note = "The product is launched, so the preferred supplier and their price were left alone. Change them through a revision."
    if new_def == old:
        return {"status": "unchanged", "preferred": any(str(s["supplier_id"]) == sid and s.get("preferred") for s in new_def["sources"]),
                "note": note or "The product already lists this supplier at these terms."}
    cat.definition = new_def
    cat.revision += 1
    await db.flush()
    await _log(db, tenant_id, cat.id, "source_from_rfq", user_id, {"request": r.number, "supplier_id": sid, "unit_cost": quote["unit_price"]})
    preferred = any(str(s["supplier_id"]) == sid and s.get("preferred") for s in new_def["sources"])
    return {"status": "added" if added else "updated", "preferred": preferred, "note": note}


async def draft_award_po(db, tenant_id, user_id, r: SourcingRequest, supplier_id: uuid.UUID, quote: dict, warehouse_id: Optional[uuid.UUID]) -> dict:
    """A draft purchase order at the quoted price. It goes through the normal approval journey; nothing is committed to the supplier."""
    from services.inventory.routes.purchasing import POItemInput, PurchaseOrderCreate, create_purchase_order
    cat = await _get(db, tenant_id, r.product_id)
    if not cat.inventory_product_id:
        return {"status": "skipped", "note": "The product has no stock item yet: launch it in Product Management first."}
    wid = warehouse_id
    if wid is None:
        whs = (await db.execute(select(Warehouse.id).where(Warehouse.tenant_id == tenant_id, Warehouse.is_active.is_(True)))).scalars().all()
        if len(whs) != 1:
            return {"status": "skipped", "note": "Choose the warehouse to deliver to." if whs else "There is no warehouse to deliver to yet."}
        wid = whs[0]
    qty = max(int(r.quantity or 1), int(quote.get("moq") or 1))
    try:
        async with db.begin_nested():
            po = await create_purchase_order(
                body=PurchaseOrderCreate(supplier_id=supplier_id, warehouse_id=wid, notes=f"From {r.number}",
                                         expected_delivery=(date.today() + timedelta(days=int(quote["lead_time_days"]))) if quote.get("lead_time_days") is not None else None,
                                         items=[POItemInput(product_id=cat.inventory_product_id, quantity_ordered=qty, unit_cost_zar=Decimal(str(quote["unit_price"])))]),
                tenant_id=tenant_id, user_id=user_id, db=db)
    except HTTPException as exc:
        return {"status": "skipped", "note": str(exc.detail)[:300]}
    return {"status": "drafted", "id": str(po.id), "po_number": po.po_number, "quantity": qty,
            "note": "Submit it to start the approval journey." + (f" Quantity raised to the supplier's minimum order of {qty}." if qty != (r.quantity or 1) else "")}


@router.post("/requests/{rid}/award", dependencies=[Depends(require_tier("manager"))])
async def award_request(rid: uuid.UUID, body: AwardIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    """Choose the winner. The protocol's minimum number of replies applies (a written reason can override); a web prospect becomes a supplier,
    the winner is added to the product as a supplier source, and a draft purchase order is prepared at the quoted price."""
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.kind != "RFQ":
        raise HTTPException(409, "Only a request for quotation can be awarded")
    if r.status == "awarded":
        raise HTTPException(409, "This request has already been awarded")
    if r.status != "sent":
        raise HTTPException(409, f"This request is {r.status}")
    c = await compare(db, tenant_id, r)
    row = next((x for x in c["rows"] if x["invitee_id"] == str(body.invitee_id)), None)
    if row is None or row["score"] is None:
        raise HTTPException(422, "Pick a supplier that sent a priced quotation")
    if not c["ready_to_award"] and len(body.reason.strip()) < 10:
        raise HTTPException(409, f"The protocol asks for {c['needed']} quotations before an award; {c['replies']} received. Give a reason (at least 10 characters) to award anyway.")
    inv = (await db.execute(select(SourcingInvitee).where(SourcingInvitee.id == body.invitee_id))).scalar_one()
    supplier_id = inv.supplier_id
    if supplier_id is None and inv.prospect_id:
        p = (await db.execute(select(SupplierProspect).where(SupplierProspect.id == inv.prospect_id).with_for_update())).scalar_one()
        s = await _convert(db, tenant_id, p)
        inv.supplier_id, supplier_id = s.id, s.id
    r.status, r.awarded_invitee_id, r.closed_at = "awarded", inv.id, datetime.now(timezone.utc)
    r.award_note = body.reason.strip()[:500]
    quote = {"unit_price": row["unit_price"], "lead_time_days": row["lead_time_days"], "moq": row["moq"], "valid_until": row["valid_until"]}
    source = po = None
    if r.product_id and body.add_source:
        async with db.begin_nested():
            source = await apply_award_source(db, tenant_id, user_id, r, supplier_id, quote, body.make_preferred)
    if r.product_id and body.create_po:
        po = await draft_award_po(db, tenant_id, user_id, r, supplier_id, quote, body.warehouse_id)
    await _event(db, tenant_id, user_id, "request.awarded", {"request_id": str(r.id), "number": r.number, "supplier_id": str(supplier_id)})
    return {"status": "awarded", "supplier_id": str(supplier_id), "name": inv.name, "unit_price": row["unit_price"], "lead_time_days": row["lead_time_days"],
            "quantity": r.quantity, "flags": row["flags"], "product_id": str(r.product_id) if r.product_id else None, "source": source, "purchase_order": po}


@router.post("/requests/{rid}/close", dependencies=[Depends(require_tier("write"))])
async def close_request(rid: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    r = await _load_request(db, tenant_id, rid, lock=True)
    if r.status in ("awarded", "closed", "cancelled"):
        raise HTTPException(409, f"This request is already {r.status}")
    r.status, r.closed_at = ("cancelled" if r.status in ("draft", "pending_approval", "approved") else "closed"), datetime.now(timezone.utc)
    return _req(r)


# ── what to buy: product KPIs and stock ──────────────────────────────────────

async def reorder_suggestions(db, tenant_id) -> list[dict]:
    """For each launched stock product: sales rate, stock cover and on-order quantity against the protocol's cover target."""
    protocol = await _protocol(db, tenant_id)
    cfg = protocol.reorder
    rows = [r for r in await _all(db, tenant_id) if r.status == "active" and r.inventory_product_id]
    catalogue = _catalogue_map(await _all(db, tenant_id))
    since = datetime.now(timezone.utc) - timedelta(days=cfg.lookback_days)
    sold = dict((await db.execute(select(StockMovement.product_id, func.coalesce(func.sum(StockMovement.quantity), 0)).where(
        StockMovement.tenant_id == tenant_id, StockMovement.movement_type == "customer_dispatch", StockMovement.created_at >= since).group_by(StockMovement.product_id))).all())
    levels = {pid: (soh, alloc, res) for pid, soh, alloc, res in (await db.execute(select(
        InventoryLevel.product_id, func.coalesce(func.sum(InventoryLevel.soh), 0), func.coalesce(func.sum(InventoryLevel.allocated), 0),
        func.coalesce(func.sum(InventoryLevel.reserved), 0)).where(InventoryLevel.tenant_id == tenant_id).group_by(InventoryLevel.product_id))).all()}
    on_order = dict((await db.execute(select(PurchaseOrderItem.product_id, func.coalesce(func.sum(PurchaseOrderItem.quantity_ordered - PurchaseOrderItem.quantity_received), 0))
                                      .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.po_id)
                                      .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.deleted_at.is_(None),
                                             PurchaseOrder.status.in_(("submitted", "pending_approval", "approved", "sent", "partially_received"))).group_by(PurchaseOrderItem.product_id))).all())
    open_req = {x for x in (await db.execute(select(SourcingRequest.product_id).where(SourcingRequest.tenant_id == tenant_id, SourcingRequest.status.in_(OPEN_STATUSES)))).scalars()}
    facts = await load_facts(db, tenant_id, 12)
    out = []
    for r in rows:
        d = r.definition or {}
        if d.get("stock", "None") == "None":
            continue
        mode = (d.get("offer") or {}).get("mode") or "sold"
        soh, alloc, res = levels.get(r.inventory_product_id, (0, 0, 0))
        avail = int(soh) - int(alloc) - int(res)
        per_day = float(sold.get(r.inventory_product_id, 0) or 0) / cfg.lookback_days
        incoming = int(on_order.get(r.inventory_product_id, 0) or 0)
        cover = None if per_day <= 0 else round(avail / per_day, 1)
        want = math.ceil(per_day * cfg.cover_days) - avail - incoming
        if per_day <= 0 and avail > 0:
            continue
        qty = max(0, want) if per_day > 0 else (1 if avail <= 0 and mode != "sold" else 0)
        if qty <= 0:
            continue
        pref = next((s for s in d.get("sources") or [] if s.get("preferred")), None)
        e = rules.economics(str(r.id), catalogue, supplier_id=str(pref["supplier_id"]) if pref else None) if pref else {}
        margin = e.get("margin_pct") if e.get("complete") else None
        unit = float(pref.get("unit_cost") or 0) if pref else None
        score = metrics_for(facts, str(pref["supplier_id"]), str(r.inventory_product_id)).get("score") if pref else None
        flags = []
        if mode == "sold" and margin is not None and margin < cfg.min_margin_pct:
            flags.append(f"Margin {margin:.1f}% is below the protocol minimum of {cfg.min_margin_pct:g}%")
        if not pref:
            flags.append("No supplier on the product yet: request quotations")
        if r.id in open_req:
            flags.append("A request is already open for this product")
        out.append({"product_id": str(r.id), "product_number": r.product_number, "name": r.name, "offer_mode": mode, "available": avail, "on_order": incoming,
                    "sales_per_day": round(per_day, 2), "days_of_cover": cover, "suggested_qty": qty,
                    "preferred_supplier_id": str(pref["supplier_id"]) if pref else None, "unit_cost": unit,
                    "estimated_spend": round(unit * qty, 2) if unit is not None else None, "margin_pct": margin, "supplier_score": score,
                    "needs_quotes": pref is None, "flags": flags, "open_request": r.id in open_req})
    return sorted(out, key=lambda x: (x["days_of_cover"] is None, x["days_of_cover"] or 0))


@router.get("/reorder-suggestions", dependencies=[Depends(require_tier("write"))])
async def get_reorder_suggestions(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    protocol = await _protocol(db, tenant_id)
    return {"items": await reorder_suggestions(db, tenant_id), "cover_days": protocol.reorder.cover_days, "lookback_days": protocol.reorder.lookback_days,
            "note": "Based on customer dispatches over the look-back period, stock on hand and quantities already on order."}


@router.post("/automation/run", dependencies=[Depends(require_tier("write"))])
async def run_automation(agent: Optional[str] = Query(None, max_length=40), tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    """Scan the KPIs and prepare a draft RFQ for each product that needs stock and has no open request. Drafts only: nothing is sent."""
    protocol = await _protocol(db, tenant_id)
    made, skipped = [], []
    for s in await reorder_suggestions(db, tenant_id):
        if len(made) >= protocol.reorder.max_requests_per_scan:
            break
        if s["open_request"]:
            skipped.append({"product": s["name"], "why": "A request is already open"})
            continue
        if any("below the protocol minimum" in f for f in s["flags"]):
            skipped.append({"product": s["name"], "why": s["flags"][0]})
            continue
        try:
            cand = await candidates(uuid.UUID(s["product_id"]), tenant_id, db)
        except HTTPException:
            continue
        pool = [c for c in cand["suppliers"] if c["eligible"]]
        pool.sort(key=lambda c: (not c["current_source"], -(c["score"] or 0)))
        invitees = [InviteIn(supplier_id=uuid.UUID(c["supplier_id"])) for c in pool[:protocol.max_suppliers_per_request] if c.get("email") or c["kind"] == "internal"]
        if not invitees:
            skipped.append({"product": s["name"], "why": "No eligible supplier with an email address; run a supplier search first"})
            continue
        r = await create_request(db, tenant_id, user_id, RequestIn(kind="RFQ", product_id=uuid.UUID(s["product_id"]), quantity=s["suggested_qty"], invitees=invitees,
                                                                 source="reorder_scan" if not agent else "agent", agent=agent))
        made.append({"request_id": str(r.id), "number": r.number, "product": s["name"], "quantity": s["suggested_qty"], "invited": len(invitees)})
    return {"created": made, "skipped": skipped, "note": "These are drafts. Submit and approve them to send."}
