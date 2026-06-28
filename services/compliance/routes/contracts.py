"""
Compliance Service — Contract & SLA Routes
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_db
from services.compliance.database import (
    Contract, ContractAuditLog, ContractSLA, SlaMeasurement,
    ContractStatus, ContractType,
)

router = APIRouter(prefix="/contracts", tags=["contracts"])


# ── Contract CRUD ───────────────────────────────────────────────────────

@router.get("/")
async def list_contracts(
    contract_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(Contract)
    if contract_type:
        q = q.where(Contract.contract_type == contract_type)
    if status:
        q = q.where(Contract.status == status)
    q = q.order_by(Contract.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    contracts = result.scalars().all()
    return {"items": [c.to_dict() for c in contracts], "page": page, "page_size": page_size}


@router.post("/")
async def create_contract(body: dict, db: AsyncSession = Depends(get_db)):
    contract = Contract(**body)
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract.to_dict()


@router.get("/{contract_id}")
async def get_contract(contract_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    return contract.to_dict()


@router.put("/{contract_id}")
async def update_contract(contract_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    for k, v in body.items():
        setattr(contract, k, v)
    # Audit log
    db.add(ContractAuditLog(
        contract_id=contract_id,
        action="update",
        performed_by=body.get("updated_by", "system"),
    ))
    await db.commit()
    await db.refresh(contract)
    return contract.to_dict()


@router.delete("/{contract_id}")
async def delete_contract(contract_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    await db.delete(contract)
    await db.commit()
    return {"status": "deleted"}


@router.get("/{contract_id}/audit")
async def get_contract_audit(contract_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ContractAuditLog)
        .where(ContractAuditLog.contract_id == contract_id)
        .order_by(ContractAuditLog.performed_at.desc())
    )
    logs = result.scalars().all()
    return {"items": [l.to_dict() for l in logs]}


# ── Contract SLA ────────────────────────────────────────────────────────

@router.get("/{contract_id}/slas")
async def list_contract_slas(contract_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContractSLA).where(ContractSLA.contract_id == contract_id))
    slas = result.scalars().all()
    return {"items": [s.to_dict() for s in slas]}


@router.post("/{contract_id}/slas")
async def create_contract_sla(contract_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    body["contract_id"] = contract_id
    sla = ContractSLA(**body)
    db.add(sla)
    await db.commit()
    await db.refresh(sla)
    return sla.to_dict()


@router.post("/{contract_id}/slas/{sla_id}/measurements")
async def record_sla_measurement(
    contract_id: int, sla_id: int, body: dict, db: AsyncSession = Depends(get_db),
):
    body["sla_id"] = sla_id
    measurement = SlaMeasurement(**body)
    db.add(measurement)

    # Auto-detect breach
    sla_result = await db.execute(select(ContractSLA).where(ContractSLA.id == sla_id))
    sla = sla_result.scalar_one_or_none()
    if sla and float(body.get("measured_value", 0)) < float(sla.target_value):
        measurement.is_breach = True
        diff_pct = (float(sla.target_value) - float(body["measured_value"])) / float(sla.target_value) * 100
        if diff_pct > 20:
            measurement.breach_severity = "critical"
        elif diff_pct > 10:
            measurement.breach_severity = "high"
        elif diff_pct > 5:
            measurement.breach_severity = "medium"
        else:
            measurement.breach_severity = "low"

    await db.commit()
    await db.refresh(measurement)
    return measurement.to_dict()


@router.get("/{contract_id}/slas/{sla_id}/measurements")
async def list_sla_measurements(
    contract_id: int, sla_id: int, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SlaMeasurement)
        .where(SlaMeasurement.sla_id == sla_id)
        .order_by(SlaMeasurement.measured_at.desc())
    )
    return {"items": [m.to_dict() for m in result.scalars().all()]}


# ── Contract Expiry Dashboard ───────────────────────────────────────────

@router.get("/dashboard/expiring")
async def expiring_contracts(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() + timedelta(days=days)
    result = await db.execute(
        select(Contract)
        .where(Contract.expiry_date <= cutoff)
        .where(Contract.status == ContractStatus.active)
        .order_by(Contract.expiry_date)
    )
    return {"items": [c.to_dict() for c in result.scalars().all()], "cutoff": str(cutoff)}
