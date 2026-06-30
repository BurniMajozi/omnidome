"""
Voicebox Service — Main FastAPI Application
Tenant-scoped voice cloning, personalities, TTS and STT for OmniDome's
call center, agent orchestrator (Hermes), and webchat. Proxies the heavy
ML work to the vendored voicebox engine (services/voicebox/engine);
this service itself stays lightweight (no PyTorch).
Port: 8027 | Module: voicebox
"""

import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from services.common.auth import get_current_tenant_id
from services.common.entitlements import EntitlementGuard
from services.common.middleware import configure_production

from services.voicebox import engine_client
from services.voicebox.database import (
    AgentVoiceBinding,
    VoiceGeneration,
    VoicePersonality,
    VoiceProfile,
    get_session,
    init_tables,
)

logger = logging.getLogger("voicebox")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(title="OmniDome Voicebox Service", version="0.1.0")
guard = EntitlementGuard(module_id="voicebox")

configure_production(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health():
    engine_up = await engine_client.health()
    return {"status": "ok", "service": "voicebox", "engine_reachable": engine_up}


@app.on_event("startup")
async def startup() -> None:
    guard.ensure_startup()
    await init_tables()


@app.middleware("http")
async def entitlement_middleware(request, call_next):
    return await guard.middleware(request, call_next)


def _unavailable(exc: engine_client.VoiceboxEngineUnavailable) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _profile_to_dict(p: VoiceProfile) -> dict:
    return {
        "id": str(p.id), "tenant_id": str(p.tenant_id),
        "name": p.name, "description": p.description, "language": p.language,
        "voice_type": p.voice_type, "engine": p.engine,
        "engine_profile_id": p.engine_profile_id, "status": p.status, "error": p.error,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _personality_to_dict(p: VoicePersonality) -> dict:
    return {
        "id": str(p.id), "tenant_id": str(p.tenant_id),
        "name": p.name, "description": p.description, "style_prompt": p.style_prompt,
        "default_voice_profile_id": str(p.default_voice_profile_id) if p.default_voice_profile_id else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _binding_to_dict(b: AgentVoiceBinding) -> dict:
    return {
        "id": str(b.id), "tenant_id": str(b.tenant_id),
        "scope": b.scope, "scope_ref": b.scope_ref,
        "voice_profile_id": str(b.voice_profile_id),
        "personality_id": str(b.personality_id) if b.personality_id else None,
    }


async def _resolve_profile(profile_id: uuid.UUID, tenant_id: uuid.UUID, db) -> VoiceProfile:
    result = await db.execute(
        select(VoiceProfile).where(VoiceProfile.id == profile_id, VoiceProfile.tenant_id == tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return profile


# ═══════════════════════════════════════════════════════════════════════════
# VOICE PROFILES (cloning + presets)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/voices")
async def list_voices(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    voice_type: Optional[str] = Query(None),
):
    stmt = select(VoiceProfile).where(VoiceProfile.tenant_id == tenant_id)
    if voice_type:
        stmt = stmt.where(VoiceProfile.voice_type == voice_type)
    result = await db.execute(stmt.order_by(VoiceProfile.created_at.desc()))
    return [_profile_to_dict(p) for p in result.scalars().all()]


@app.post("/voices/clone", status_code=status.HTTP_201_CREATED)
async def clone_voice(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    language: str = Form("en"),
    engine: Optional[str] = Form(None),
    reference_text: str = Form(...),
    sample: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Create a voice profile by cloning from an uploaded audio sample."""
    profile = VoiceProfile(
        tenant_id=tenant_id, name=name, description=description, language=language,
        voice_type="cloned", engine=engine, status="pending",
    )
    db.add(profile)
    await db.flush()

    try:
        engine_profile = await engine_client.create_profile(
            name=name, description=description, language=language, voice_type="cloned",
            default_engine=engine,
        )
        sample_bytes = await sample.read()
        await engine_client.add_profile_sample(
            engine_profile_id=engine_profile["id"],
            audio_bytes=sample_bytes,
            filename=sample.filename or "sample.wav",
            reference_text=reference_text,
        )
        profile.engine_profile_id = engine_profile["id"]
        profile.status = "ready"
    except engine_client.VoiceboxEngineUnavailable as exc:
        profile.status = "failed"
        profile.error = str(exc)
        await db.flush()
        raise _unavailable(exc)
    except Exception as exc:
        profile.status = "failed"
        profile.error = str(exc)
        await db.flush()
        raise HTTPException(status_code=502, detail=f"Cloning failed: {exc}")

    await db.flush()
    await db.refresh(profile)
    return _profile_to_dict(profile)


class PresetVoiceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    language: str = "en"
    preset_engine: str
    preset_voice_id: str


@app.post("/voices/preset", status_code=status.HTTP_201_CREATED)
async def create_preset_voice(
    body: PresetVoiceCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Register a stock/preset engine voice as a tenant voice profile (no cloning)."""
    profile = VoiceProfile(
        tenant_id=tenant_id, name=body.name, description=body.description, language=body.language,
        voice_type="preset", engine=body.preset_engine, status="pending",
    )
    db.add(profile)
    await db.flush()

    try:
        engine_profile = await engine_client.create_profile(
            name=body.name, description=body.description, language=body.language, voice_type="preset",
            preset_engine=body.preset_engine, preset_voice_id=body.preset_voice_id,
        )
        profile.engine_profile_id = engine_profile["id"]
        profile.status = "ready"
    except engine_client.VoiceboxEngineUnavailable as exc:
        profile.status = "failed"
        profile.error = str(exc)
        await db.flush()
        raise _unavailable(exc)

    await db.flush()
    await db.refresh(profile)
    return _profile_to_dict(profile)


@app.get("/voices/presets/{engine}")
async def list_preset_voices(engine: str):
    """List stock voices available for a given TTS engine (e.g. kokoro)."""
    try:
        return await engine_client.list_presets(engine)
    except engine_client.VoiceboxEngineUnavailable as exc:
        raise _unavailable(exc)


@app.delete("/voices/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice(
    voice_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    profile = await _resolve_profile(voice_id, tenant_id, db)
    if profile.engine_profile_id:
        await engine_client.delete_profile(profile.engine_profile_id)
    await db.delete(profile)
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# VOICE PERSONALITIES
# ═══════════════════════════════════════════════════════════════════════════

class PersonalityCreate(BaseModel):
    name: str
    description: Optional[str] = None
    style_prompt: Optional[str] = None
    default_voice_profile_id: Optional[uuid.UUID] = None


@app.get("/personalities")
async def list_personalities(tenant_id: uuid.UUID = Depends(get_current_tenant_id), db=Depends(get_session)):
    result = await db.execute(
        select(VoicePersonality).where(VoicePersonality.tenant_id == tenant_id).order_by(VoicePersonality.created_at.desc())
    )
    return [_personality_to_dict(p) for p in result.scalars().all()]


@app.post("/personalities", status_code=status.HTTP_201_CREATED)
async def create_personality(
    body: PersonalityCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    p = VoicePersonality(tenant_id=tenant_id, **body.dict())
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return _personality_to_dict(p)


@app.put("/personalities/{personality_id}")
async def update_personality(
    personality_id: uuid.UUID,
    body: PersonalityCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(VoicePersonality).where(VoicePersonality.id == personality_id, VoicePersonality.tenant_id == tenant_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Personality not found")
    for field, value in body.dict(exclude_unset=True).items():
        setattr(p, field, value)
    await db.flush()
    await db.refresh(p)
    return _personality_to_dict(p)


@app.delete("/personalities/{personality_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personality(
    personality_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    result = await db.execute(
        select(VoicePersonality).where(VoicePersonality.id == personality_id, VoicePersonality.tenant_id == tenant_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Personality not found")
    await db.delete(p)
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════════
# AGENT / WEBCHAT VOICE BINDINGS
# ═══════════════════════════════════════════════════════════════════════════

class BindingCreate(BaseModel):
    scope: str  # call_center_agent, orchestrator_agent_type, webchat_bot
    scope_ref: str
    voice_profile_id: uuid.UUID
    personality_id: Optional[uuid.UUID] = None


@app.put("/bindings")
async def set_binding(
    body: BindingCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Upsert the voice (+ optional personality) bound to a scope/scope_ref."""
    result = await db.execute(
        select(AgentVoiceBinding).where(
            AgentVoiceBinding.tenant_id == tenant_id,
            AgentVoiceBinding.scope == body.scope,
            AgentVoiceBinding.scope_ref == body.scope_ref,
        )
    )
    binding = result.scalar_one_or_none()
    if binding:
        binding.voice_profile_id = body.voice_profile_id
        binding.personality_id = body.personality_id
    else:
        binding = AgentVoiceBinding(tenant_id=tenant_id, **body.dict())
        db.add(binding)
    await db.flush()
    await db.refresh(binding)
    return _binding_to_dict(binding)


@app.get("/bindings")
async def list_bindings(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
    scope: Optional[str] = Query(None),
    scope_ref: Optional[str] = Query(None),
):
    stmt = select(AgentVoiceBinding).where(AgentVoiceBinding.tenant_id == tenant_id)
    if scope:
        stmt = stmt.where(AgentVoiceBinding.scope == scope)
    if scope_ref:
        stmt = stmt.where(AgentVoiceBinding.scope_ref == scope_ref)
    result = await db.execute(stmt)
    return [_binding_to_dict(b) for b in result.scalars().all()]


async def _resolve_binding(scope: str, scope_ref: str, tenant_id: uuid.UUID, db) -> Optional[AgentVoiceBinding]:
    result = await db.execute(
        select(AgentVoiceBinding).where(
            AgentVoiceBinding.tenant_id == tenant_id,
            AgentVoiceBinding.scope == scope,
            AgentVoiceBinding.scope_ref == scope_ref,
        )
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════════
# SPEECH SYNTHESIS (TTS) & TRANSCRIPTION (STT)
# ═══════════════════════════════════════════════════════════════════════════

class SpeakRequest(BaseModel):
    text: str
    voice_profile_id: Optional[uuid.UUID] = None
    scope: Optional[str] = None
    scope_ref: Optional[str] = None
    personality_id: Optional[uuid.UUID] = None
    use_personality: bool = False
    language: str = "en"
    requested_by_service: Optional[str] = None


@app.post("/speak")
async def speak(
    body: SpeakRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db=Depends(get_session),
):
    """Synthesize speech for a voice profile (given directly, or resolved
    from a scope/scope_ref binding — e.g. scope=orchestrator_agent_type,
    scope_ref=support)."""
    voice_profile_id = body.voice_profile_id
    personality_id = body.personality_id

    if voice_profile_id is None:
        if not (body.scope and body.scope_ref):
            raise HTTPException(status_code=400, detail="Provide voice_profile_id, or scope + scope_ref")
        binding = await _resolve_binding(body.scope, body.scope_ref, tenant_id, db)
        if not binding:
            raise HTTPException(status_code=404, detail=f"No voice bound to {body.scope}/{body.scope_ref}")
        voice_profile_id = binding.voice_profile_id
        personality_id = personality_id or binding.personality_id

    profile = await _resolve_profile(voice_profile_id, tenant_id, db)
    if profile.status != "ready" or not profile.engine_profile_id:
        raise HTTPException(status_code=409, detail=f"Voice profile '{profile.name}' is not ready (status={profile.status})")

    generation = VoiceGeneration(
        tenant_id=tenant_id, voice_profile_id=profile.id, personality_id=personality_id,
        source_text=body.text, status="generating", requested_by_service=body.requested_by_service,
    )
    db.add(generation)
    await db.flush()

    try:
        audio_bytes, content_type = await engine_client.speak(
            text=body.text, profile=profile.engine_profile_id, engine=profile.engine,
            personality=body.use_personality, language=body.language,
        )
        generation.status = "completed"
    except engine_client.VoiceboxEngineUnavailable as exc:
        generation.status = "failed"
        await db.flush()
        raise _unavailable(exc)
    except Exception as exc:
        generation.status = "failed"
        await db.flush()
        raise HTTPException(status_code=502, detail=f"Speech generation failed: {exc}")

    await db.flush()
    return Response(content=audio_bytes, media_type=content_type)


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    try:
        audio_bytes = await file.read()
        result = await engine_client.transcribe(
            audio_bytes=audio_bytes, filename=file.filename or "audio.wav", language=language,
        )
        return result
    except engine_client.VoiceboxEngineUnavailable as exc:
        raise _unavailable(exc)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8027)
