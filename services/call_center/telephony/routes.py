"""HTTP API for telephony. Mounted by main.py with the same role-tier dependency as every other route
(settings / trunk / audit / recordings are admin tier via access._ADMIN_PATH)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from services.call_center import access
from services.call_center.database import TelephonyAudit
from services.call_center.telephony.service import Telephony, TelephonyError, get_runtime, settings_view
from services.common.auth import get_current_tenant_id, get_current_user_id

router = APIRouter(dependencies=[Depends(access.enforce_route_tier)])


def _http(exc: TelephonyError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


def _rt() -> Telephony:
    return get_runtime()


class PlaceCall(BaseModel):
    to: str = Field(..., min_length=1, max_length=40)
    agent_id: Optional[uuid.UUID] = None  # admin tier only; agents always call as themselves


class HoldBody(BaseModel):
    on: bool = True


class TransferBody(BaseModel):
    to_agent_id: Optional[uuid.UUID] = None
    to_number: Optional[str] = Field(None, max_length=40)


class DtmfBody(BaseModel):
    digits: str = Field(..., min_length=1, max_length=32)


class SettingsBody(BaseModel):
    enabled: Optional[bool] = None
    dids: Optional[List[str]] = None
    inbound_queue_id: Optional[uuid.UUID] = None
    allowed_prefixes: Optional[List[str]] = None
    blocked_prefixes: Optional[List[str]] = None
    max_concurrent_calls: Optional[int] = None
    max_call_seconds: Optional[int] = None
    max_calls_per_agent_hour: Optional[int] = None
    recording_enabled: Optional[bool] = None
    recording_announcement_confirmed: Optional[bool] = None


@router.get("/telephony/status")
async def telephony_status(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Safe for every agent: no host/credentials. Drives the softphone's honest states."""
    rt = _rt()
    st = await rt.trunk_status(tenant_id)
    row = await rt.get_settings_row(tenant_id)
    view = settings_view(row, tenant_id)
    st["recording_effective"] = view["recording_effective"]
    st["allowed_prefixes"] = view["allowed_prefixes"]
    return st


@router.get("/telephony/settings")
async def get_settings(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return settings_view(await _rt().get_settings_row(tenant_id), tenant_id)


@router.put("/telephony/settings")
async def put_settings(body: SettingsBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    patch = body.model_dump(exclude_unset=True)
    try:
        return await _rt().update_settings(tenant_id, patch)
    except TelephonyError as exc:
        raise _http(exc)


@router.get("/telephony/trunk/status")
async def trunk_status_admin(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    return await _rt().trunk_status(tenant_id, admin_view=True)


@router.post("/telephony/trunk/test")
async def trunk_test(tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    """Re-applies the trunk config and checks REGISTRATION only. Places no call."""
    try:
        return await _rt().test_registration(tenant_id)
    except TelephonyError as exc:
        raise _http(exc)


@router.get("/telephony/audit")
async def audit_log(tenant_id: uuid.UUID = Depends(get_current_tenant_id), limit: int = 100):
    rt = _rt()
    async with rt.factory() as db:
        rows = (await db.execute(select(TelephonyAudit).where(TelephonyAudit.tenant_id == tenant_id)
                                 .order_by(desc(TelephonyAudit.created_at)).limit(max(1, min(limit, 500))))).scalars().all()
    return [{"id": str(r.id), "at": r.created_at.isoformat(), "kind": r.kind, "user_id": str(r.user_id) if r.user_id else None,
             "agent_id": str(r.agent_id) if r.agent_id else None, "to": r.to_number, "result": r.result,
             "session_id": str(r.session_id) if r.session_id else None} for r in rows]


@router.post("/telephony/agents/me/webrtc-credentials")
async def webrtc_credentials(tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                             user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        return await _rt().issue_webrtc(tenant_id, user_id)
    except TelephonyError as exc:
        raise _http(exc)


@router.post("/telephony/calls", status_code=201)
async def place_call(body: PlaceCall, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                     user_id: uuid.UUID = Depends(get_current_user_id)):
    is_admin = access.request_is_admin.get()
    try:
        return await _rt().place_call(tenant_id=tenant_id, user_id=user_id, is_admin=is_admin, to=body.to,
                                      agent_id=body.agent_id if is_admin else None)
    except TelephonyError as exc:
        raise _http(exc)


@router.get("/telephony/calls/active")
async def active_calls(tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                       user_id: uuid.UUID = Depends(get_current_user_id)) -> List[Dict[str, Any]]:
    rt = _rt()
    if rt.bridge is None:
        return []
    if access.request_is_admin.get():
        return rt.bridge.list_active(tenant_id)
    async with rt.factory() as db:
        agent = await rt._agent_for_user(db, tenant_id, user_id)
    return rt.bridge.list_active(tenant_id, agent.id) if agent else []


async def _control(call_id: str, action: str, tenant_id, user_id, **kw):
    try:
        return await _rt().control(tenant_id, user_id, access.request_is_admin.get(), call_id, action, **kw)
    except TelephonyError as exc:
        raise _http(exc)


@router.post("/telephony/calls/{call_id}/hangup")
async def call_hangup(call_id: str, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                      user_id: uuid.UUID = Depends(get_current_user_id)):
    return await _control(call_id, "hangup", tenant_id, user_id)


@router.post("/telephony/calls/{call_id}/hold")
async def call_hold(call_id: str, body: HoldBody = HoldBody(), tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                    user_id: uuid.UUID = Depends(get_current_user_id)):
    return await _control(call_id, "hold", tenant_id, user_id, on=body.on)


@router.post("/telephony/calls/{call_id}/transfer")
async def call_transfer(call_id: str, body: TransferBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                        user_id: uuid.UUID = Depends(get_current_user_id)):
    return await _control(call_id, "transfer", tenant_id, user_id, to_agent_id=body.to_agent_id, to_number=body.to_number)


@router.post("/telephony/calls/{call_id}/dtmf")
async def call_dtmf(call_id: str, body: DtmfBody, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                    user_id: uuid.UUID = Depends(get_current_user_id)):
    return await _control(call_id, "dtmf", tenant_id, user_id, digits=body.digits)


# admin tier (path contains /recordings): audio + Deepgram transcription of a finished recording
@router.get("/recordings/{session_id}/audio")
async def recording_audio(session_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id)):
    try:
        path = await _rt().recording_file(tenant_id, session_id)
    except TelephonyError as exc:
        raise _http(exc)
    return FileResponse(path, media_type="audio/wav", filename=f"call-{session_id}.wav")


@router.post("/recordings/{session_id}/transcribe")
async def recording_transcribe(session_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_current_tenant_id),
                               user_id: uuid.UUID = Depends(get_current_user_id)):
    try:
        text = await _rt().transcribe_recording(tenant_id, session_id, user_id)
    except TelephonyError as exc:
        raise _http(exc)
    return {"session_id": str(session_id), "transcript": text}
