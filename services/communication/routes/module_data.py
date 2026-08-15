"""Module Data routes — CRUD for module-specific data storage."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import ModuleData
from services.communication.schemas import (
    ModuleDataCreate,
    ModuleDataRead,
    ModuleDataResponse,
    ModuleDataUpdate,
    PaginatedResponse,
)

router = APIRouter(prefix="/module-data", tags=["Module Data"])


@router.post("/", response_model=ModuleDataRead, status_code=status.HTTP_201_CREATED)
async def upsert_module_data(
    body: ModuleDataCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        # Upsert: check if module data already exists for this tenant
        stmt = select(ModuleData).where(
            ModuleData.tenant_id == ctx.tenant_id,
            ModuleData.module_name == body.module_name
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.payload = body.payload
            existing.updated_by = ctx.user_id
            await session.flush()
            await session.refresh(existing)
            return existing

        module_data = ModuleData(
            tenant_id=ctx.tenant_id,
            module_name=body.module_name,
            payload=body.payload,
            updated_by=ctx.user_id,
        )
        session.add(module_data)
        await session.flush()
        await session.refresh(module_data)
        return module_data


@router.get("/", response_model=list[ModuleDataRead])
async def list_module_data(
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(ModuleData).where(
            ModuleData.tenant_id == ctx.tenant_id
        ).order_by(ModuleData.module_name)
        result = await session.execute(stmt)
        items = result.scalars().all()
        return [ModuleDataRead.model_validate(m) for m in items]


@router.get("/{module_name}", response_model=ModuleDataResponse)
async def get_module_data(
    module_name: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(ModuleData).where(
            ModuleData.tenant_id == ctx.tenant_id,
            ModuleData.module_name == module_name
        )
        result = await session.execute(stmt)
        module_data = result.scalar_one_or_none()
        if not module_data:
            raise HTTPException(status_code=404, detail="Module data not found")
        return ModuleDataResponse(
            data=module_data.payload,
            updated_at=module_data.updated_at,
        )


@router.put("/{module_name}", response_model=ModuleDataRead)
async def update_module_data(
    module_name: str,
    body: ModuleDataUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(ModuleData).where(
            ModuleData.tenant_id == ctx.tenant_id,
            ModuleData.module_name == module_name
        )
        result = await session.execute(stmt)
        module_data = result.scalar_one_or_none()
        if not module_data:
            raise HTTPException(status_code=404, detail="Module data not found")

        module_data.payload = body.payload
        module_data.updated_by = ctx.user_id
        await session.flush()
        await session.refresh(module_data)
        return module_data


@router.delete("/{module_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module_data(
    module_name: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(ModuleData).where(
            ModuleData.tenant_id == ctx.tenant_id,
            ModuleData.module_name == module_name
        )
        result = await session.execute(stmt)
        module_data = result.scalar_one_or_none()
        if not module_data:
            raise HTTPException(status_code=404, detail="Module data not found")
        await session.delete(module_data)
