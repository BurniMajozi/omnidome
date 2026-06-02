"""Customer Notes & Tags routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import Customer, CustomerNote, CustomerTag
from services.crm.schemas import NoteCreate, NoteRead, TagCreate, TagRead

router = APIRouter(prefix="/customers", tags=["Notes & Tags"])


# ---------------------------------------------------------------------------
# POST /customers/{id}/notes — Add note to customer
# ---------------------------------------------------------------------------

@router.post("/{customer_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def add_note(
    customer_id: uuid.UUID,
    body: NoteCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id
            )
        )
        customer = result.scalar_one_or_none()
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


# ---------------------------------------------------------------------------
# GET /customers/{id}/notes — List notes for customer
# ---------------------------------------------------------------------------

@router.get("/{customer_id}/notes", response_model=list[NoteRead])
async def list_notes(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    limit: int = Query(50, ge=1, le=200),
):
    async with get_session() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        notes_result = await session.execute(
            select(CustomerNote)
            .where(
                CustomerNote.customer_id == customer_id,
                CustomerNote.tenant_id == ctx.tenant_id,
            )
            .order_by(CustomerNote.created_at.desc())
            .limit(limit)
        )
        notes = notes_result.scalars().all()
        return [NoteRead.model_validate(n) for n in notes]


# ---------------------------------------------------------------------------
# POST /customers/{id}/tags — Tag customer
# ---------------------------------------------------------------------------

@router.post("/{customer_id}/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def add_tag(
    customer_id: uuid.UUID,
    body: TagCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Check for duplicate tag
        existing_result = await session.execute(
            select(CustomerTag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
                CustomerTag.tag == body.tag,
            )
        )
        existing = existing_result.scalar_one_or_none()
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


# ---------------------------------------------------------------------------
# GET /customers/{id}/tags — List tags for customer
# ---------------------------------------------------------------------------

@router.get("/{customer_id}/tags", response_model=list[TagRead])
async def list_tags(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(Customer).where(
                Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        tags_result = await session.execute(
            select(CustomerTag)
            .where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
            )
            .order_by(CustomerTag.created_at.desc())
        )
        tags = tags_result.scalars().all()
        return [TagRead.model_validate(t) for t in tags]


# ---------------------------------------------------------------------------
# DELETE /customers/{id}/tags/{tag} — Remove tag from customer
# ---------------------------------------------------------------------------

@router.delete("/{customer_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag(
    customer_id: uuid.UUID,
    tag: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with get_session() as session:
        result = await session.execute(
            select(CustomerTag).where(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
                CustomerTag.tag == tag,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Tag not found")
        await session.delete(row)
