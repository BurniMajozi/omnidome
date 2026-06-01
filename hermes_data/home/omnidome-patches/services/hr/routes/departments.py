"""HR Department routes — CRUD with employee count."""

import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from hr.database import session_scope
from hr.models import Department, Employee
from hr.schemas import (
    DepartmentCreate, DepartmentRead, DepartmentUpdate, DepartmentWithCount,
    PaginatedResponse,
)
from services.common.auth import AuthContext, get_auth_context
from sqlalchemy import func, select


router = APIRouter(prefix="/api/v1/hr/departments", tags=["HR Departments"])


@router.get("", response_model=list[DepartmentWithCount])
async def list_departments(
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        departments = (
            await session.execute(
                select(Department).where(
                    Department.tenant_id == ctx.tenant_id
                ).order_by(Department.name)
            )
        ).scalars().all()

        result = []
        for dept in departments:
            emp_count = (
                await session.scalar(
                    select(func.count()).select_from(Employee).where(
                        Employee.tenant_id == ctx.tenant_id,
                        Employee.department == dept.name,
                    )
                )
            ) or 0
            read = DepartmentWithCount.model_validate(dept)
            read.employee_count = emp_count
            result.append(read)
        return result


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def create_department(
    body: DepartmentCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        department = Department(
            tenant_id=ctx.tenant_id,
            name=body.name,
            description=body.description,
            head_id=body.head_id,
        )
        session.add(department)
        await session.flush()
        await session.refresh(department)
        return DepartmentRead.model_validate(department)


@router.put("/{department_id}", response_model=DepartmentRead)
async def update_department(
    department_id: uuid.UUID,
    body: DepartmentUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        department = await session.get(Department, department_id)
        if not department or department.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Department not found")
        update = body.model_dump(exclude_unset=True)
        for k, v in update.items():
            setattr(department, k, v)
        await session.flush()
        await session.refresh(department)
        return DepartmentRead.model_validate(department)


@router.delete("/{department_id}")
async def delete_department(
    department_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        department = await session.get(Department, department_id)
        if not department or department.tenant_id != ctx.tenant_id:
            raise HTTPException(404, "Department not found")
        await session.delete(department)
        await session.flush()
        return {"department_id": str(department_id), "deleted": True}
