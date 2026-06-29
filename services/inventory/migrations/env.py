import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ensure the repo root is importable as `services.*` regardless of cwd.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from services.inventory.database import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# All services share one physical Postgres database (DATABASE_URL), so each
# service's Alembic history must use its own version table to avoid
# colliding with other services' migration state.
VERSION_TABLE = "alembic_version_inventory"

# inventory_products and inventory_levels already exist live, created by
# config/master_schema.sql under a different, incompatible legacy schema
# (different columns, different FK targets — e.g. category_id -> product_categories
# instead of inventory_product_categories) than what Product/InventoryLevel
# model in database.py now describes. Other live tables (sales_planning,
# shipment_items, stock_movements) have FKs into the legacy inventory_products,
# so it cannot be safely altered or dropped here. Excluded from this service's
# Alembic management entirely until that conflict is deliberately reconciled.
EXCLUDED_TABLES = {"inventory_products", "inventory_levels"}

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL", config.get_main_option("sqlalchemy.url")
    ).replace("postgresql+asyncpg://", "postgresql://")


def include_object(object, name, type_, reflected, compare_to):
    """Restrict autogenerate to tables this service actually owns.

    Unlike include_name (which only filters names during DB reflection and
    therefore acts asymmetrically — a name hidden from reflection but still
    present in target_metadata reads as "missing, please create"),
    include_object is consulted for objects from BOTH sides (reflected=True
    for the live DB, reflected=False for the Python model), so the same rule
    applies whether checking "should this proposed DROP happen" or "should
    this proposed CREATE happen". All services share one physical Postgres
    database, so without the metadata-membership check, autogenerate would
    propose dropping every other service's tables too; the explicit
    EXCLUDED_TABLES check additionally keeps the two legacy-schema tables
    untouched on both sides.
    """
    if type_ == "table":
        if name in EXCLUDED_TABLES:
            return False
        return name in target_metadata.tables
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
