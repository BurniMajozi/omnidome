"""
Compliance Service — Contract & SLA Routes
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.compliance.database import (
    Contract, ContractAuditLog, ContractSLA, SlaMeasurement,
    ContractStatus, ContractType,
)
from services.compliance.schemas import (
    ContractCreate, ContractUpdate, ContractSLACreate, SlaMeasurementCreate,
    PaginatedResponse,
)

router = APIRouter(prefix="/contracts", tags=["contracts"])


# ── Contract CRUD ───────────────────────────────────────────────────────

@router.get("/", response_model=PaginatedResponse)
async def list_contracts(
    contract_type: Optional[str] = Query(None),
    contract_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        q = select(Contract).where(Contract.tenant_id == ctx.tenant_id)
        if contract_type:
            q = q.where(Contract.contract_type == contract_type)
        if contract_status:
            q = q.where(Contract.status == contract_status)
        q = q.order_by(Contract.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await session.execute(q)
        contracts = result.scalars().all()

        count_q = select(func.count(Contract.id)).where(Contract.tenant_id == ctx.tenant_id)
        if contract_type:
            count_q = count_q.where(Contract.contract_type == contract_type)
        if contract_status:
            count_q = count_q.where(Contract.status == contract_status)
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        return PaginatedResponse.create(
            items=[c.to_dict() for c in contracts],
            total=total, page=page, page_size=page_size
        )


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_contract(
    body: ContractCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        contract = Contract(
            **body.model_dump(exclude={"tenant_id", "created_by"}),
            tenant_id=ctx.tenant_id,
            created_by=ctx.user_id,
        )
        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        return contract.to_dict()


@router.get("/{contract_id}")
async def get_contract(
    contract_id: int,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        return contract.to_dict()


@router.put("/{contract_id}")
async def update_contract(
    contract_id: int,
    body: ContractUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        update_data = body.model_dump(exclude_unset=True)
        for k, v in update_data.items():
            setattr(contract, k, v)

        # Audit log
        session.add(ContractAuditLog(
            tenant_id=ctx.tenant_id,
            contract_id=contract_id,
            action="update",
            performed_by=ctx.user_id,
        ))
        await session.commit()
        await session.refresh(contract)
        return contract.to_dict()


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: int,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
        await session.delete(contract)
        await session.commit()


@router.get("/{contract_id}/audit")
async def get_contract_audit(
    contract_id: int,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        result = await session.execute(
            select(ContractAuditLog)
            .where(
                ContractAuditLog.contract_id == contract_id,
                ContractAuditLog.tenant_id == ctx.tenant_id
            )
            .order_by(ContractAuditLog.performed_at.desc())
        )
        logs = result.scalars().all()
        return {"items": [l.to_dict() for l in logs]}


# ── Contract SLA ────────────────────────────────────────────────────────

@router.get("/{contract_id}/slas")
async def list_contract_slas(
    contract_id: int,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify contract belongs to tenant
        contract_result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        if not contract_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contract not found")

        result = await session.execute(
            select(ContractSLA).where(ContractSLA.contract_id == contract_id)
        )
        slas = result.scalars().all()
        return {"items": [s.to_dict() for s in slas]}


@router.post("/{contract_id}/slas", status_code=status.HTTP_201_CREATED)
async def create_contract_sla(
    contract_id: int,
    body: ContractSLACreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify contract belongs to tenant
        contract_result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        if not contract_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contract not found")

        sla = ContractSLA(
            **body.model_dump(exclude={"contract_id", "tenant_id"}),
            contract_id=contract_id,
            tenant_id=ctx.tenant_id,
        )
        session.add(sla)
        await session.commit()
        await session.refresh(sla)
        return sla.to_dict()


@router.post("/{contract_id}/slas/{sla_id}/measurements", status_code=status.HTTP_201_CREATED)
async def record_sla_measurement(
    contract_id: int,
    sla_id: int,
    body: SlaMeasurementCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify contract belongs to tenant
        contract_result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        if not contract_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contract not found")

        # Verify SLA belongs to contract
        sla_result = await session.execute(
            select(ContractSLA).where(
                ContractSLA.id == sla_id,
                ContractSLA.contract_id == contract_id
            )
        )
        sla = sla_result.scalar_one_or_none()
        if not sla:
            raise HTTPException(status_code=404, detail="SLA not found")

        measurement = SlaMeasurement(
            tenant_id=ctx.tenant_id,
            sla_id=sla_id,
            measured_value=body.measured_value,
            measured_at=body.measured_at,
            notes=body.notes,
        )

        # Auto-detect breach with correct direction logic
        if sla.comparison.value == "lower_is_worse":
            is_breach = float(body.measured_value) < float(sla.target_value)
        else:  # higher_is_worse
            is_breach = float(body.measured_value) > float(sla.target_value)

        if is_breach:
            measurement.is_breach = True
            diff_pct = abs(float(sla.target_value) - float(body.measured_value)) / float(sla.target_value) * 100
            if diff_pct > 20:
                measurement.breach_severity = "critical"
            elif diff_pct > 10:
                measurement.breach_severity = "high"
            elif diff_pct > 5:
                measurement.breach_severity = "medium"
            else:
                measurement.breach_severity = "low"

        session.add(measurement)
        await session.commit()
        await session.refresh(measurement)
        return measurement.to_dict()


@router.get("/{contract_id}/slas/{sla_id}/measurements")
async def list_sla_measurements(
    contract_id: int,
    sla_id: int,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify contract belongs to tenant
        contract_result = await session.execute(
            select(Contract).where(
                Contract.id == contract_id,
                Contract.tenant_id == ctx.tenant_id
            )
        )
        if not contract_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contract not found")

        result = await session.execute(
            select(SlaMeasurement)
            .where(SlaMeasurement.sla_id == sla_id)
            .order_by(SlaMeasurement.measured_at.desc())
        )
        return {"items": [m.to_dict() for m in result.scalars().all()]}


# ── Contract Expiry Dashboard ──────────────────────────────────────────

@router.get("/dashboard/expiring")
async def expiring_contracts(
    days: int = Query(30, ge=1, le=365),
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        cutoff = date.today() + timedelta(days=days)
        result = await session.execute(
            select(Contract)
            .where(
                Contract.expiry_date <= cutoff,
                Contract.status == ContractStatus.active,
                Contract.tenant_id == ctx.tenant_id
            )
            .order_by(Contract.expiry_date)
        )
        return {"items": [c.to_dict() for c in result.scalars().all()], "cutoff": str(cutoff)}