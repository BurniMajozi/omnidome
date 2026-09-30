"""IoT startup migration planning (no database needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from sqlalchemy.dialects import postgresql  # noqa: E402

from services.iot.database import is_legacy_iot_devices, missing_column_ddl  # noqa: E402
from services.iot.models import Base  # noqa: E402

LEGACY_COLS = {
    "id", "tenant_id", "contact_id", "device_name", "device_type", "mac_address",
    "serial_number", "status", "firmware_version", "last_seen", "metadata", "created_at",
}


def test_model_metadata_is_self_contained():
    # A ForeignKey to a table owned by another service makes create_all raise
    # NoReferencedTableError at startup.
    assert [t.name for t in Base.metadata.sorted_tables]


def test_legacy_shape_detected():
    assert is_legacy_iot_devices(LEGACY_COLS)
    assert not is_legacy_iot_devices(LEGACY_COLS | {"ha_entity_id"})
    assert not is_legacy_iot_devices({"id", "ha_entity_id", "friendly_name"})


def test_missing_integration_id_is_added():
    devices = Base.metadata.tables["iot_devices"]
    have = {c.name for c in devices.columns} - {"integration_id"}
    plan = missing_column_ddl({"iot_devices": have}, dialect=postgresql.dialect())
    assert len(plan) == 1
    table, sql, _col = plan[0]
    assert table == "iot_devices"
    assert 'ADD COLUMN IF NOT EXISTS "integration_id" UUID' in sql
    assert "NOT NULL" not in sql


def test_up_to_date_and_absent_tables_yield_nothing():
    full = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    assert missing_column_ddl(full) == []
    assert missing_column_ddl({}) == []  # tables that do not exist are create_all's job


def test_not_null_only_with_server_default():
    devices = Base.metadata.tables["iot_devices"]
    plan = missing_column_ddl({"iot_devices": {"id"}}, dialect=postgresql.dialect())
    by_col = {c.name: sql for _t, sql, c in plan}
    assert set(by_col) == {c.name for c in devices.columns} - {"id"}
    # ha_domain is NOT NULL without a server default: must be added nullable.
    assert "NOT NULL" not in by_col["ha_domain"]
    # created_at has server_default now(): NOT NULL is safe.
    assert "DEFAULT now()" in by_col["created_at"] and "NOT NULL" in by_col["created_at"]
