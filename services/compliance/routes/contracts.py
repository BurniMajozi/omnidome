"""
Compliance Service — Contract & SLA Routes

Tenant-scoped (explicit filters from the signed identity), explicit request schemas
derived from the real columns (no mass assignment), role tiers: reads = any member,
create/update/delete = compliance_officer / manager / admin, audit trail = sensitive tier.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud
from services.compliance.access import member_ctx, sensitive_ctx, tenant_str, write_ctx
from services.compliance.database import (
    Contract, ContractAuditLog, ContractSLA, SlaMeasurement, ContractStatus,
)
from services.compliance.schemas import PaginatedResponse
from services.compliance.write_schemas import create_schema, dump_set, update_schema

router = APIRouter(prefix="/contracts", tags=["contracts"])

ContractIn = create_schema(Contract)
ContractPatch = update_schema(Contract)
ContractSLAIn = create_schema(ContractSLA, protected=("contract_id",))


class SlaMeasurementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    measured_value: Decimal
    measured_at: Optional[datetime] = None
    notes: Optional[str] = None


# For these metrics a HIGHER value is worse (response/repair times, latency, loss);
# for everything else (uptime, availability...) a LOWER value than target is the breach.
_HIGHER_IS_WORSE = ("mttr", "latency", "response", "resolution", "repair", "loss", "jitter", "downtime", "outage")


def is_breach(metric: str, measured: float, target: float) -> bool:
    if any(word in (metric or "").lower() for word in _HIGHER_IS_WORSE):
        return measured > target
    return measured < target


async def _owned_contract(db: AsyncSession, ctx: AuthContext, contract_id: int) -> Contract:
    return await crud.get_owned(db, ctx, Contract, contract_id, "Contract")


# ── Contract CRUD ───────────────────────────────────────────────────────

@router.get("/", response_model=PaginatedResponse)
async def list_contracts(
    contract_type: Optional[str] = Query(None),
    contract_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [Contract.tenant_id == tenant_str(ctx)]
    if contract_type:
        where.append(Contract.contract_type == contract_type)
    if contract_status:
        where.append(Contract.status == contract_status)
    q = select(Contract).where(*where).order_by(Contract.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    contracts = (await db.execute(q)).scalars().all()
    total = (await db.execute(select(func.count(Contract.id)).where(*where))).scalar() or 0
    return PaginatedResponse.create(items=[c.to_dict() for c in contracts], total=total, page=page, page_size=page_size)


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_contract(body: ContractIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    data = dump_set(body)
    await crud.assert_owned(db, ctx, Contract, data.get("parent_contract_id"), "Parent contract")
    return (await crud.create_row(db, ctx, Contract, data)).to_dict()


@router.get("/dashboard/expiring")
async def expiring_contracts(
    days: int = Query(30, ge=1, le=365),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() + timedelta(days=days)
    rows = await crud.list_rows(
        db, ctx, Contract,
        Contract.expiry_date <= cutoff, Contract.status == ContractStatus.active,
        order_by=Contract.expiry_date,
    )
    return {"items": [c.to_dict() for c in rows], "cutoff": str(cutoff)}


@router.get("/{contract_id}")
async def get_contract(contract_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    return (await _owned_contract(db, ctx, contract_id)).to_dict()


@router.put("/{contract_id}")
async def update_contract(contract_id: int, body: ContractPatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    contract = await _owned_contract(db, ctx, contract_id)
    data = dump_set(body)
    if data.get("parent_contract_id") == contract_id:
        raise HTTPException(422, "A contract cannot be its own parent")
    await crud.assert_owned(db, ctx, Contract, data.get("parent_contract_id"), "Parent contract")
    for k, v in data.items():
        setattr(contract, k, v)
    db.add(ContractAuditLog(
        tenant_id=tenant_str(ctx),
        contract_id=contract_id,
        action="update",
        performed_by=str(ctx.user_id),
    ))
    await db.commit()
    await db.refresh(contract)
    return contract.to_dict()


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(contract_id: int, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    contract = await _owned_contract(db, ctx, contract_id)
    await db.delete(contract)
    await db.commit()


@router.get("/{contract_id}/audit")
async def get_contract_audit(contract_id: int, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    await _owned_contract(db, ctx, contract_id)
    logs = await crud.list_rows(
        db, ctx, ContractAuditLog, ContractAuditLog.contract_id == contract_id,
        order_by=ContractAuditLog.performed_at.desc(),
    )
    return {"items": [l.to_dict() for l in logs]}


# ── Contract SLA ────────────────────────────────────────────────────────

@router.get("/{contract_id}/slas")
async def list_contract_slas(contract_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    await _owned_contract(db, ctx, contract_id)
    slas = await crud.list_rows(db, ctx, ContractSLA, ContractSLA.contract_id == contract_id)
    return {"items": [s.to_dict() for s in slas]}


@router.post("/{contract_id}/slas", status_code=status.HTTP_201_CREATED)
async def create_contract_sla(contract_id: int, body: ContractSLAIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    await _owned_contract(db, ctx, contract_id)
    data = dump_set(body)
    data["contract_id"] = contract_id
    return (await crud.create_row(db, ctx, ContractSLA, data)).to_dict()


async def _owned_sla(db: AsyncSession, ctx: AuthContext, contract_id: int, sla_id: int) -> ContractSLA:
    await _owned_contract(db, ctx, contract_id)
    sla = (await db.execute(
        crud.scoped_select(ContractSLA, ctx, ContractSLA.id == sla_id, ContractSLA.contract_id == contract_id)
    )).scalar_one_or_none()
    if not sla:
        raise HTTPException(404, "SLA not found")
    return sla


@router.post("/{contract_id}/slas/{sla_id}/measurements", status_code=status.HTTP_201_CREATED)
async def record_sla_measurement(
    contract_id: int, sla_id: int, body: SlaMeasurementIn,
    ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db),
):
    sla = await _owned_sla(db, ctx, contract_id, sla_id)
    measurement = SlaMeasurement(
        tenant_id=tenant_str(ctx),
        sla_id=sla_id,
        measured_value=body.measured_value,
        measured_at=body.measured_at or datetime.utcnow(),
        notes=body.notes,
        is_breach=False,
    )
    target = float(sla.target_value)
    if is_breach(sla.metric, float(body.measured_value), target):
        measurement.is_breach = True
        diff_pct = abs(target - float(body.measured_value)) / target * 100 if target else 100.0
        measurement.breach_severity = (
            "critical" if diff_pct > 20 else "high" if diff_pct > 10 else "medium" if diff_pct > 5 else "low"
        )
    db.add(measurement)
    await db.commit()
    await db.refresh(measurement)
    return measurement.to_dict()


@router.get("/{contract_id}/slas/{sla_id}/measurements")
async def list_sla_measurements(contract_id: int, sla_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    await _owned_sla(db, ctx, contract_id, sla_id)
    rows = await crud.list_rows(
        db, ctx, SlaMeasurement, SlaMeasurement.sla_id == sla_id, order_by=SlaMeasurement.measured_at.desc(),
    )
    return {"items": [m.to_dict() for m in rows]}
