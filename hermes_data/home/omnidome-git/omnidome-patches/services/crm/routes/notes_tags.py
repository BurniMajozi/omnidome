"""Customer Notes & Tags routes.

FIX: Converted from sync to async SQLAlchemy. Added delete return fix.
"""

import uuid
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select, func

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import Customer, CustomerNote, CustomerTag
from services.crm.schemas import NoteCreate, NoteRead, TagCreate, TagRead, PaginatedResponse

router = APIRouter(prefix="/customers", tags=["Notes & Tags"])


@router.post("/{customer_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def add_note(
    customer_id: uuid.UUID,
    body: NoteCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        customer = (await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalars().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        note = CustomerNote(
            tenant_id=ctx.tenant_id,
            customer_id=customer_id,
            author_id=ctx.user_id,
            content=body.content,
        )
        session.add(note)
        await session.flush()
        await session.refresh(note)
        return note


@router.get("/{customer_id}/notes")
async def list_notes(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with get_session() as session:
        # Verify customer exists
        customer = (await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalars().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        query = select(CustomerNote).where(
            CustomerNote.customer_id == customer_id,
            CustomerNote.tenant_id == ctx.tenant_id,
        )
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        items = (await session.execute(
            query.order_by(CustomerNote.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        return PaginatedResponse(
            items=[NoteRead.model_validate(n) for n in items],
            total=total or 0, page=page, page_size=page_size,
            pages=max(1, math.ceil((total or 0) / page_size)),
        )


@router.post("/{customer_id}/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def add_tag(
    customer_id: uuid.UUID,
    body: TagCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        customer = (await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalars().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        existing = (await session.execute(
            select(CustomerTag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
                CustomerTag.tag == body.tag,
            )
        )).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail="Tag already exists for this customer")

        tag = CustomerTag(
            tenant_id=ctx.tenant_id,
            customer_id=customer_id,
            tag=body.tag,
        )
        session.add(tag)
        await session.flush()
        await session.refresh(tag)
        return tag


@router.get("/{customer_id}/tags")
async def list_tags(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        customer = (await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
        )).scalars().first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        tags = (await session.execute(
            select(CustomerTag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
            ).order_by(CustomerTag.created_at.desc())
        )).scalars().all()
        return [TagRead.model_validate(t) for t in tags]


@router.delete("/{customer_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(
    customer_id: uuid.UUID,
    tag: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        row = (await session.execute(
            select(CustomerTag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
                CustomerTag.tag == tag,
            )
        )).scalars().first()
        if not row:
            raise HTTPException(status_code=404, detail="Tag not found")
        await session.delete(row)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
