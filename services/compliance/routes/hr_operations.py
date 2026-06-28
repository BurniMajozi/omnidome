"""
Compliance Service — Leave, Vehicle, Foreign Worker, Travel Routes
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.db import get_async_session as get_db
from services.compliance.database import (
    LeaveApplication, LeaveBalance, LeaveStatus, LeaveType,
    VehicleRegistration, VehicleStatus,
    ForeignWorkerPermit, PermitStatus, PermitType,
    TravelReadiness, VisaStatus, VisaType,
)

router = APIRouter()


# ── Leave Management ────────────────────────────────────────────────────

leave_router = APIRouter(prefix="/leave", tags=["leave"])


@leave_router.get("/applications")
async def list_leave_applications(
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(LeaveApplication)
    if employee_id:
        q = q.where(LeaveApplication.employee_id == employee_id)
    if status:
        q = q.where(LeaveApplication.status == status)
    q = q.order_by(LeaveApplication.start_date.desc())
    result = await db.execute(q)
    return {"items": [a.to_dict() for a in result.scalars().all()]}


@leave_router.post("/applications")
async def create_leave_application(body: dict, db: AsyncSession = Depends(get_db)):
    app = LeaveApplication(**body)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app.to_dict()


@leave_router.put("/applications/{app_id}/approve")
async def approve_leave(app_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LeaveApplication).where(LeaveApplication.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Leave application not found")
    app.status = LeaveStatus.approved
    app.approver_id = body.get("approver_id")
    app.approver_name = body.get("approver_name")
    app.days_approved = body.get("days_approved", app.days_requested)
    from datetime import datetime
    app.approved_date = datetime.utcnow()
    await db.commit()
    return {"status": "approved", "id": app_id}


@leave_router.put("/applications/{app_id}/reject")
async def reject_leave(app_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LeaveApplication).where(LeaveApplication.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(404, "Leave application not found")
    app.status = LeaveStatus.rejected
    app.rejection_reason = body.get("rejection_reason")
    await db.commit()
    return {"status": "rejected", "id": app_id}


@leave_router.get("/balances/{employee_id}")
async def get_leave_balances(employee_id: int, year: Optional[int] = Query(None), db: AsyncSession = Depends(get_db)):
    if not year:
        year = date.today().year
    result = await db.execute(
        select(LeaveBalance)
        .where(LeaveBalance.employee_id == str(employee_id))
        .where(LeaveBalance.year == year)
    )
    return {"items": [b.to_dict() for b in result.scalars().all()]}


@leave_router.post("/balances")
async def upsert_leave_balance(body: dict, db: AsyncSession = Depends(get_db)):
    bal = LeaveBalance(**body)
    db.add(bal)
    await db.commit()
    await db.refresh(bal)
    return bal.to_dict()


# ── Vehicle Registration ────────────────────────────────────────────────

vehicle_router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@vehicle_router.get("/")
async def list_vehicles(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(VehicleRegistration)
    if status:
        q = q.where(VehicleRegistration.status == status)
    result = await db.execute(q)
    return {"items": [v.to_dict() for v in result.scalars().all()]}


@vehicle_router.post("/")
async def create_vehicle(body: dict, db: AsyncSession = Depends(get_db)):
    v = VehicleRegistration(**body)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v.to_dict()


@vehicle_router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(VehicleRegistration).where(VehicleRegistration.id == vehicle_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    return v.to_dict()


@vehicle_router.put("/{vehicle_id}")
async def update_vehicle(vehicle_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(VehicleRegistration).where(VehicleRegistration.id == vehicle_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, "Vehicle not found")
    for k, val in body.items():
        setattr(v, k, val)
    await db.commit()
    await db.refresh(v)
    return v.to_dict()


@vehicle_router.get("/dashboard/expiring")
async def expiring_vehicles(days: int = Query(30), db: AsyncSession = Depends(get_db)):
    from datetime import timedelta
    cutoff = date.today() + timedelta(days=days)
    result = await db.execute(
        select(VehicleRegistration)
        .where(VehicleRegistration.license_expiry <= cutoff)
        .where(VehicleRegistration.status == VehicleStatus.active)
    )
    return {"items": [v.to_dict() for v in result.scalars().all()]}


# ── Foreign Worker Permits ──────────────────────────────────────────────

fw_router = APIRouter(prefix="/foreign-workers", tags=["foreign-workers"])


@fw_router.get("/")
async def list_foreign_workers(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ForeignWorkerPermit)
    if status:
        q = q.where(ForeignWorkerPermit.status == status)
    q = q.order_by(ForeignWorkerPermit.expiry_date)
    result = await db.execute(q)
    return {"items": [w.to_dict() for w in result.scalars().all()]}


@fw_router.post("/")
async def create_foreign_worker(body: dict, db: AsyncSession = Depends(get_db)):
    w = ForeignWorkerPermit(**body)
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return w.to_dict()


@fw_router.get("/{worker_id}")
async def get_foreign_worker(worker_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ForeignWorkerPermit).where(ForeignWorkerPermit.id == worker_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Worker permit not found")
    return w.to_dict()


@fw_router.put("/{worker_id}")
async def update_foreign_worker(worker_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ForeignWorkerPermit).where(ForeignWorkerPermit.id == worker_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Worker permit not found")
    for k, v in body.items():
        setattr(w, k, v)
    await db.commit()
    await db.refresh(w)
    return w.to_dict()


@fw_router.get("/dashboard/expiring")
async def expiring_permits(days: int = Query(60), db: AsyncSession = Depends(get_db)):
    from datetime import timedelta
    cutoff = date.today() + timedelta(days=days)
    result = await db.execute(
        select(ForeignWorkerPermit)
        .where(ForeignWorkerPermit.expiry_date <= cutoff)
        .where(ForeignWorkerPermit.status == PermitStatus.approved)
    )
    return {"items": [w.to_dict() for w in result.scalars().all()]}


# ── Travel Readiness ────────────────────────────────────────────────────

travel_router = APIRouter(prefix="/travel", tags=["travel"])


@travel_router.get("/")
async def list_travel_readiness(
    employee_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(TravelReadiness)
    if employee_id:
        q = q.where(TravelReadiness.employee_id == employee_id)
    result = await db.execute(q)
    return {"items": [t.to_dict() for t in result.scalars().all()]}


@travel_router.post("/")
async def create_travel_readiness(body: dict, db: AsyncSession = Depends(get_db)):
    t = TravelReadiness(**body)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t.to_dict()


@travel_router.get("/{travel_id}")
async def get_travel_readiness(travel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TravelReadiness).where(TravelReadiness.id == travel_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Travel record not found")
    return t.to_dict()


@travel_router.put("/{travel_id}")
async def update_travel_readiness(travel_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TravelReadiness).where(TravelReadiness.id == travel_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Travel record not found")
    for k, v in body.items():
        setattr(t, k, v)
    await db.commit()
    await db.refresh(t)
    return t.to_dict()


@travel_router.get("/dashboard/pending")
async def pending_travel(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TravelReadiness)
        .where(TravelReadiness.overall_status.in_(["pending", "in_progress"]))
    )
    return {"items": [t.to_dict() for t in result.scalars().all()]}
