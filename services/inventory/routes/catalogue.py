"""Product catalogue API: CRUD for the product journey, managed lists, launch gate and history.

Mounted under /catalogue by services.inventory.main. All reads/writes are tenant scoped. Cost and margin
fields are only returned to callers with inventory write access. Launch is validated here, so the client's
Launch button is a convenience, not the control.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select

from services.common.auth import AuthContext, get_auth_context, get_current_tenant_id, get_current_user_id
from services.inventory import catalogue_rules as rules
from services.inventory.access import require_access, require_tier
from services.inventory.catalogue_models import (CatalogueAsset, CatalogueEvent, CatalogueList, CatalogueProduct,
                                                 CatalogueReservedNumber)
from services.inventory.database import get_session, next_sequence_number

router = APIRouter(prefix="/catalogue", tags=["Catalogue"])

DEFAULT_CATEGORIES = {"Connectivity": ["Home Fibre", "Business Fibre"], "Equipment": ["Wi-Fi Routers"],
                      "Infrastructure": ["Installation Materials"]}
DEFAULT_FAMILIES = ["Fibre", "LTE / 5G", "VoIP", "Hosting", "Installation", "Equipment", "Other"]
Status = Literal["draft", "in_review", "active", "archived"]


# ── schemas ──────────────────────────────────────────────────────────────────

class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Cost(_Loose):
    name: str = ""
    supplier: str = ""
    amount: Decimal = Decimal(0)
    cadence: Literal["Monthly", "Once-off"] = "Monthly"


class Component(_Loose):
    product_id: uuid.UUID
    qty: int = Field(1, ge=1, le=10_000)


class Fee(_Loose):
    id: str = ""
    name: str
    enabled: bool = False
    amount: Decimal = Field(Decimal(0), ge=0)
    cadence: Literal["Once-off", "Monthly", "On event"] = "Once-off"
    mode: Literal["Charge", "Included", "Waived"] = "Charge"
    invoice_label: str = ""
    policy_ref: Optional[str] = None


class Asset(_Loose):
    """Metadata only. Binary upload/storage is a separate service; ``url`` points at stored content."""
    id: str
    name: str
    kind: str = "Document"
    extension: str = ""
    size: int = 0
    url: str = ""
    alt: str = ""
    visibility: Literal["Internal only", "Customer portal"] = "Internal only"
    primary: bool = False
    category: str = "Other"
    version: str = "1"
    effective: str = ""
    acceptance: bool = False


class Competitor(_Loose):
    name: str = ""
    offer: str = ""
    price: Optional[Decimal] = None
    spec: str = ""
    term: str = ""
    date: str = ""
    source: str = ""


class ResearchFinding(_Loose):
    claim: str = Field("", max_length=600)
    source_ids: list[str] = Field([], max_length=15)


class ResearchSource(_Loose):
    id: str = Field("", max_length=12)
    title: str = Field("", max_length=300)
    url: str = Field("", max_length=600)
    domain: str = Field("", max_length=200)

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("source links must be http(s)")
        return v


class MarketResearch(_Loose):
    """AI-assisted research from the BI Studio research API (Firecrawl + cited synthesis), kept with the product."""
    run_id: str = Field("", max_length=64)
    checked_at: str = Field("", max_length=40)
    summary: str = Field("", max_length=2000)
    findings: list[ResearchFinding] = Field([], max_length=20)
    sources: list[ResearchSource] = Field([], max_length=15)


class Research(_Loose):
    rows: list[Competitor] = []
    kpis: list[str] = []
    market: Optional[MarketResearch] = None


class TestResult(_Loose):
    name: str
    result: Literal["Pending", "Pass", "Fail", "Waived"] = "Pending"
    tester: str = ""
    date: str = ""
    notes: str = ""
    evidence: str = ""


class IcasaItem(_Loose):
    id: str = ""
    kind: Literal["Product", "Promotion"] = "Product"
    objectives: str = ""
    reasons: str = ""
    effective: str = ""
    promo_start: str = ""
    promo_end: str = ""
    lodged: str = ""
    ref: str = ""
    ack: bool = False


class Icasa(_Loose):
    required: Optional[bool] = None
    exempt_reason: str = ""
    notice: int = Field(rules.DEFAULT_NOTICE_DAYS, ge=1, le=30)
    items: list[IcasaItem] = []


class Readiness(_Loose):
    tests_required: bool = True
    tests_exempt_reason: str = ""
    tests: list[TestResult] = []
    icasa: Icasa = Icasa()


class Definition(_Loose):
    description: str = Field("", max_length=8000)
    customer_name: str = Field("", max_length=200)
    down: Optional[int] = Field(None, ge=0)
    up: Optional[int] = Field(None, ge=0)
    stock: str = "None"
    unit: str = "Each"
    supplier: str = ""
    price: Decimal = Field(Decimal(0), ge=0)
    recurring: bool = True
    term: int = Field(24, ge=1, le=120)
    launch_date: Optional[str] = None
    costs: list[Cost] = []
    components: list[Component] = []
    fees: list[Fee] = []
    media: list[Asset] = []
    documents: list[Asset] = []
    policy_refs: list[str] = []
    research: Research = Research()
    readiness: Readiness = Readiness()


class ProductIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = ""
    range: str = ""
    family: str = ""
    nature: Literal["Digital service", "Physical item", "Professional service"] = "Digital service"
    usage: Literal["Customer-facing", "Internal consumable", "Company-owned asset"] = "Customer-facing"
    owner: str = ""
    product_number: Optional[str] = None
    definition: Definition = Definition()


class ProductPatch(BaseModel):
    expected_revision: int
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = None
    range: Optional[str] = None
    family: Optional[str] = None
    nature: Optional[Literal["Digital service", "Physical item", "Professional service"]] = None
    usage: Optional[Literal["Customer-facing", "Internal consumable", "Company-owned asset"]] = None
    owner: Optional[str] = None
    product_number: Optional[str] = None
    definition: Optional[Definition] = None
    submit_for_review: bool = False


class RevisionBody(BaseModel):
    expected_revision: int


class ListIn(BaseModel):
    kind: Literal["category", "range", "family"]
    name: str = Field(..., min_length=1, max_length=120)
    parent: str = ""


class ListRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


# ── helpers ──────────────────────────────────────────────────────────────────

async def _can_see_costs(auth: AuthContext) -> bool:
    try:
        await require_access(auth, "write")
        return True
    except HTTPException:
        return False


def _view(p: CatalogueProduct) -> dict:
    return {"id": str(p.id), "product_number": p.product_number, "name": p.name, "category": p.category,
            "range": p.range, "family": p.family, "nature": p.nature, "usage": p.usage, "owner": p.owner,
            "status": p.status, "definition": p.definition or {}, "revision": p.revision}


def _catalogue_map(rows: list[CatalogueProduct]) -> dict[str, dict]:
    return {str(r.id): _view(r) for r in rows}


def _serialise(p: CatalogueProduct, catalogue: dict[str, dict], costs_visible: bool) -> dict:
    v = _view(p)
    e = rules.economics(v["id"], catalogue)
    checks = rules.launch_checks(v, catalogue)
    out = {**v, "created_at": p.created_at, "updated_at": p.updated_at, "launched_at": p.launched_at,
           "checks": checks, "ready_to_launch": all(c["ok"] for c in checks) and p.status not in ("active", "archived"),
           "cost_complete": e["complete"]}
    if costs_visible:
        out["economics"] = {k: (str(val) if isinstance(val, Decimal) else val) for k, val in e.items()}
    else:
        out["definition"] = {**out["definition"], "costs": [], "supplier": ""}
    return out


async def _all(db, tenant_id: uuid.UUID) -> list[CatalogueProduct]:
    return list((await db.execute(select(CatalogueProduct).where(CatalogueProduct.tenant_id == tenant_id))).scalars())


async def _get(db, tenant_id: uuid.UUID, pid: uuid.UUID) -> CatalogueProduct:
    p = (await db.execute(select(CatalogueProduct).where(CatalogueProduct.id == pid,
                                                         CatalogueProduct.tenant_id == tenant_id))).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Product not found")
    return p


async def _log(db, tenant_id, product_id, kind: str, actor, detail: Optional[dict] = None) -> None:
    db.add(CatalogueEvent(tenant_id=tenant_id, product_id=product_id, kind=kind, actor=actor, detail=detail or {}))


async def _next_number(db, tenant_id: uuid.UUID) -> str:
    """Server-assigned OD-000123, skipping any number already used or reserved."""
    for _ in range(50):
        raw = await next_sequence_number(db, tenant_id, "catalogue", "OD")
        number = f"OD-{int(raw.rsplit('-', 1)[1]):06d}"
        if not await _number_taken(db, tenant_id, number):
            return number
    raise HTTPException(503, "Could not allocate a product number")


async def _number_taken(db, tenant_id: uuid.UUID, number: str, exclude: Optional[uuid.UUID] = None) -> bool:
    q = select(func.count()).select_from(CatalogueProduct).where(CatalogueProduct.tenant_id == tenant_id,
                                                                CatalogueProduct.product_number == number)
    if exclude:
        q = q.where(CatalogueProduct.id != exclude)
    if (await db.execute(q)).scalar():
        return True
    return bool((await db.execute(select(func.count()).select_from(CatalogueReservedNumber).where(
        CatalogueReservedNumber.tenant_id == tenant_id, CatalogueReservedNumber.product_number == number))).scalar())


async def _validate_lists(db, tenant_id, category: str, range_: str, family: str) -> None:
    """Classification must come from the managed lists (blank is allowed for a draft)."""
    await _ensure_lists(db, tenant_id)
    if category:
        ok = (await db.execute(select(func.count()).select_from(CatalogueList).where(
            CatalogueList.tenant_id == tenant_id, CatalogueList.kind == "category", CatalogueList.name == category))).scalar()
        if not ok:
            raise HTTPException(422, f"Unknown category '{category}'")
    if range_:
        ok = (await db.execute(select(func.count()).select_from(CatalogueList).where(
            CatalogueList.tenant_id == tenant_id, CatalogueList.kind == "range", CatalogueList.name == range_,
            CatalogueList.parent == category))).scalar()
        if not ok:
            raise HTTPException(422, f"Range '{range_}' does not belong to category '{category}'")
    if family:
        ok = (await db.execute(select(func.count()).select_from(CatalogueList).where(
            CatalogueList.tenant_id == tenant_id, CatalogueList.kind == "family", CatalogueList.name == family))).scalar()
        if not ok:
            raise HTTPException(422, f"Unknown service family '{family}'")


async def _check_components(db, tenant_id, pid: Optional[uuid.UUID], definition: dict, catalogue: dict[str, dict]) -> None:
    for comp in definition.get("components") or []:
        cid = str(comp["product_id"])
        if cid not in catalogue:
            raise HTTPException(422, "An included product does not exist in this tenant's catalogue")
        if pid and (cid == str(pid) or rules.would_cycle(str(pid), cid, catalogue)):
            raise HTTPException(422, "A product cannot include itself or a product that includes it")


async def _ensure_lists(db, tenant_id: uuid.UUID) -> None:
    n = (await db.execute(select(func.count()).select_from(CatalogueList).where(CatalogueList.tenant_id == tenant_id))).scalar()
    if n:
        return
    pos = 0
    for cat, ranges in DEFAULT_CATEGORIES.items():
        db.add(CatalogueList(tenant_id=tenant_id, kind="category", name=cat, parent="", position=pos))
        pos += 1
        for r in ranges:
            db.add(CatalogueList(tenant_id=tenant_id, kind="range", name=r, parent=cat, position=pos))
            pos += 1
    for f in DEFAULT_FAMILIES:
        db.add(CatalogueList(tenant_id=tenant_id, kind="family", name=f, parent="", position=pos))
        pos += 1
    await db.flush()


# ── managed lists ────────────────────────────────────────────────────────────

@router.get("/lists")
async def get_lists(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    await _ensure_lists(db, tenant_id)
    rows = list((await db.execute(select(CatalogueList).where(CatalogueList.tenant_id == tenant_id)
                                  .order_by(CatalogueList.position))).scalars())
    cats: dict[str, list[str]] = {r.name: [] for r in rows if r.kind == "category"}
    for r in rows:
        if r.kind == "range":
            cats.setdefault(r.parent, []).append(r.name)
    return {"categories": cats, "families": [r.name for r in rows if r.kind == "family"],
            "items": [{"id": str(r.id), "kind": r.kind, "name": r.name, "parent": r.parent} for r in rows]}


@router.post("/lists", status_code=201, dependencies=[Depends(require_tier("write"))])
async def add_list_value(body: ListIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    await _ensure_lists(db, tenant_id)
    name, parent = body.name.strip(), body.parent.strip()
    if body.kind == "range":
        if not parent:
            raise HTTPException(422, "A range needs a parent category")
        if not (await db.execute(select(func.count()).select_from(CatalogueList).where(
                CatalogueList.tenant_id == tenant_id, CatalogueList.kind == "category", CatalogueList.name == parent))).scalar():
            raise HTTPException(422, "Parent category does not exist")
    else:
        parent = ""
    dup = (await db.execute(select(CatalogueList).where(CatalogueList.tenant_id == tenant_id, CatalogueList.kind == body.kind,
                                                        CatalogueList.parent == parent,
                                                        func.lower(CatalogueList.name) == name.lower()))).scalar_one_or_none()
    if dup:
        raise HTTPException(409, f"'{name}' already exists")
    pos = (await db.execute(select(func.coalesce(func.max(CatalogueList.position), 0)).where(CatalogueList.tenant_id == tenant_id))).scalar() + 1
    row = CatalogueList(tenant_id=tenant_id, kind=body.kind, name=name, parent=parent, position=pos)
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "kind": row.kind, "name": row.name, "parent": row.parent}


async def _list_row(db, tenant_id, list_id: uuid.UUID) -> CatalogueList:
    row = (await db.execute(select(CatalogueList).where(CatalogueList.id == list_id, CatalogueList.tenant_id == tenant_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "List value not found")
    return row


def _usage_clause(row: CatalogueList):
    if row.kind == "category":
        return CatalogueProduct.category == row.name
    if row.kind == "range":
        return (CatalogueProduct.range == row.name) & (CatalogueProduct.category == row.parent)
    return CatalogueProduct.family == row.name


@router.patch("/lists/{list_id}", dependencies=[Depends(require_tier("write"))])
async def rename_list_value(list_id: uuid.UUID, body: ListRename, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                            db=Depends(get_session)):
    row = await _list_row(db, tenant_id, list_id)
    new, old = body.name.strip(), row.name
    if new.lower() != old.lower() and (await db.execute(select(func.count()).select_from(CatalogueList).where(
            CatalogueList.tenant_id == tenant_id, CatalogueList.kind == row.kind, CatalogueList.parent == row.parent,
            func.lower(CatalogueList.name) == new.lower()))).scalar():
        raise HTTPException(409, f"'{new}' already exists")
    products = list((await db.execute(select(CatalogueProduct).where(CatalogueProduct.tenant_id == tenant_id, _usage_clause(row)))).scalars())
    for p in products:
        if row.kind == "category":
            p.category = new
        elif row.kind == "range":
            p.range = new
        else:
            p.family = new
    if row.kind == "category":
        children = (await db.execute(select(CatalogueList).where(CatalogueList.tenant_id == tenant_id, CatalogueList.kind == "range",
                                                                 CatalogueList.parent == old))).scalars()
        for c in children:
            c.parent = new
    row.name = new
    await db.flush()
    return {"id": str(row.id), "name": new, "updated_products": len(products)}


@router.delete("/lists/{list_id}", dependencies=[Depends(require_tier("write"))])
async def delete_list_value(list_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    row = await _list_row(db, tenant_id, list_id)
    used = list((await db.execute(select(CatalogueProduct.name).where(CatalogueProduct.tenant_id == tenant_id, _usage_clause(row)))).scalars())
    if used:
        raise HTTPException(409, {"message": f"'{row.name}' is used by {len(used)} product(s). Reassign them first.", "products": used[:20]})
    if row.kind == "category":
        await db.execute(delete(CatalogueList).where(CatalogueList.tenant_id == tenant_id, CatalogueList.kind == "range",
                                                     CatalogueList.parent == row.name))
    await db.delete(row)
    return {"deleted": True}


# ── products ─────────────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(status: Optional[Status] = None, q: Optional[str] = None, category: Optional[str] = None,
                        range: Optional[str] = None, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    rows = await _all(db, tenant_id)
    catalogue = _catalogue_map(rows)
    costs = await _can_see_costs(auth)
    out = []
    for p in sorted(rows, key=lambda r: r.product_number):
        if status and p.status != status:
            continue
        if category and p.category != category:
            continue
        if range and p.range != range:
            continue
        if q and q.lower() not in f"{p.product_number} {p.name}".lower():
            continue
        out.append(_serialise(p, catalogue, costs))
    return out


@router.post("/products", status_code=201, dependencies=[Depends(require_tier("write"))])
async def create_product(body: ProductIn, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    await _validate_lists(db, tenant_id, body.category, body.range, body.family)
    definition = body.definition.model_dump(mode="json")
    rows = await _all(db, tenant_id)
    catalogue = _catalogue_map(rows)
    await _check_components(db, tenant_id, None, definition, catalogue)
    if body.product_number:
        number = rules.normalise_number(body.product_number)
        if not rules.number_is_valid(number):
            raise HTTPException(422, "Product number must be 3-24 letters, digits or hyphens")
        if await _number_taken(db, tenant_id, number):
            raise HTTPException(409, f"Product number {number} is already used")
    else:
        number = await _next_number(db, tenant_id)
    p = CatalogueProduct(tenant_id=tenant_id, product_number=number, name=body.name.strip(), category=body.category,
                         range=body.range, family=body.family, nature=body.nature, usage=body.usage, owner=body.owner,
                         status="draft", definition=definition, revision=1, created_by=user_id)
    db.add(p)
    await db.flush()
    await _log(db, tenant_id, p.id, "created", user_id, {"product_number": number})
    await db.refresh(p)
    return _serialise(p, {**catalogue, str(p.id): _view(p)}, True)


@router.get("/products/{product_id}")
async def get_product(product_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                      auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    p = await _get(db, tenant_id, product_id)
    rows = await _all(db, tenant_id)
    return _serialise(p, _catalogue_map(rows), await _can_see_costs(auth))


@router.patch("/products/{product_id}", dependencies=[Depends(require_tier("write"))])
async def update_product(product_id: uuid.UUID, body: ProductPatch, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    p = await _get(db, tenant_id, product_id)
    if p.revision != body.expected_revision:
        raise HTTPException(409, {"message": "This product was changed by someone else. Reload and retry.", "revision": p.revision})
    if p.status == "archived":
        raise HTTPException(409, "Archived products cannot be edited")
    changes = body.model_dump(exclude_unset=True, exclude={"expected_revision", "submit_for_review"})
    new_def = body.definition.model_dump(mode="json") if body.definition is not None else None
    active = p.status == "active"
    if active:
        locked = [c for c in rules.ACTIVE_LOCKED_COLUMNS if c in changes and changes[c] != getattr(p, c)]
        if "product_number" in changes and rules.normalise_number(changes["product_number"] or "") != p.product_number:
            locked.append("product_number")
        if new_def is not None:
            locked += rules.commercial_changes(p.definition or {}, new_def)
        if locked:
            raise HTTPException(409, f"An active product's commercial and identity fields ({', '.join(sorted(set(locked)))}) change through a revision, not a direct edit")
    cat = changes.get("category", p.category)
    rng = changes.get("range", p.range)
    if cat != p.category and "range" not in changes:
        rng = ""
    await _validate_lists(db, tenant_id, cat, rng, changes.get("family", p.family))
    if "product_number" in changes and changes["product_number"] is not None:
        number = rules.normalise_number(changes["product_number"])
        if number != p.product_number:
            if not rules.number_is_valid(number):
                raise HTTPException(422, "Product number must be 3-24 letters, digits or hyphens")
            if await _number_taken(db, tenant_id, number, exclude=p.id):
                raise HTTPException(409, f"Product number {number} is already used")
            db.add(CatalogueReservedNumber(tenant_id=tenant_id, product_number=p.product_number))
            p.product_number = number
    for k in ("name", "family", "nature", "usage", "owner"):
        if k in changes and changes[k] is not None:
            setattr(p, k, changes[k].strip() if isinstance(changes[k], str) else changes[k])
    p.category, p.range = cat, rng
    if new_def is not None:
        rows = await _all(db, tenant_id)
        await _check_components(db, tenant_id, p.id, new_def, _catalogue_map(rows))
        p.definition = new_def
    if body.submit_for_review and p.status == "draft":
        p.status = "in_review"
    p.revision += 1
    await db.flush()
    await _log(db, tenant_id, p.id, "updated", user_id, {"fields": sorted(changes), "revision": p.revision})
    rows = await _all(db, tenant_id)
    return _serialise(p, _catalogue_map(rows), True)


@router.get("/products/{product_id}/launch-readiness")
async def launch_readiness(product_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    p = await _get(db, tenant_id, product_id)
    catalogue = _catalogue_map(await _all(db, tenant_id))
    checks = rules.launch_checks(_view(p), catalogue)
    return {"checks": checks, "ready": all(c["ok"] for c in checks) and p.status in ("draft", "in_review")}


@router.post("/products/{product_id}/launch", dependencies=[Depends(require_tier("write"))])
async def launch_product(product_id: uuid.UUID, body: RevisionBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    p = await _get(db, tenant_id, product_id)
    if p.revision != body.expected_revision:
        raise HTTPException(409, {"message": "This product was changed by someone else. Reload and retry.", "revision": p.revision})
    if p.status not in ("draft", "in_review"):
        raise HTTPException(409, f"A {p.status} product cannot be launched")
    catalogue = _catalogue_map(await _all(db, tenant_id))
    checks = rules.launch_checks(_view(p), catalogue)
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise HTTPException(422, {"message": "Launch requirements are not all met", "failed": failed})
    effective = rules.launch_effective_date(_view(p))
    p.status = "active"
    p.launched_at = datetime.now(timezone.utc)
    p.revision += 1
    await db.flush()
    r = (p.definition or {}).get("readiness") or {}
    await _log(db, tenant_id, p.id, "launched", user_id, {
        "effective": effective, "tests": len(r.get("tests") or []), "tests_required": r.get("tests_required", True),
        "icasa": {"required": (r.get("icasa") or {}).get("required"), "items": [
            {"kind": i.get("kind"), "ref": i.get("ref"), "lodged": i.get("lodged"), "effective": i.get("effective")}
            for i in (r.get("icasa") or {}).get("items") or []]}})
    await _publish_event(db, tenant_id, p, "product.published", {"effective": effective})
    rows = await _all(db, tenant_id)
    return _serialise(p, _catalogue_map(rows), True)


async def _publish_event(db, tenant_id, p: CatalogueProduct, event_type: str, extra: dict) -> None:
    """Best-effort domain event (Postgres event bus). Never fails the catalogue write."""
    if db.get_bind().dialect.name != "postgresql":
        return
    try:
        from services.common import event_bus
        async with db.begin_nested():
            await event_bus.ensure_schema(db)
            await event_bus.publish(db, tenant_id, event_type,
                                    {"product_id": str(p.id), "product_number": p.product_number, "revision": p.revision, **extra},
                                    source="inventory.catalogue", subject=("catalogue_product", p.id),
                                    idempotency_key=f"{event_type}:{p.id}:{p.revision}")
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("omnidome.catalogue").warning("event publish failed for %s", p.id, exc_info=True)


@router.post("/products/{product_id}/archive", dependencies=[Depends(require_tier("write"))])
async def archive_product(product_id: uuid.UUID, body: RevisionBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                          user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    p = await _get(db, tenant_id, product_id)
    if p.revision != body.expected_revision:
        raise HTTPException(409, {"message": "This product was changed by someone else. Reload and retry.", "revision": p.revision})
    if p.status == "archived":
        return {"status": "archived"}
    deps = rules.referenced_by(str(p.id), [_view(r) for r in await _all(db, tenant_id)])
    if deps:
        raise HTTPException(409, {"message": "Other products include this one. Resolve them first.", "products": [d["name"] for d in deps]})
    p.status, p.archived_at = "archived", datetime.now(timezone.utc)
    p.revision += 1
    await _log(db, tenant_id, p.id, "archived", user_id)
    await _publish_event(db, tenant_id, p, "product.archived", {})
    return {"status": "archived", "revision": p.revision}


@router.delete("/products/{product_id}", dependencies=[Depends(require_tier("write"))])
async def delete_product(product_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                         user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    """Unused drafts only. The number stays reserved so it is never recycled."""
    p = await _get(db, tenant_id, product_id)
    if p.status not in ("draft", "in_review"):
        raise HTTPException(409, "Only unlaunched drafts can be deleted. Archive launched products instead.")
    deps = rules.referenced_by(str(p.id), [_view(r) for r in await _all(db, tenant_id)])
    if deps:
        raise HTTPException(409, {"message": "Other products include this one.", "products": [d["name"] for d in deps]})
    db.add(CatalogueReservedNumber(tenant_id=tenant_id, product_number=p.product_number))
    await db.execute(delete(CatalogueAsset).where(CatalogueAsset.tenant_id == tenant_id, CatalogueAsset.product_id == p.id))
    await _log(db, tenant_id, p.id, "deleted", user_id, {"product_number": p.product_number, "name": p.name})
    await db.delete(p)
    return {"deleted": True, "reserved_number": p.product_number}


@router.get("/products/{product_id}/history")
async def product_history(product_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    await _get(db, tenant_id, product_id)
    rows = (await db.execute(select(CatalogueEvent).where(CatalogueEvent.tenant_id == tenant_id, CatalogueEvent.product_id == product_id)
                             .order_by(CatalogueEvent.at.desc()))).scalars()
    return [{"id": str(r.id), "kind": r.kind, "actor": str(r.actor) if r.actor else None, "detail": r.detail, "at": r.at} for r in rows]


# ── preview (same rules as launch, no write) ─────────────────────────────────

@router.post("/preview")
async def preview(body: ProductIn, product_id: Optional[uuid.UUID] = None, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                  auth: AuthContext = Depends(get_auth_context), db=Depends(get_session)):
    """Launch checks and economics for an unsaved draft, so the editor shows the server's verdict as the user types."""
    catalogue = _catalogue_map(await _all(db, tenant_id))
    pid = str(product_id) if product_id else "draft"
    status = catalogue[pid]["status"] if pid in catalogue else "draft"
    view = {"id": pid, "name": body.name, "category": body.category, "range": body.range, "family": body.family,
            "nature": body.nature, "usage": body.usage, "status": status, "definition": body.definition.model_dump(mode="json")}
    checks = rules.launch_checks(view, {**catalogue, pid: view})
    out = {"checks": checks, "ready_to_launch": all(c["ok"] for c in checks) and status in ("draft", "in_review")}
    if await _can_see_costs(auth):
        e = rules.economics(pid, {**catalogue, pid: view})
        out["economics"] = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in e.items()}
    return out


