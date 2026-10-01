"""
Compliance Service — Leave, Vehicle, Foreign Worker, Travel Routes

Tenant-scoped, explicit request schemas, role tiers. Records holding passport /
permit numbers (foreign workers, travel readiness) need a compliance/hr/finance
admin tier to read.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.auth import AuthContext
from services.common.db import get_async_session as get_db
from services.compliance import crud
from services.compliance.access import member_ctx, sensitive_ctx, write_ctx
from services.compliance.database import (
    LeaveApplication, LeaveBalance, LeaveStatus,
    VehicleRegistration, VehicleStatus,
    ForeignWorkerPermit, PermitStatus,
    TravelReadiness,
)
from services.compliance.write_schemas import create_schema, dump_set, update_schema

router = APIRouter()

LeaveApplicationIn = create_schema(
    LeaveApplication,
    protected=("status", "days_approved", "approver_id", "approver_name", "approved_date", "rejection_reason"),
)
LeaveBalanceIn = create_schema(LeaveBalance)
VehicleIn = create_schema(VehicleRegistration)
VehiclePatch = update_schema(VehicleRegistration)
ForeignWorkerIn = create_schema(ForeignWorkerPermit)
ForeignWorkerPatch = update_schema(ForeignWorkerPermit)
TravelIn = create_schema(TravelReadiness)
TravelPatch = update_schema(TravelReadiness)


class LeaveApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approver_name: Optional[str] = None
    days_approved: Optional[Decimal] = None


class LeaveRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rejection_reason: Optional[str] = None


# ── Leave Management ────────────────────────────────────────────────────

leave_router = APIRouter(prefix="/leave", tags=["leave"])


@leave_router.get("/applications")
async def list_leave_applications(
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if employee_id:
        where.append(LeaveApplication.employee_id == employee_id)
    if status:
        where.append(LeaveApplication.status == status)
    rows = await crud.list_rows(db, ctx, LeaveApplication, *where, order_by=LeaveApplication.start_date.desc())
    return {"items": [a.to_dict() for a in rows]}


@leave_router.post("/applications")
async def create_leave_application(body: LeaveApplicationIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, LeaveApplication, dump_set(body))).to_dict()


@leave_router.put("/applications/{app_id}/approve")
async def approve_leave(app_id: int, body: LeaveApproveIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    app = await crud.get_owned(db, ctx, LeaveApplication, app_id, "Leave application")
    app.status = LeaveStatus.approved
    app.approver_id = str(ctx.user_id)  # the approver is the signed-in user, not a client claim
    app.approver_name = body.approver_name
    app.days_approved = body.days_approved if body.days_approved is not None else app.days_requested
    app.approved_date = datetime.utcnow()
    await db.commit()
    return {"status": "approved", "id": app_id}


@leave_router.put("/applications/{app_id}/reject")
async def reject_leave(app_id: int, body: LeaveRejectIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    app = await crud.get_owned(db, ctx, LeaveApplication, app_id, "Leave application")
    app.status = LeaveStatus.rejected
    app.rejection_reason = body.rejection_reason
    app.approver_id = str(ctx.user_id)
    await db.commit()
    return {"status": "rejected", "id": app_id}


@leave_router.get("/balances/{employee_id}")
async def get_leave_balances(
    employee_id: int,
    year: Optional[int] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    if not year:
        year = date.today().year
    rows = await crud.list_rows(
        db, ctx, LeaveBalance, LeaveBalance.employee_id == str(employee_id), LeaveBalance.year == year,
    )
    return {"items": [b.to_dict() for b in rows]}


@leave_router.post("/balances")
async def upsert_leave_balance(body: LeaveBalanceIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, LeaveBalance, dump_set(body))).to_dict()


# ── Vehicle Registration ────────────────────────────────────────────────

vehicle_router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@vehicle_router.get("/")
async def list_vehicles(
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [VehicleRegistration.status == status] if status else []
    rows = await crud.list_rows(db, ctx, VehicleRegistration, *where)
    return {"items": [v.to_dict() for v in rows]}


@vehicle_router.post("/")
async def create_vehicle(body: VehicleIn, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, VehicleRegistration, dump_set(body))).to_dict()


# Static sub-paths are declared before "/{vehicle_id}" so they are not shadowed.
@vehicle_router.get("/dashboard/expiring")
async def expiring_vehicles(
    days: int = Query(30, ge=0, le=730),
    ctx: AuthContext = Depends(member_ctx),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() + timedelta(days=days)
    rows = await crud.list_rows(
        db, ctx, VehicleRegistration,
        VehicleRegistration.license_expiry <= cutoff,
        VehicleRegistration.status == VehicleStatus.active,
    )
    return {"items": [v.to_dict() for v in rows]}


@vehicle_router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: int, ctx: AuthContext = Depends(member_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.get_owned(db, ctx, VehicleRegistration, vehicle_id, "Vehicle")).to_dict()


@vehicle_router.put("/{vehicle_id}")
async def update_vehicle(vehicle_id: int, body: VehiclePatch, ctx: AuthContext = Depends(write_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, VehicleRegistration, vehicle_id, dump_set(body), "Vehicle")).to_dict()


# ── Foreign Worker Permits ──────────────────────────────────────────────

fw_router = APIRouter(prefix="/foreign-workers", tags=["foreign-workers"])


@fw_router.get("/")
async def list_foreign_workers(
    status: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [ForeignWorkerPermit.status == status] if status else []
    rows = await crud.list_rows(db, ctx, ForeignWorkerPermit, *where, order_by=ForeignWorkerPermit.expiry_date)
    return {"items": [w.to_dict() for w in rows]}


@fw_router.post("/")
async def create_foreign_worker(body: ForeignWorkerIn, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, ForeignWorkerPermit, dump_set(body))).to_dict()


@fw_router.get("/dashboard/expiring")
async def expiring_permits(
    days: int = Query(60, ge=0, le=730),
    ctx: AuthContext = Depends(sensitive_ctx),
    db: AsyncSession = Depends(get_db),
):
    cutoff = date.today() + timedelta(days=days)
    rows = await crud.list_rows(
        db, ctx, ForeignWorkerPermit,
        ForeignWorkerPermit.expiry_date <= cutoff,
        ForeignWorkerPermit.status == PermitStatus.approved,
    )
    return {"items": [w.to_dict() for w in rows]}


@fw_router.get("/{worker_id}")
async def get_foreign_worker(worker_id: int, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.get_owned(db, ctx, ForeignWorkerPermit, worker_id, "Worker permit")).to_dict()


@fw_router.put("/{worker_id}")
async def update_foreign_worker(worker_id: int, body: ForeignWorkerPatch, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, ForeignWorkerPermit, worker_id, dump_set(body), "Worker permit")).to_dict()


# ── Travel Readiness ────────────────────────────────────────────────────

travel_router = APIRouter(prefix="/travel", tags=["travel"])


@travel_router.get("/")
async def list_travel_readiness(
    employee_id: Optional[str] = Query(None),
    ctx: AuthContext = Depends(sensitive_ctx),
    db: AsyncSession = Depends(get_db),
):
    where = [TravelReadiness.employee_id == employee_id] if employee_id else []
    rows = await crud.list_rows(db, ctx, TravelReadiness, *where)
    return {"items": [t.to_dict() for t in rows]}


@travel_router.post("/")
async def create_travel_readiness(body: TravelIn, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.create_row(db, ctx, TravelReadiness, dump_set(body))).to_dict()


@travel_router.get("/dashboard/pending")
async def pending_travel(ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    rows = await crud.list_rows(db, ctx, TravelReadiness, TravelReadiness.overall_status.in_(["pending", "in_progress"]))
    return {"items": [t.to_dict() for t in rows]}


@travel_router.get("/{travel_id}")
async def get_travel_readiness(travel_id: int, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.get_owned(db, ctx, TravelReadiness, travel_id, "Travel record")).to_dict()


@travel_router.put("/{travel_id}")
async def update_travel_readiness(travel_id: int, body: TravelPatch, ctx: AuthContext = Depends(sensitive_ctx), db: AsyncSession = Depends(get_db)):
    return (await crud.update_row(db, ctx, TravelReadiness, travel_id, dump_set(body), "Travel record")).to_dict()
