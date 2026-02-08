"""Customer Notes & Tags routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.common.auth import AuthContext, get_auth_context
from services.crm.database import get_session
from services.crm.models import Customer, CustomerNote, CustomerTag
from services.crm.schemas import NoteCreate, NoteRead, TagCreate, TagRead

router = APIRouter(prefix="/customers", tags=["Notes & Tags"])


# ---------------------------------------------------------------------------
# POST /customers/{id}/notes — Add note to customer
# ---------------------------------------------------------------------------

@router.post("/{customer_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def add_note(
    customer_id: uuid.UUID,
    body: NoteCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        note = CustomerNote(
            tenant_id=ctx.tenant_id,
            customer_id=customer_id,
            author_id=ctx.user_id,
            content=body.content,
        )
        session.add(note)
        session.flush()
        session.refresh(note)
        return note


# ---------------------------------------------------------------------------
# GET /customers/{id}/notes — List notes for customer
# ---------------------------------------------------------------------------

@router.get("/{customer_id}/notes", response_model=list[NoteRead])
def list_notes(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    limit: int = Query(50, ge=1, le=200),
):
    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        notes = (
            session.query(CustomerNote)
            .filter(
                CustomerNote.customer_id == customer_id,
                CustomerNote.tenant_id == ctx.tenant_id,
            )
            .order_by(CustomerNote.created_at.desc())
            .limit(limit)
            .all()
        )
        return [NoteRead.model_validate(n) for n in notes]


# ---------------------------------------------------------------------------
# POST /customers/{id}/tags — Tag customer
# ---------------------------------------------------------------------------

@router.post("/{customer_id}/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def add_tag(
    customer_id: uuid.UUID,
    body: TagCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Check for duplicate tag
        existing = (
            session.query(CustomerTag)
            .filter(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
                CustomerTag.tag == body.tag,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Tag already exists for this customer")

        tag = CustomerTag(
            tenant_id=ctx.tenant_id,
            customer_id=customer_id,
            tag=body.tag,
        )
        session.add(tag)
        session.flush()
        session.refresh(tag)
        return tag


# ---------------------------------------------------------------------------
# GET /customers/{id}/tags — List tags for customer
# ---------------------------------------------------------------------------

@router.get("/{customer_id}/tags", response_model=list[TagRead])
def list_tags(
    customer_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        customer = (
            session.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == ctx.tenant_id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        tags = (
            session.query(CustomerTag)
            .filter(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
            )
            .order_by(CustomerTag.created_at.desc())
            .all()
        )
        return [TagRead.model_validate(t) for t in tags]


# ---------------------------------------------------------------------------
# DELETE /customers/{id}/tags/{tag} — Remove tag from customer
# ---------------------------------------------------------------------------

@router.delete("/{customer_id}/tags/{tag}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tag(
    customer_id: uuid.UUID,
    tag: str,
    ctx: AuthContext = Depends(get_auth_context),
):
    with get_session() as session:
        row = (
            session.query(CustomerTag)
            .filter(
                CustomerTag.customer_id == customer_id,
                CustomerTag.tenant_id == ctx.tenant_id,
                CustomerTag.tag == tag,
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Tag not found")
        session.delete(row)
