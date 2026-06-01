"""Task routes — CRUD for tasks linked to channels."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.models import Task
from services.communication.schemas import (
    PaginatedResponse,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        task = Task(
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            message_id=body.message_id,
            user_id=ctx.user_id,
            title=body.title,
            description=body.description,
            assignee_id=body.assignee_id,
            due_date=body.due_date,
            created_by=ctx.user_id,
        )
        session.add(task)
        await session.flush()
        await session.refresh(task)
        return task


@router.get("", response_model=PaginatedResponse)
async def list_tasks(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    assignee: Optional[uuid.UUID] = Query(None),
):
    async with session_scope() as session:
        stmt = select(Task).where(Task.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(Task.id)).where(
            Task.tenant_id == ctx.tenant_id
        )

        if channel_id:
            stmt = stmt.where(Task.channel_id == channel_id)
            count_stmt = count_stmt.where(Task.channel_id == channel_id)
        if status_filter:
            stmt = stmt.where(Task.status == status_filter)
            count_stmt = count_stmt.where(Task.status == status_filter)
        if assignee:
            stmt = stmt.where(Task.assignee_id == assignee)
            count_stmt = count_stmt.where(Task.assignee_id == assignee)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return PaginatedResponse(
            items=[TaskRead.model_validate(t) for t in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Task).where(
            Task.id == task_id, Task.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task


@router.put("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Task).where(
            Task.id == task_id, Task.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        await session.flush()
        await session.refresh(task)
        return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Task).where(
            Task.id == task_id, Task.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        await session.delete(task)


@router.patch("/{task_id}/status", response_model=TaskRead)
async def update_task_status(
    task_id: uuid.UUID,
    body: TaskUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        stmt = select(Task).where(
            Task.id == task_id, Task.tenant_id == ctx.tenant_id
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if body.status is not None:
            task.status = body.status
        await session.flush()
        await session.refresh(task)
        return task
