"""Postgres household checks with an outer rollback. No HA/network/device calls."""
import asyncio
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from services.common.auth import AuthContext
from services.common.db import get_async_engine
from services.iot.models import IoTHome, IoTHomeEntity, IoTHomeSupport, IoTGatewayBinding, IoTHomeRoom, IoTHomeRoomAssignment
from services.iot.models import IoTHomeStatistic, IoTReportingRequest
from services.iot.households import home_for, now
from services.iot.home_events import emit
from sqlalchemy import text, insert, select
from sqlalchemy.exc import IntegrityError


async def check():
    engine = get_async_engine()
    tenant, owner, other, staff = [uuid.uuid4() for _ in range(4)]
    checks = 0
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            first = IoTHome(tenant_id=tenant, customer_id=uuid.uuid4(), owner_user_id=owner, name="Rollback-only isolation probe")
            second = IoTHome(tenant_id=tenant, customer_id=uuid.uuid4(), owner_user_id=other, name="Rollback-only isolation probe B")
            session.add_all([first, second]); await session.flush()
            context = AuthContext(user_id=owner, tenant_id=tenant, roles=["customer"], rbac_loaded=True)
            assert (await home_for(session, context, first.id, "diagnostics")).id == first.id
            checks += 1
            for ctx, expected in [(AuthContext(user_id=other, tenant_id=tenant, roles=["customer"], rbac_loaded=True),404),
                (AuthContext(user_id=owner, tenant_id=uuid.uuid4(), roles=["customer"], rbac_loaded=True),404),
                (AuthContext(user_id=staff, tenant_id=tenant, roles=["technician"], rbac_loaded=True),403)]:
                try:
                    await home_for(session, ctx, first.id, "diagnostics")
                    raise AssertionError("Access should have been denied")
                except HTTPException as error:
                    assert error.status_code == expected
                    checks += 1
            staff_ctx = AuthContext(user_id=staff, tenant_id=tenant, roles=["technician"], rbac_loaded=True)
            grant = IoTHomeSupport(tenant_id=tenant, home_id=first.id, staff_user_id=staff, reference="rollback-probe",
                reason="Rollback-only permission test", scopes=["diagnostics"], status="approved", requested_at=now(), expires_at=now()+timedelta(minutes=5))
            session.add(grant); await session.flush()
            assert (await home_for(session, staff_ctx, first.id, "diagnostics")).id == first.id
            checks += 1
            try:
                await home_for(session, staff_ctx, first.id, "camera")
                raise AssertionError("Camera permission should be denied")
            except HTTPException as error:
                assert error.status_code == 403
                checks += 1
            grant.status = "revoked"; await session.flush()
            try:
                await home_for(session, staff_ctx, first.id, "diagnostics")
                raise AssertionError("Revoked permission should be denied")
            except HTTPException as error:
                assert error.status_code == 403
                checks += 1
            for home in [first, second]:
                session.add(IoTHomeEntity(tenant_id=tenant, home_id=home.id, entity_id="sensor.energy", name="Meter", domain="sensor", state="1", attributes={}, observed_at=now()))
            await session.flush()
            checks += 1
            room = IoTHomeRoom(tenant_id=tenant, home_id=first.id, name="Rollback-only kitchen", kind="kitchen")
            session.add(room); await session.flush()
            assert await session.scalar(select(IoTHomeRoom.name).where(IoTHomeRoom.id == room.id)) == "Rollback-only kitchen"
            checks += 1
            entity = await session.scalar(select(IoTHomeEntity).where(IoTHomeEntity.home_id == first.id))
            session.add(IoTHomeRoomAssignment(entity_id=entity.id, tenant_id=tenant, home_id=first.id, room_id=room.id))
            await session.flush()
            assert await session.scalar(select(IoTHomeRoomAssignment.room_id).where(IoTHomeRoomAssignment.entity_id == entity.id)) == room.id
            checks += 1
            key = "rollback-probe:" + str(first.id)
            await emit(session, first, "iot.home.offline", key)
            await emit(session, first, "iot.home.offline", key)
            facts = (await session.execute(text("SELECT payload FROM domain_events WHERE tenant_id=:tenant AND idempotency_key=:key"),
                {"tenant": str(tenant), "key": "homedome:" + key})).scalars().all()
            assert len(facts) == 1 and facts[0] == {"home_id": str(first.id)}
            checks += 1
            gateway_key = "probe-" + uuid.uuid4().hex[:24]
            await session.execute(insert(IoTGatewayBinding).values(gateway_key=gateway_key, tenant_id=tenant, home_id=first.id))
            try:
                async with session.begin_nested():
                    await session.execute(insert(IoTGatewayBinding).values(gateway_key=gateway_key, tenant_id=uuid.uuid4(), home_id=second.id))
                raise AssertionError("A gateway must not belong to two households")
            except IntegrityError:
                checks += 1
            assert await session.scalar(select(IoTGatewayBinding.home_id).where(IoTGatewayBinding.gateway_key == gateway_key)) == first.id
            checks += 1
            stamp = now().replace(minute=0, second=0, microsecond=0)
            statistic = IoTHomeStatistic(tenant_id=tenant, home_id=first.id, entity_id="sensor.energy", start_at=stamp, values={"sum": 2}, unit="kWh")
            session.add(statistic); await session.flush()
            assert await session.scalar(select(IoTHomeStatistic.values).where(IoTHomeStatistic.id == statistic.id)) == {"sum": 2}
            checks += 1
            try:
                async with session.begin_nested():
                    await session.execute(insert(IoTHomeStatistic).values(tenant_id=tenant, home_id=first.id, entity_id="sensor.energy", start_at=stamp, values={"sum": 3}))
                raise AssertionError("Duplicate home/statistic/hour must be rejected")
            except IntegrityError:
                checks += 1
            request = IoTReportingRequest(tenant_id=tenant, home_id=first.id, requested_by=owner, status="requested")
            session.add(request); await session.flush()
            assert await session.scalar(select(IoTReportingRequest.status).where(IoTReportingRequest.home_id == first.id)) == "requested"
            checks += 1
        finally:
            await transaction.rollback()
            await session.close()
    await engine.dispose()
    print(f"Postgres checks passed: {checks}. All probe rows rolled back.")

asyncio.run(check())
