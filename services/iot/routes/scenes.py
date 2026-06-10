"""Scene management routes for IoT.

All routes use async SQLAlchemy with tenant-scoped queries.
Scenes map to Home Assistant scene entities and can be activated
via the HA scene.turn_on service.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.ha_client import HARestClient, decrypt_token
from services.iot.models import IoTIntegration, IoTScene

logger = logging.getLogger("iot.scenes")

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SceneCreate(BaseModel):
    """Schema for creating a new scene."""
    name: str = Field(..., max_length=255)
    ha_scene_id: str | None = Field(None, max_length=128, description="Home Assistant scene entity ID")
    icon: str | None = Field(None, max_length=64)
    description: str | None = None
    scene_config: dict = Field(default_factory=dict, description="Device states to apply when scene is activated")
    is_favorite: bool = False


class SceneUpdate(BaseModel):
    """Schema for updating an existing scene (all fields optional)."""
    name: str | None = Field(None, max_length=255)
    ha_scene_id: str | None = Field(None, max_length=128)
    icon: str | None = Field(None, max_length=64)
    description: str | None = None
    scene_config: dict | None = None
    is_favorite: bool | None = None


class SceneRead(BaseModel):
    """Schema for scene responses."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    ha_scene_id: str | None
    name: str
    icon: str | None
    description: str | None
    scene_config: dict | None
    is_favorite: bool
    activation_count: int
    last_activated: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedSceneResponse(BaseModel):
    items: list[SceneRead]
    total: int
    page: int
    page_size: int
    pages: int


class SceneActivateResponse(BaseModel):
    success: bool
    scene_id: uuid.UUID
    ha_scene_id: str | None
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_ha_client(session, tenant_id: uuid.UUID) -> HARestClient | None:
    """Return a configured HARestClient for the tenant's primary integration."""
    stmt = select(IoTIntegration).where(
        IoTIntegration.tenant_id == tenant_id,
        IoTIntegration.is_primary.is_(True),
    )
    result = await session.execute(stmt)
    integration = result.scalar_one_or_none()
    if not integration:
        stmt = select(IoTIntegration).where(
            IoTIntegration.tenant_id == tenant_id,
        )
        result = await session.execute(stmt)
        integration = result.scalar_one_or_none()
    if not integration:
        return None
    token = decrypt_token(integration.ha_token_encrypted)
    return HARestClient(integration.ha_url, token)


def _scene_to_read(scene: IoTScene) -> SceneRead:
    """Convert an IoTScene ORM instance to a SceneRead schema."""
    return SceneRead.model_validate(scene)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedSceneResponse)
async def list_scenes(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    is_favorite: bool | None = Query(None, description="Filter by favorite status"),
    search: str | None = Query(None, description="Search by name or description"),
):
    """List IoT scenes with optional filters and pagination."""
    async with get_session() as session:
        stmt = select(IoTScene).where(IoTScene.tenant_id == ctx.tenant_id)
        count_stmt = select(func.count(IoTScene.id)).where(IoTScene.tenant_id == ctx.tenant_id)

        if is_favorite is not None:
            stmt = stmt.where(IoTScene.is_favorite == is_favorite)
            count_stmt = count_stmt.where(IoTScene.is_favorite == is_favorite)
        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                IoTScene.name.ilike(search_term)
                | IoTScene.description.ilike(search_term)
            )
            count_stmt = count_stmt.where(
                IoTScene.name.ilike(search_term)
                | IoTScene.description.ilike(search_term)
            )

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(IoTScene.is_favorite.desc(), IoTScene.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        scenes = result.scalars().all()

        return PaginatedSceneResponse(
            items=[_scene_to_read(s) for s in scenes],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{scene_id}", response_model=SceneRead)
async def get_scene(
    scene_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single IoT scene by ID."""
    async with get_session() as session:
        stmt = select(IoTScene).where(
            IoTScene.id == scene_id,
            IoTScene.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        return _scene_to_read(scene)


@router.post("", response_model=SceneRead, status_code=status.HTTP_201_CREATED)
async def create_scene(
    body: SceneCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new IoT scene."""
    async with get_session() as session:
        scene = IoTScene(
            tenant_id=ctx.tenant_id,
            name=body.name,
            ha_scene_id=body.ha_scene_id,
            icon=body.icon,
            description=body.description,
            scene_config=body.scene_config or {},
            is_favorite=body.is_favorite,
        )
        session.add(scene)
        await session.flush()
        await session.refresh(scene)
        logger.info("Scene %s created (tenant %s)", scene.id, ctx.tenant_id)
        return _scene_to_read(scene)


@router.put("/{scene_id}", response_model=SceneRead)
async def update_scene(
    scene_id: uuid.UUID,
    body: SceneUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update an existing IoT scene."""
    async with get_session() as session:
        stmt = select(IoTScene).where(
            IoTScene.id == scene_id,
            IoTScene.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(scene, field, value)

        await session.flush()
        await session.refresh(scene)
        logger.info("Scene %s updated (tenant %s)", scene.id, ctx.tenant_id)
        return _scene_to_read(scene)


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene(
    scene_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete an IoT scene."""
    async with get_session() as session:
        stmt = select(IoTScene).where(
            IoTScene.id == scene_id,
            IoTScene.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
        await session.delete(scene)
        await session.flush()
        logger.info("Scene %s deleted (tenant %s)", scene_id, ctx.tenant_id)
        return None


@router.post("/{scene_id}/activate", response_model=SceneActivateResponse)
async def activate_scene(
    scene_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Activate an IoT scene by calling the HA scene.turn_on service.

    If the scene has a ha_scene_id, the activation is forwarded to
    Home Assistant. Otherwise, the scene is marked as activated
    locally (useful for custom/logical scenes without HA backing).
    """
    async with get_session() as session:
        stmt = select(IoTScene).where(
            IoTScene.id == scene_id,
            IoTScene.tenant_id == ctx.tenant_id,
        )
        result = await session.execute(stmt)
        scene = result.scalar_one_or_none()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")

        ha_scene_id = scene.ha_scene_id

        if ha_scene_id:
            ha_client = await _get_ha_client(session, ctx.tenant_id)
            if not ha_client:
                raise HTTPException(
                    status_code=503,
                    detail="No Home Assistant integration configured for this tenant",
                )
            try:
                await ha_client.call_service(
                    domain="scene",
                    service="turn_on",
                    service_data={"entity_id": ha_scene_id},
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Home Assistant scene.turn_on failed: {exc}",
                ) from exc
            finally:
                await ha_client.aclose()

        # Update activation metadata
        scene.activation_count += 1
        scene.last_activated = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(scene)

        message = (
            f"Scene '{scene.name}' activated via Home Assistant"
            if ha_scene_id
            else f"Scene '{scene.name}' activated (no HA scene linked)"
        )
        logger.info(
            "Scene %s activated (tenant %s, ha_scene_id=%s)",
            scene_id, ctx.tenant_id, ha_scene_id,
        )

        return SceneActivateResponse(
            success=True,
            scene_id=scene.id,
            ha_scene_id=ha_scene_id,
            message=message,
        )
