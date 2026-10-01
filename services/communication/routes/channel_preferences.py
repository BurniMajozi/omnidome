"""Channel preference routes for per-user UI state."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from services.common.auth import AuthContext, get_auth_context
from services.common.db import session_scope
from services.communication.access import get_visible_channel
from services.communication.models import Channel, ChannelPreference
from services.communication.schemas import ChannelPreferenceRead, ChannelPreferenceUpdate

router = APIRouter(prefix="/channels/{channel_id}/preferences", tags=["Channel Preferences"])


@router.get("", response_model=ChannelPreferenceRead)
async def get_preferences(channel_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with session_scope() as session:
        await get_visible_channel(session, ctx, channel_id)
        stmt = select(ChannelPreference).where(
            ChannelPreference.channel_id == channel_id,
            ChannelPreference.tenant_id == ctx.tenant_id,
            ChannelPreference.user_id == ctx.user_id,
        )
        result = await session.execute(stmt)
        pref = result.scalar_one_or_none()
        if pref:
            return pref
        return ChannelPreference(
            tenant_id=ctx.tenant_id,
            channel_id=channel_id,
            user_id=ctx.user_id,
            muted=False,
            pinned=False,
        )


@router.patch("", response_model=ChannelPreferenceRead)
async def update_preferences(
    channel_id: uuid.UUID,
    body: ChannelPreferenceUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    async with session_scope() as session:
        channel = await get_visible_channel(session, ctx, channel_id)

        stmt = select(ChannelPreference).where(
            ChannelPreference.channel_id == channel_id,
            ChannelPreference.tenant_id == ctx.tenant_id,
            ChannelPreference.user_id == ctx.user_id,
        )
        result = await session.execute(stmt)
        pref = result.scalar_one_or_none()
        if not pref:
            pref = ChannelPreference(
                tenant_id=ctx.tenant_id,
                channel_id=channel_id,
                user_id=ctx.user_id,
                muted=False,
                pinned=False,
            )
            session.add(pref)

        updates = body.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(pref, field, value)

        await session.flush()
        await session.refresh(pref)
        return pref
