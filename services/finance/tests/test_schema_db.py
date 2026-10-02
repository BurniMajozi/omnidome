"""Postgres regression for an existing journal table and concurrent first references."""
import asyncio
import os
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.finance import database

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Dedicated test database required')
def test_existing_journal_schema_and_first_reference_race(monkeypatch):
    url = make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql+asyncpg')
    assert url.database.endswith('_test')
    async def case():
        engine = create_async_engine(url)
        monkeypatch.setattr(database, 'get_async_engine', lambda: engine)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(database.Base.metadata.create_all)
                await conn.execute(text('ALTER TABLE journal_entries DROP COLUMN IF EXISTS deleted_at'))
            await database.init_tables()
            await database.init_tables()
            async with engine.connect() as conn:
                assert (await conn.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='journal_entries' AND column_name='deleted_at'"))).scalar() == 1
            factory = async_sessionmaker(engine, expire_on_commit=False)
            tenant = uuid.uuid4()
            async def allocate():
                async with factory() as session:
                    value = await database.next_journal_reference(session, tenant)
                    await session.commit()
                    return value
            values = await asyncio.gather(*(allocate() for _ in range(8)))
            assert len(set(values)) == 8
            assert sorted(int(value.rsplit('-', 1)[1]) for value in values) == list(range(1, 9))
        finally:
            await engine.dispose()
    asyncio.run(case())
