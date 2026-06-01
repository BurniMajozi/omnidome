"""HR Leave Request routes — submit, approve, reject, balance tracking."""

import math
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from hr.database import session_scope
from hr.models import Employee, LeaveRequest
from hr.schemas import LeaveBalance, LeaveRequestCreate, LeaveRequestRead, LeaveRequestUpdate, PaginatedResponse
from services.common.auth import AuthContext, get_auth_context
from sqlalchemy import extract, func, select, and_


router = APIRouter(prefix="/api/v1/hr/leave", tags=["HR Leave"])

# Default leave entitlements (days per year)
_DEFAULT_BALANCES = {
    "annual": 21,
    "sick": 10,
    "family": 5,
}


@router.post("", response_model=LeaveRequestRead, status_code=status.HTTP_201_CREATED)
async def submit_leave_request(
    body: LeaveRequestCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        leave = LeaveRequest(
            tenant_id=ctx.tenant_id,
            employee_id=body.employee_id,
            leave_type=body.leave_type,
            start_date=body.start_date,
            end_date=body.end_date,
            reason=body.reason,
            status="pending",
        )
        session.add(leave)
        await session.flush()
        await session.refresh(leave)
        return LeaveRequestRead.model_validate(leave)


@router.get("", response_model=PaginatedResponse)
async def list_leave_requests(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    employee_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    leave_type: Optional[str] = Query(None),
):
    async with session_scope() as session:
        query = select(LeaveRequest).where(LeaveRequest.tenant_id == ctx.tenant_id)
        if employee_id:
            query = query.where(LeaveRequest.employee_id == employee_id)
        if status_filter:
            query = query.where(LeaveRequest.status == status_filter)
        if leave_type:
            query = query.where(LeaveRequest.leave_type == leave_type)

        total = (
            await session.scalar(select(func.count()).select_from(query.subquery()))
        ) or 0

        items = (
            await session.execute(
                query.order_by(LeaveRequest.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=[LeaveRequestRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )


@router.get("/{request_id}", response_model=LeaveRequestRead)
async def get_leave_request(
    request_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        req = await session.get(LeaveRequest, request_id)
        if not req or req.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Leave request not found")
        return LeaveRequestRead.model_validate(req)


@router.post("/{request_id}/approve", response_model=LeaveRequestRead)
async def approve_leave_request(
    request_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        req = await session.get(LeaveRequest, request_id)
        if not req or req.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Leave request not found")
        if req.status != "pending":
            raise HTTPException(400, f"Cannot approve leave request with status '{req.status}'")
        req.status = "approved"
        req.approved_by = ctx.user_id
        await session.flush()
        await session.refresh(req)
        return LeaveRequestRead.model_validate(req)


@router.post("/{request_id}/reject", response_model=LeaveRequestRead)
async def reject_leave_request(
    request_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        req = await session.get(LeaveRequest, request_id)
        if not req or req.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Leave request not found")
        if req.status != "pending":
            raise HTTPException(400, f"Cannot reject leave request with status '{req.status}'")
        req.status = "rejected"
        req.approved_by = ctx.user_id
        await session.flush()
        await session.refresh(req)
        return LeaveRequestRead.model_validate(req)


def _days_between(start: date, end: date) -> int:
    """Calculate number of working days between start and end (inclusive)."""
    delta = (end - start).days + 1
    # Rough estimate: exclude weekends (Saturday=5, Sunday=6 in Python's weekday)
    weekends = 0
    current = start
    while current <= end:
        if current.weekday() >= 5:
            weekends += 1
        current += __import__("datetime").timedelta(days=1)
    return max(0, delta - weekends)


@router.get("/balance/{employee_id}", response_model=LeaveBalance)
async def get_leave_balance(
    employee_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Verify employee exists and belongs to tenant
        employee = await session.get(Employee, employee_id)
        if not employee or employee.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Employee not found")

        current_year = date.today().year
        leave_requests = (
            await session.execute(
                select(LeaveRequest).where(
                    LeaveRequest.tenant_id == ctx.tenant_id,
                    LeaveRequest.employee_id == employee_id,
                    LeaveRequest.status == "approved",
                    extract("year", LeaveRequest.start_date) == current_year,
                )
            )
        ).scalars().all()

        used = {"annual": 0, "sick": 0, "family": 0, "unpaid": 0}
        for req in leave_requests:
            days = _days_between(req.start_date, req.end_date)
            key = req.leave_type if req.leave_type in used else "unpaid"
            used[key] += days

        return LeaveBalance(
            employee_id=employee_id,
            annual_entitled=_DEFAULT_BALANCES["annual"],
            annual_used=used["annual"],
            annual_remaining=max(0, _DEFAULT_BALANCES["annual"] - used["annual"]),
            sick_entitled=_DEFAULT_BALANCES["sick"],
            sick_used=used["sick"],
            sick_remaining=max(0, _DEFAULT_BALANCES["sick"] - used["sick"]),
            family_entitled=_DEFAULT_BALANCES["family"],
            family_used=used["family"],
            family_remaining=max(0, _DEFAULT_BALANCES["family"] - used["family"]),
            unpaid_used=used["unpaid"],
        )
