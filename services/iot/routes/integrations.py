"""Home Assistant integration management routes.

Provides CRUD for HA instance registrations, connection testing,
full device sync (fetch all states from HA → upsert to iot_devices),
health checks, and new device discovery.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from services.common.auth import AuthContext, get_auth_context
from services.iot.database import get_session
from services.iot.ha_client import (
    HARestClient,
    decrypt_token,
    encrypt_token,
    ha_entity_to_device_type,
    ha_state_to_device_status,
)
from services.iot.models import IoTDevice, IoTIntegration

logger = logging.getLogger("iot.integrations")

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

INTEGRATION_STATUSES = ["connected", "disconnected", "error", "syncing"]


class IntegrationCreate(BaseModel):
    """Schema for registering a new HA instance."""
    name: str = Field(..., max_length=255, description="Display name for this HA instance")
    ha_url: str = Field(..., max_length=512, description="Home Assistant base URL")
    ha_token: str = Field(..., description="HA long-lived access token (encrypted before storage)")
    is_primary: bool = Field(False, description="Whether this is the primary HA instance for the tenant")
    sync_interval_seconds: int = Field(30, ge=10, le=3600, description="Auto-sync interval in seconds")


class IntegrationUpdate(BaseModel):
    """Schema for updating an existing HA integration (all fields optional)."""
    name: Optional[str] = Field(None, max_length=255)
    ha_url: Optional[str] = Field(None, max_length=512)
    ha_token: Optional[str] = Field(None, description="HA long-lived access token (encrypted before storage)")
    is_primary: Optional[bool] = None
    sync_interval_seconds: Optional[int] = Field(None, ge=10, le=3600)
    status: Optional[str] = Field(None, description=f"One of: {', '.join(INTEGRATION_STATUSES)}")


class IntegrationRead(BaseModel):
    """Schema for integration responses."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    ha_url: str
    status: str
    ha_version: Optional[str]
    last_sync_at: Optional[datetime]
    last_error: Optional[str]
    sync_interval_seconds: int
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedIntegrationResponse(BaseModel):
    items: List[IntegrationRead]
    total: int
    page: int
    page_size: int
    pages: int


class ConnectionTestResponse(BaseModel):
    success: bool
    ha_version: Optional[str] = None
    message: str
    latency_ms: Optional[float] = None


class SyncResponse(BaseModel):
    integration_id: uuid.UUID
    status: str
    devices_synced: int
    devices_created: int
    devices_updated: int
    errors: List[str]
    started_at: datetime
    completed_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    integration_id: uuid.UUID
    status: str
    ha_reachable: bool
    ha_version: Optional[str] = None
    last_sync_at: Optional[datetime]
    last_error: Optional[str]
    checked_at: datetime


class DiscoverResponse(BaseModel):
    integration_id: uuid.UUID
    discovered: int
    new_devices: List[Dict[str, Any]]
    existing_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _integration_to_read(integration: IoTIntegration) -> IntegrationRead:
    """Convert an IoTIntegration ORM instance to an IntegrationRead schema."""
    return IntegrationRead.model_validate(integration)


async def _get_integration_or_404(
    session, integration_id: uuid.UUID, tenant_id: uuid.UUID
) -> IoTIntegration:
    """Fetch an integration by ID scoped to tenant, or raise 404."""
    result = await session.execute(
        select(IoTIntegration).where(
            IoTIntegration.id == integration_id,
            IoTIntegration.tenant_id == tenant_id,
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )
    return integration


def _build_ha_client(integration: IoTIntegration) -> HARestClient:
    """Build an HARestClient from an IoTIntegration (decrypts the token)."""
    token = decrypt_token(integration.ha_token_encrypted)
    return HARestClient(integration.ha_url, token)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedIntegrationResponse)
