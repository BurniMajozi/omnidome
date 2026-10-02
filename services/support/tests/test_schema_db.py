"""Existing tickets remain readable after additive schema reconciliation."""
import asyncio
import os
import uuid
import pytest
from sqlalchemy import Column, MetaData, Table, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.support import database

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Dedicated test database required')
def test_legacy_ticket_columns_preserve_rows(monkeypatch):
    url = make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql+asyncpg')
    assert url.database.endswith('_test')
    async def case():
        schema = 'support_legacy_' + uuid.uuid4().hex
        engine = create_async_engine(url, connect_args={'server_settings': {'search_path': schema}})
        monkeypatch.setattr(database, 'get_async_engine', lambda: engine)
        metadata = MetaData()
        Table('inventory_products', metadata, Column('id', UUID(as_uuid=True), primary_key=True))
        for table in database.Base.metadata.tables.values():
            table.to_metadata(metadata)
        ticket_id, tenant = uuid.uuid4(), uuid.uuid4()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
                await conn.run_sync(metadata.create_all)
            async with factory() as session:
                session.add(database.Ticket(id=ticket_id, tenant_id=tenant, customer_id=uuid.uuid4(), subject='Existing ticket'))
                await session.commit()
            async with engine.begin() as conn:
                for column in ('resolution_notes', 'product_id', 'serial_number', 'finance_status', 'finance_error'):
                    await conn.execute(text(f'ALTER TABLE tickets DROP COLUMN {column}'))
            await database.init_tables()
            await database.init_tables()
            async with factory() as session:
                row = (await session.execute(select(database.Ticket).where(database.Ticket.id == ticket_id))).scalar_one()
                assert row.subject == 'Existing ticket'
                assert row.tenant_id == tenant
                assert row.resolution_notes is None and row.product_id is None
        finally:
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await engine.dispose()
    asyncio.run(case())
