"""Regression for the pre-ORM agent/session tables in the master schema."""
import asyncio
import os
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.call_center import database

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Dedicated test database required')
def test_legacy_agent_and_session_columns_preserve_rows(monkeypatch):
    url = make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql+asyncpg')
    assert url.database.endswith('_test')
    async def case():
        schema = 'calls_legacy_' + uuid.uuid4().hex
        engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
        monkeypatch.setattr(database, 'get_async_engine', lambda: engine)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant, agent_id, call_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
                await conn.run_sync(database.Base.metadata.create_all)
            async with factory() as session:
                session.add(database.Agent(id=agent_id, tenant_id=tenant, name='Existing agent', extension='101'))
                await session.commit()
                session.add(database.CallSession(id=call_id, tenant_id=tenant, agent_id=agent_id, start_time=datetime.now(timezone.utc)))
                await session.commit()
            async with engine.begin() as conn:
                for column in ('skills', 'max_concurrent_calls'):
                    await conn.execute(text(f'ALTER TABLE call_center_agents DROP COLUMN {column}'))
                for column in ('direction', 'queue_id', 'live_transcript', 'outcome', 'notes'):
                    await conn.execute(text(f'ALTER TABLE call_sessions DROP COLUMN {column}'))
            await database.init_tables()
            await database.init_tables()
            async with engine.connect() as conn:
                row = (await conn.execute(select(database.Agent.__table__).where(database.Agent.id == agent_id))).mappings().one()
                assert row['name'] == 'Existing agent' and row['tenant_id'] == tenant
                assert row['skills'] is None and row['max_concurrent_calls'] == 1
                call = (await conn.execute(select(database.CallSession.__table__).where(database.CallSession.id == call_id))).mappings().one()
                assert call['tenant_id'] == tenant and call['agent_id'] == agent_id
                assert call['direction'] == 'UNKNOWN'
        finally:
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await engine.dispose()
    asyncio.run(case())