# ── assets (pictures and documents) ──────────────────────────────────────────

MAX_ASSET_BYTES = 15 * 1024 * 1024
MAX_ASSETS_PER_PRODUCT = 40
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "avif": "image/avif", "gif": "image/gif"}
MODEL_TYPES = {"glb": "model/gltf-binary", "gltf": "model/gltf+json", "usdz": "model/vnd.usdz+zip"}
DOC_TYPES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "txt": "text/plain; charset=utf-8"}
ALLOWED_TYPES = {**IMAGE_TYPES, **MODEL_TYPES, **DOC_TYPES}      # SVG/HTML are refused: they can carry script


_MAGIC = {  # extension -> leading bytes (hex), so the content must match the claimed type
    "png": "89504e470d0a1a0a", "jpg": "ffd8ff", "jpeg": "ffd8ff", "gif": None, "webp": None, "avif": None,
    "pdf": "255044462d", "docx": "504b0304", "glb": "676c5446", "usdz": "504b0304",
}


def _sniff_ok(ext: str, data: bytes) -> bool:
    """Extension must match the bytes, so a renamed executable or HTML page cannot be stored as a picture."""
    if ext == "txt":
        return bytes([0]) not in data[:4096]
    if ext == "gltf":
        return data.lstrip()[:1] == b"{"
    if ext == "gif":
        return data[:6] in (b"GIF87a", b"GIF89a")
    if ext == "webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if ext == "avif":
        return data[4:8] == b"ftyp" and b"avif" in data[8:32]
    magic = _MAGIC.get(ext)
    return bool(magic) and data.startswith(bytes.fromhex(magic))


