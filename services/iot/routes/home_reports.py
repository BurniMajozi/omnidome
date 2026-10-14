"""Read-only household reports and a separate tenant commercial request queue."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from services.common.auth import AuthContext, get_auth_context
from services.iot.access import require_tier
from services.iot.database import get_session
from services.iot.households import home_for, audit, client_for, now, aware
from services.iot.ha_client import HAWebSocketClient, token_for_integration
from services.iot.managed_gateway import target_for
from services.iot.models import IoTHome, IoTHomeEntity, IoTHomeReading, IoTHomeStatistic, IoTReportingRequest
from services.iot.home_reports import series_report, finite, clean_statistic
from services.iot.routes.homes import enabled

router = APIRouter(dependencies=[Depends(enabled)])

class RequestStatus(BaseModel):
    status: Literal["contacted", "closed"]

@router.get("/reporting/requests")
async def requests(ctx: AuthContext = Depends(require_tier("admin"))):
    async with get_session() as session:
        rows = (await session.execute(select(IoTReportingRequest, IoTHome.name, IoTHome.customer_id).join(
            IoTHome, (IoTHome.id == IoTReportingRequest.home_id) & (IoTHome.tenant_id == IoTReportingRequest.tenant_id)
        ).where(IoTReportingRequest.tenant_id == ctx.tenant_id).order_by(IoTReportingRequest.updated_at.desc()).limit(100))).all()
        return [{"id": str(row.id), "home": name, "customer_id": str(customer), "status": row.status,
            "created_at": row.created_at, "updated_at": row.updated_at} for row, name, customer in rows]

@router.put("/reporting/requests/{request_id}")
async def update_request(request_id: uuid.UUID, body: RequestStatus, ctx: AuthContext = Depends(require_tier("admin"))):
    async with get_session() as session:
        row = await session.scalar(select(IoTReportingRequest).where(IoTReportingRequest.id == request_id,
            IoTReportingRequest.tenant_id == ctx.tenant_id).with_for_update())
        if not row:
            raise HTTPException(404, "Reporting request not found")
        row.status = body.status
        row.updated_at = now()
        return {"ok": True}

@router.post("/{home_id}/reporting/upgrade")
async def request_upgrade(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        row = await session.scalar(select(IoTReportingRequest).where(IoTReportingRequest.home_id == home.id,
            IoTReportingRequest.tenant_id == ctx.tenant_id))
        if row is None:
            row = IoTReportingRequest(tenant_id=ctx.tenant_id, home_id=home.id, requested_by=ctx.user_id, status="requested")
            session.add(row)
        elif row.status == "closed":
            row.status, row.updated_at = "requested", now()
        audit(session, home, ctx.user_id, "reporting_upgrade_requested")
        return {"status": row.status, "message": "Your ISP has your request. No payment has been taken; basic reporting stays included."}

@router.get("/{home_id}/reports")
async def reports(home_id: uuid.UUID, days: int = Query(30, ge=1, le=30), ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, "diagnostics")
        start, end = now() - timedelta(days=days), now()
        entities = (await session.scalars(select(IoTHomeEntity).where(IoTHomeEntity.tenant_id == ctx.tenant_id,
            IoTHomeEntity.home_id == home.id, IoTHomeEntity.domain == "sensor").order_by(IoTHomeEntity.entity_id).limit(20))).all()
        series = []
        for entity in entities:
            stats = (await session.scalars(select(IoTHomeStatistic).where(IoTHomeStatistic.tenant_id == ctx.tenant_id,
                IoTHomeStatistic.home_id == home.id, IoTHomeStatistic.entity_id == entity.entity_id,
                IoTHomeStatistic.start_at >= start, IoTHomeStatistic.start_at < end).order_by(IoTHomeStatistic.start_at))).all()
            if stats:
                result = series_report(entity, [(aware(row.start_at), row.values) for row in stats], "recorder")
            else:
                rows = (await session.scalars(select(IoTHomeReading).where(IoTHomeReading.tenant_id == ctx.tenant_id,
                    IoTHomeReading.home_id == home.id, IoTHomeReading.entity_id == entity.entity_id,
                    IoTHomeReading.observed_at >= start).order_by(IoTHomeReading.observed_at).limit(10000))).all()
                result = series_report(entity, [(aware(row.observed_at), {"state": row.state}) for row in rows], "observations")
            if result["points"]:
                series.append(result)
        upgrade = await session.scalar(select(IoTReportingRequest).where(IoTReportingRequest.home_id == home.id,
            IoTReportingRequest.tenant_id == ctx.tenant_id)) if home.owner_user_id == ctx.user_id else None
        return {"plan": "included", "days": days, "series": series, "gateway_status": home.status,
            "last_sync_at": home.last_sync_at, "upgrade_status": upgrade.status if upgrade else None,
            "note": "Partial days and missing samples are not complete totals. Observation averages are sample averages; they are not Recorder time-weighted statistics."}

@router.post("/{home_id}/reports/import")
async def import_history(home_id: uuid.UUID, ctx: AuthContext = Depends(get_auth_context)):
    async with get_session() as session:
        home = await home_for(session, ctx, home_id, owner_only=True)
        entities = (await session.scalars(select(IoTHomeEntity).where(IoTHomeEntity.tenant_id == ctx.tenant_id,
            IoTHomeEntity.home_id == home.id, IoTHomeEntity.domain == "sensor").order_by(IoTHomeEntity.entity_id).limit(20))).all()
        chosen = {entity.entity_id: entity for entity in entities if entity.attributes.get("state_class") in {"measurement", "total", "total_increasing"}}
        if not chosen:
            raise HTTPException(409, "Pair and sync a supported sensor before importing history. Sample reports remain available.")
        client = await client_for(home)
        end = now().replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=30)
        websocket = HAWebSocketClient(client.ha_url, token_for_integration(home), managed_gateway=bool(target_for(home)))
        try:
            async with asyncio.timeout(30):
                await websocket.connect()
                rows = await websocket.request("recorder/statistics_during_period",
                    start_time=start.isoformat(), end_time=end.isoformat(), statistic_ids=list(chosen), period="hour",
                    types=["mean", "min", "max", "sum", "state", "change"])
        except Exception:
            raise HTTPException(502, "Historical import failed. Check your gateway connection and try again.") from None
        finally:
            await websocket.close()
        if not isinstance(rows, dict):
            raise HTTPException(502, "The gateway returned an unsupported history response")
        existing = {(row.entity_id, aware(row.start_at)): row for row in (await session.scalars(select(IoTHomeStatistic).where(
            IoTHomeStatistic.tenant_id == ctx.tenant_id, IoTHomeStatistic.home_id == home.id, IoTHomeStatistic.start_at >= start))).all()}
        count = 0
        for identity, entity in chosen.items():
            data = rows.get(identity, [])
            if not isinstance(data, list):
                continue
            for value in data[:745]:
                if not isinstance(value, dict):
                    continue
                stamp = finite(value.get("start"))
                if stamp is None or not start.timestamp() * 1000 <= stamp < end.timestamp() * 1000:
                    continue
                stamp = datetime.fromtimestamp(stamp / 1000, timezone.utc)
                values = clean_statistic(value)
                if not values:
                    continue
                key = (identity, stamp)
                row = existing.get(key)
                if row is None:
                    row = IoTHomeStatistic(tenant_id=ctx.tenant_id, home_id=home.id, entity_id=identity,
                        start_at=stamp, unit=str(entity.attributes.get("unit_of_measurement", ""))[:32])
                    session.add(row); existing[key] = row
                row.values = values
                count += 1
        await session.execute(delete(IoTHomeStatistic).where(IoTHomeStatistic.home_id == home.id,
            IoTHomeStatistic.tenant_id == ctx.tenant_id, IoTHomeStatistic.start_at < start).execution_options(synchronize_session=False))
        audit(session, home, ctx.user_id, "reporting_history_imported", samples=count)
        return {"ok": True, "samples": count}
