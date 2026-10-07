import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from sqlalchemy import create_engine
from services.support.database import Ticket
from services.support.main import get_my_stats

def test_stats_use_only_actual_tenant_and_technician_timestamps():
    engine = create_engine("sqlite://")
    Ticket.__table__.create(engine)
    tenant, user, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.utcnow()
    with engine.begin() as conn:
        for tid, uid, minutes in [(tenant, user, 30), (tenant, user, 90), (other, user, 999), (tenant, other, 999)]:
            conn.execute(Ticket.__table__.insert().values(tenant_id=tid, customer_id=uuid.uuid4(), assigned_to=uid, subject="Measured job", status="CLOSED", is_fcr=True, created_at=now - timedelta(minutes=minutes), resolved_at=now))
        class Session:
            async def execute(self, query): return conn.execute(query)
        result = asyncio.run(get_my_stats(auth=SimpleNamespace(tenant_id=tenant, user_id=user), db=Session()))
    assert result["jobs_today"] == 2
    assert result["avg_resolution_min"] == 60
    assert result["fcr_rate"] == 100
    assert result["customer_rating"] is None
    assert result["revenue_generated"] is None
    engine.dispose()