async def list_integrations(
    ctx: AuthContext = Depends(get_auth_context),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    is_primary: Optional[bool] = Query(None, description="Filter by primary flag"),
):
    """List all HA integrations for the current tenant with optional filters."""
    async with get_session() as session:
        stmt = select(IoTIntegration).where(
            IoTIntegration.tenant_id == ctx.tenant_id
        )
        count_stmt = select(func.count(IoTIntegration.id)).where(
            IoTIntegration.tenant_id == ctx.tenant_id
        )

        if status:
            stmt = stmt.where(IoTIntegration.status == status)
            count_stmt = count_stmt.where(IoTIntegration.status == status)
        if is_primary is not None:
            stmt = stmt.where(IoTIntegration.is_primary == is_primary)
            count_stmt = count_stmt.where(IoTIntegration.is_primary == is_primary)

        total_result = await session.execute(count_stmt)
        total = total_result.scalar() or 0
        pages = max(1, (total + page_size - 1) // page_size)

        stmt = (
            stmt.order_by(IoTIntegration.is_primary.desc(), IoTIntegration.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        integrations = result.scalars().all()

        return PaginatedIntegrationResponse(
            items=[_integration_to_read(i) for i in integrations],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


@router.get("/{integration_id}", response_model=IntegrationRead)
async def get_integration(
    integration_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Get a single HA integration by ID."""
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )
        return _integration_to_read(integration)


@router.post("", response_model=IntegrationRead, status_code=status.HTTP_201_CREATED)
async def register_integration(
    body: IntegrationCreate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Register a new Home Assistant instance.

    The HA token is encrypted before storage. If `is_primary` is set to True,
    any existing primary integration for this tenant will be demoted.
    """
    async with get_session() as session:
        # If setting as primary, demote existing primary
        if body.is_primary:
            existing_primary = await session.execute(
                select(IoTIntegration).where(
                    IoTIntegration.tenant_id == ctx.tenant_id,
                    IoTIntegration.is_primary.is_(True),
                )
            )
            for existing in existing_primary.scalars().all():
                existing.is_primary = False

        # Encrypt the token before storage
        encrypted_token = encrypt_token(body.ha_token)

        integration = IoTIntegration(
            tenant_id=ctx.tenant_id,
            name=body.name,
            ha_url=body.ha_url.rstrip("/"),
            ha_token_encrypted=encrypted_token,
            status="disconnected",
            is_primary=body.is_primary,
            sync_interval_seconds=body.sync_interval_seconds,
        )
        session.add(integration)
        await session.flush()
        await session.refresh(integration)
        logger.info(
            "Integration %s registered (tenant %s, primary=%s)",
            integration.id,
            ctx.tenant_id,
            integration.is_primary,
        )
        return _integration_to_read(integration)


@router.put("/{integration_id}", response_model=IntegrationRead)
async def update_integration(
    integration_id: uuid.UUID,
    body: IntegrationUpdate,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update an existing HA integration.

    If `is_primary` is set to True, any existing primary integration for
    this tenant will be demoted. If `ha_token` is provided it will be
    encrypted before storage.
    """
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )

        # If setting as primary, demote existing primary
        if body.is_primary:
            existing_primary = await session.execute(
                select(IoTIntegration).where(
                    IoTIntegration.tenant_id == ctx.tenant_id,
                    IoTIntegration.is_primary.is_(True),
                    IoTIntegration.id != integration_id,
                )
            )
            for existing in existing_primary.scalars().all():
                existing.is_primary = False

        update_data = body.model_dump(exclude_unset=True)

        # Encrypt token if provided
        if "ha_token" in update_data:
            update_data["ha_token_encrypted"] = encrypt_token(update_data.pop("ha_token"))

        # Normalize URL if provided
        if "ha_url" in update_data and update_data["ha_url"]:
            update_data["ha_url"] = update_data["ha_url"].rstrip("/")

        for field, value in update_data.items():
            setattr(integration, field, value)

        await session.flush()
        await session.refresh(integration)
        logger.info("Integration %s updated (tenant %s)", integration.id, ctx.tenant_id)
        return _integration_to_read(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Delete an HA integration. Associated devices will have their integration_id set to NULL."""
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )
        await session.delete(integration)
        await session.flush()
        logger.info(
            "Integration %s deleted (tenant %s)", integration_id, ctx.tenant_id
        )
        return None


@router.post("/{integration_id}/connect", response_model=ConnectionTestResponse)
async def test_connection(
    integration_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Test the connection to a Home Assistant instance.

    Calls the HA `/api/` endpoint to verify the token and URL are valid.
    Updates the integration status to `connected` on success or `error` on failure.
    """
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )

        ha_client = _build_ha_client(integration)
        try:
            import time as _time
            start = _time.monotonic()
            ha_info = await ha_client.health_check()
            latency_ms = round((_time.monotonic() - start) * 1000, 2)

            ha_version = ha_info.get("version") if isinstance(ha_info, dict) else None

            integration.status = "connected"
            integration.ha_version = ha_version
            integration.last_error = None
            await session.flush()

            return ConnectionTestResponse(
                success=True,
                ha_version=ha_version,
                message="Successfully connected to Home Assistant",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            integration.status = "error"
            integration.last_error = str(exc)
            await session.flush()
            logger.warning(
                "Integration %s connection test failed: %s", integration_id, exc
            )
            return ConnectionTestResponse(
                success=False,
                message=f"Connection failed: {exc}",
            )
        finally:
            await ha_client.aclose()


@router.post("/{integration_id}/sync", response_model=SyncResponse)
async def sync_devices(
    integration_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Perform a full device sync from Home Assistant.

    Fetches all entity states from the HA `/api/states` endpoint and upserts
    them into the `iot_devices` table. Existing devices (matched by
    `tenant_id` + `ha_entity_id`) are updated; new entities are inserted.
    """
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )

        # Mark as syncing
        integration.status = "syncing"
        integration.last_error = None
        await session.flush()

        started_at = datetime.now(timezone.utc)
        devices_synced = 0
        devices_created = 0
        devices_updated = 0
        errors: List[str] = []

        ha_client = _build_ha_client(integration)
        try:
            ha_states = await ha_client.get_states()

            for ha_state in ha_states:
                try:
                    entity_id = ha_state.get("entity_id", "")
                    if not entity_id:
                        continue

                    state_value = ha_state.get("state", "unavailable")
                    attributes = ha_state.get("attributes", {})
                    friendly_name = attributes.get("friendly_name", entity_id)
                    domain = entity_id.split(".")[0] if "." in entity_id else "other"

                    # Check if device already exists for this tenant
                    existing_result = await session.execute(
                        select(IoTDevice).where(
                            IoTDevice.tenant_id == ctx.tenant_id,
                            IoTDevice.ha_entity_id == entity_id,
                        )
                    )
                    existing_device = existing_result.scalar_one_or_none()

                    # Parse timestamps
                    last_changed_str = ha_state.get("last_changed")
                    last_updated_str = ha_state.get("last_updated")
                    last_changed = None
                    last_updated = None
                    if last_changed_str:
                        last_changed = datetime.fromisoformat(
                            last_changed_str.replace("Z", "+00:00")
                        )
                    if last_updated_str:
                        last_updated = datetime.fromisoformat(
                            last_updated_str.replace("Z", "+00:00")
                        )

                    if existing_device:
                        # Update existing device
                        existing_device.friendly_name = friendly_name
                        existing_device.ha_domain = domain
                        existing_device.device_type = ha_entity_to_device_type(entity_id)
                        existing_device.status = ha_state_to_device_status(state_value)
                        existing_device.attributes = attributes
                        existing_device.integration_id = integration_id
                        existing_device.last_changed = last_changed
                        existing_device.last_updated = last_updated
                        existing_device.last_seen = datetime.now(timezone.utc)

                        # Update optional fields from attributes
                        if attributes.get("manufacturer"):
                            existing_device.manufacturer = str(attributes["manufacturer"])
                        if attributes.get("model"):
                            existing_device.model = str(attributes["model"])

                        # Auto-link to inventory product by serial/mac
                        if not existing_device.product_id:
                            serial = (
                                attributes.get("serial_number")
                                or attributes.get("serial")
                                or existing_device.serial_number
                            )
                            mac = attributes.get("mac_address") or attributes.get("mac")
                            if serial or mac:
                                from services.inventory.database import Product as InvProduct
                                product_lookup = await session.execute(
                                    select(InvProduct).where(
                                        InvProduct.tenant_id == ctx.tenant_id,
                                        (
                                            (serial is not None) & (InvProduct.barcode == serial)
                                        ) | (
                                            (mac is not None) & (InvProduct.barcode == mac)
                                        ),
                                    ).limit(1)
                                )
                                matched = product_lookup.scalar_one_or_none()
                                if matched:
                                    existing_device.product_id = matched.id

                        devices_updated += 1
                    else:
                        # Create new device
                        new_device = IoTDevice(
                            tenant_id=ctx.tenant_id,
                            integration_id=integration_id,
                            ha_entity_id=entity_id,
                            ha_domain=domain,
                            friendly_name=friendly_name,
                            device_type=ha_entity_to_device_type(entity_id),
                            status=ha_state_to_device_status(state_value),
                            attributes=attributes,
                            is_controllable=domain in (
                                "light", "switch", "lock", "climate",
                                "alarm_control_panel", "cover", "fan",
                                "media_player", "remote", "scene",
                            ),
                            is_configurable=domain in (
                                "light", "climate", "alarm_control_panel",
                            ),
                            last_changed=last_changed,
                            last_updated=last_updated,
                            last_seen=datetime.now(timezone.utc),
                        )
                        session.add(new_device)
                        devices_created += 1

                    devices_synced += 1
                except Exception as exc:
                    errors.append(f"Error syncing entity {ha_state.get('entity_id', '?')}: {exc}")
                    logger.exception("Error syncing entity from HA")

            # Update integration record
            integration.status = "connected" if not errors else "error"
            integration.last_sync_at = datetime.now(timezone.utc)
            integration.last_error = "; ".join(errors) if errors else None

            # Try to get HA version
            try:
                config = await ha_client.get_config()
                if isinstance(config, dict):
                    integration.ha_version = config.get("version")
            except Exception:
                pass

            await session.flush()
            await session.refresh(integration)

            completed_at = datetime.now(timezone.utc)
            logger.info(
                "Integration %s sync complete: %d synced, %d created, %d updated, %d errors",
                integration_id,
                devices_synced,
                devices_created,
                devices_updated,
                len(errors),
            )

            return SyncResponse(
                integration_id=integration_id,
                status=integration.status,
                devices_synced=devices_synced,
                devices_created=devices_created,
                devices_updated=devices_updated,
                errors=errors,
                started_at=started_at,
                completed_at=completed_at,
            )
        except Exception as exc:
            integration.status = "error"
            integration.last_error = str(exc)
            await session.flush()
            logger.error("Integration %s sync failed: %s", integration_id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Device sync failed: {exc}",
            ) from exc
        finally:
            await ha_client.aclose()


@router.get("/{integration_id}/health", response_model=HealthResponse)
async def integration_health(
    integration_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Check the health / connection status of a HA integration.

    Performs a lightweight HA API call to verify reachability and
    returns the current integration status metadata.
    """
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )

        ha_reachable = False
        ha_version = integration.ha_version
        checked_at = datetime.now(timezone.utc)

        ha_client = _build_ha_client(integration)
        try:
            ha_info = await ha_client.health_check()
            ha_reachable = True
            if isinstance(ha_info, dict) and ha_info.get("version"):
                ha_version = ha_info["version"]
                integration.ha_version = ha_version

            # Update status if it was previously in error
            if integration.status == "error":
                integration.status = "connected"
                integration.last_error = None
            await session.flush()
        except Exception as exc:
            logger.warning(
                "Integration %s health check failed: %s", integration_id, exc
            )
            if integration.status == "connected":
                integration.status = "error"
                integration.last_error = str(exc)
                await session.flush()
        finally:
            await ha_client.aclose()

        return HealthResponse(
            integration_id=integration_id,
            status=integration.status,
            ha_reachable=ha_reachable,
            ha_version=ha_version,
            last_sync_at=integration.last_sync_at,
            last_error=integration.last_error,
            checked_at=checked_at,
        )


@router.post("/{integration_id}/discover", response_model=DiscoverResponse)
async def discover_devices(
    integration_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Discover new devices from Home Assistant that are not yet registered.

    Fetches all entity states from HA and returns a list of entities
    that do not yet exist in the tenant's device registry. This is a
    read-only preview — call `/sync` to actually register them.
    """
    async with get_session() as session:
        integration = await _get_integration_or_404(
            session, integration_id, ctx.tenant_id
        )

        ha_client = _build_ha_client(integration)
        try:
            ha_states = await ha_client.get_states()

            # Get all existing entity IDs for this tenant
            existing_result = await session.execute(
                select(IoTDevice.ha_entity_id).where(
                    IoTDevice.tenant_id == ctx.tenant_id,
                )
            )
            existing_ids = {row[0] for row in existing_result.all()}

            new_devices: List[Dict[str, Any]] = []
            for ha_state in ha_states:
                entity_id = ha_state.get("entity_id", "")
                if not entity_id:
                    continue
                if entity_id not in existing_ids:
                    attributes = ha_state.get("attributes", {})
                    new_devices.append({
                        "entity_id": entity_id,
                        "domain": entity_id.split(".")[0] if "." in entity_id else "other",
                        "friendly_name": attributes.get("friendly_name", entity_id),
                        "device_type": ha_entity_to_device_type(entity_id),
                        "state": ha_state.get("state", "unknown"),
                        "attributes": attributes,
                    })

            logger.info(
                "Integration %s discovery: %d new devices found (existing: %d)",
                integration_id,
                len(new_devices),
                len(existing_ids),
            )

            return DiscoverResponse(
                integration_id=integration_id,
                discovered=len(new_devices),
                new_devices=new_devices,
                existing_count=len(existing_ids),
            )
        except Exception as exc:
            logger.error("Integration %s discovery failed: %s", integration_id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Device discovery failed: {exc}",
            ) from exc
        finally:
            await ha_client.aclose()
