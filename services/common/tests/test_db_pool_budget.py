import pytest
from services.common.db import database_pool_options


def test_small_postgres_budget_and_sqlite_compatibility(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test@localhost/test")
    monkeypatch.setenv("DB_POOL_SIZE", "1")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "1")
    assert database_pool_options() == {"pool_size": 1, "max_overflow": 1}
    monkeypatch.setenv("DB_POOL_SIZE", "0")
    with pytest.raises(ValueError):
        database_pool_options()
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    assert database_pool_options() == {}