@router.post("/products/{product_id}/assets", status_code=201, dependencies=[Depends(require_tier("write"))])
async def upload_asset(product_id: uuid.UUID, request: Request, filename: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    """Raw-body upload (Content-Length bounded) so no multipart dependency is needed: POST bytes with ?filename=."""
    await _get(db, tenant_id, product_id)
    clean = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()[:200]
    ext = clean.rsplit(".", 1)[-1].lower() if "." in clean else ""
    if ext not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported file type. Allowed: " + ", ".join(sorted(ALLOWED_TYPES)))
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_ASSET_BYTES:
        raise HTTPException(413, "File exceeds 15 MB")
    data = b""
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_ASSET_BYTES:
            raise HTTPException(413, "File exceeds 15 MB")
    if not data:
        raise HTTPException(422, "File is empty")
    if not _sniff_ok(ext, data):
        raise HTTPException(422, f"File content does not look like a .{ext} file")
    n = (await db.execute(select(func.count()).select_from(CatalogueAsset).where(
        CatalogueAsset.tenant_id == tenant_id, CatalogueAsset.product_id == product_id))).scalar()
    if n >= MAX_ASSETS_PER_PRODUCT:
        raise HTTPException(409, f"A product can hold at most {MAX_ASSETS_PER_PRODUCT} files")
    kind = "3D" if ext in MODEL_TYPES else "Image" if ext in IMAGE_TYPES else "Document"
    a = CatalogueAsset(tenant_id=tenant_id, product_id=product_id, filename=clean, content_type=ALLOWED_TYPES[ext], size=len(data), data=data)
    db.add(a)
    await db.flush()
    await _log(db, tenant_id, product_id, "asset_added", user_id, {"filename": clean, "size": len(data)})
    return {"id": str(a.id), "name": clean, "kind": kind, "extension": ext, "size": len(data),
            "url": f"/svc/inventory/catalogue/assets/{a.id}"}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    a = (await db.execute(select(CatalogueAsset).where(CatalogueAsset.id == asset_id, CatalogueAsset.tenant_id == tenant_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "File not found")
    inline = a.content_type.startswith("image/")
    return Response(a.data, media_type=a.content_type, headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox",
        "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{a.filename.replace(chr(34), "")}"'})


@router.delete("/assets/{asset_id}", dependencies=[Depends(require_tier("write"))])
async def delete_asset(asset_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       user_id: uuid.UUID = Depends(get_current_user_id), db=Depends(get_session)):
    a = (await db.execute(select(CatalogueAsset).where(CatalogueAsset.id == asset_id, CatalogueAsset.tenant_id == tenant_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "File not found")
    await _log(db, tenant_id, a.product_id, "asset_removed", user_id, {"filename": a.filename})
    await db.delete(a)
    return {"deleted": True}
