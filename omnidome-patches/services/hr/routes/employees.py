"""HR Employee routes — CRUD, search, manager hierarchy, direct reports."""

import math
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from hr.database import session_scope
from hr.models import Employee
from hr.schemas import (
    DirectReportRead, EmployeeCreate, EmployeeRead, EmployeeWithManager,
    EmployeeUpdate, PaginatedResponse,
)
from services.common.auth import AuthContext, get_auth_context
from sqlalchemy import func, select


router = APIRouter(prefix="/api/v1/hr/employees", tags=["HR Employees"])


async def _next_employee_number(tenant_id: uuid.UUID, session) -> str:
    """Generate a unique employee number like EMP-{tenant_short}-{seq}."""
    short_tenant = str(tenant_id).split("-")[0].upper()[:4]
    result = await session.execute(
        select(func.count()).select_from(Employee).where(Employee.tenant_id == tenant_id)
    )
    seq = (result.scalar() or 0) + 1
    return f"EMP-{short_tenant}-{seq:04d}"


@router.get("", response_model=PaginatedResponse)
async def list_employees(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    department: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, description="Search by first or last name"),
):
    async with session_scope() as session:
        query = select(Employee).where(Employee.tenant_id == ctx.tenant_id)
        if department:
            query = query.where(Employee.department == department)
        if status_filter:
            query = query.where(Employee.status == status_filter)
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Employee.first_name.ilike(search_term))
                | (Employee.last_name.ilike(search_term))
            )

        total = (
            await session.scalar(select(func.count()).select_from(query.subquery()))
        ) or 0

        items = (
            await session.execute(
                query.order_by(Employee.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return PaginatedResponse(
            items=[EmployeeRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        emp_number = await _next_employee_number(ctx.tenant_id, session)
        employee = Employee(
            tenant_id=ctx.tenant_id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            employee_number=emp_number,
            department=body.department,
            role=body.role,
            manager_id=body.manager_id,
            status=body.status or "active",
            hire_date=body.hire_date,
            salary_band=body.salary_band,
        )
        session.add(employee)
        await session.flush()
        await session.refresh(employee)
        return EmployeeRead.model_validate(employee)


@router.get("/{employee_id}", response_model=EmployeeWithManager)
async def get_employee(
    employee_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        employee = await session.get(Employee, employee_id)
        if not employee or employee.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Employee not found")
        return EmployeeWithManager.model_validate(employee)


@router.put("/{employee_id}", response_model=EmployeeRead)
async def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        employee = await session.get(Employee, employee_id)
        if not employee or employee.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Employee not found")
        update = body.model_dump(exclude_unset=True)
        for k, v in update.items():
            setattr(employee, k, v)
        await session.flush()
        await session.refresh(employee)
        return EmployeeRead.model_validate(employee)


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Soft delete — sets employee status to 'terminated'."""
    async with session_scope() as session:
        employee = await session.get(Employee, employee_id)
        if not employee or employee.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Employee not found")
        employee.status = "terminated"
        await session.flush()
        return {"employee_id": str(employee_id), "status": "terminated"}


@router.get("/{employee_id}/reports", response_model=list[DirectReportRead])
async def get_direct_reports(
    employee_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        employee = await session.get(Employee, employee_id)
        if not employee or employee.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Employee not found")
        reports = (
            await session.execute(
                select(Employee).where(
                    Employee.manager_id == employee_id,
                    Employee.tenant_id == ctx.tenant_id,
                ).order_by(Employee.last_name, Employee.first_name)
            )
        ).scalars().all()
        return [DirectReportRead.model_validate(r) for r in reports]
